# 09 — Timber Gridshell System

- `system_id`: `STR-SYS-TIMBER-GRIDSHELL`
- `tectonic_family`: `shell`
- `material_system`: `timber_gridshell`

## Scope and research basis

A timber gridshell is a shell made of **discrete slender members instead of a continuous
surface**. Its defining move is elastic bending: a flat lattice of long laths is
assembled on the ground, then pushed into a doubly curved shape, and the members stay in
that shape under bending stress. The buildability constraint is therefore a *radius*,
not a span — a lath will break before it reaches a curvature the timber cannot take, and
that single limit governs the architecture.

The alternative construction route is a segmented gridshell of individually shaped
members. It relaxes the radius limit and replaces it with a unique-part-count limit.
Either route must be declared, because they produce different geometry rules.

Canonical references:

1. Frei Otto with Ove Arup & Partners, **Mannheim Multihalle**, 1975 — the reference
   elastically bent timber gridshell, formed from a flat lath mat.
2. Edward Cullinan Architects with Buro Happold, **Weald & Downland Museum gridshell**,
   2002 — green oak laths, scarf-jointed, formed by controlled lowering.
3. Shigeru Ban with Arup, **Centre Pompidou-Metz**, 2010 — a woven glulam lattice roof
   built as shaped segments rather than elastically bent laths.
4. Buro Happold and IL Stuttgart research on gridshell form finding — the methodological
   basis for both routes.

Primary sources:

- [AWC 2024 National Design Specification for Wood Construction](https://awc.org/resources/2024-nds/)
- [APA, Glulam Product Guide and design resources](https://www.apawood.org/glulam)
- [IASS, International Association for Shell and Spatial Structures](https://iass-structures.org/)
- [ASCE/SEI 7-22, Minimum Design Loads and Associated Criteria](https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22)

## Structural thesis

Two families of continuous laths cross at pinned or clamped nodes to form a quadrilateral
mesh on a doubly curved surface. A quadrilateral mesh has no in-plane shear stiffness on
its own, so a **third or fourth diagonal layer, or a shear block or cable bracing system,
is mandatory** — this is the single most commonly forgotten requirement of the system.
Boundaries collect the shell thrust into an edge beam and then into ties or foundations.

## Invariants

- `TGS-INV-01` — the construction route is declared: elastically bent laths or shaped
  segments. Every downstream rule depends on it.
- `TGS-INV-02` — for the elastic route, every lath's minimum bending radius is checked
  against the declared species, section, and moisture state. A violated radius is a hard
  failure, not a warning.
- `TGS-INV-03` — a shear-resisting layer is present: a diagonal lath family, cable
  bracing, shear blocks, or structural sheathing. A bare quad mesh fails.
- `TGS-INV-04` — nodes are modelled elements with a declared type (pinned, clamped,
  slotted) and a rotation allowance; a node that must rotate during forming cannot be a
  rigid connection.
- `TGS-INV-05` — lath continuity and scarf-joint positions are modelled; a lath is a long
  continuous member, not a chain of unrelated segments.
- `TGS-INV-06` — the boundary collects thrust into a modelled edge beam and a declared tie
  or abutment.

## Element taxonomy

| Kind | Primitive | Form | Starting range | Located by |
|---|---|---|---|---|
| `lath_family_a` | member | rectangular, continuous | 50 × 50 mm, layered ×2 | mesh direction 1 |
| `lath_family_b` | member | rectangular, continuous | 50 × 50 mm, layered ×2 | mesh direction 2 |
| `diagonal_lath` | member | rectangular | 40 × 40 mm | mesh diagonal, shear layer |
| `shear_block` | box | timber or plywood infill | 0.2–0.4 m | selected mesh cells |
| `bracing_cable` | member | strand | Ø 8–20 mm | mesh diagonals, cable option |
| `grid_node` | box | bolted plate or slotted clamp | 0.10–0.25 m | every family crossing |
| `scarf_joint` | box | finger or scarf splice | 0.3–0.8 m | lath continuity points |
| `edge_beam` | member | curved glulam | 0.2 × 0.5–0.9 m | shell boundary |
| `boundary_tie` | member | steel rod or timber | Ø 25–60 mm | thrust resolution line |
| `purlin` · `cladding_rail` | member | rectangular | 0.05 × 0.15 m | mesh cell subdivision |
| `cladding_panel` | quad | ETFE, timber, or glass | ≤ 1.5 × 1.5 m | mesh cell, planarity checked |
| `support_shoe` | box | steel base fitting | 0.2–0.5 m | every boundary node |
| `abutment` · `footing` | extrusion | mass or piled | 1.0–3.0 m | boundary support line |

## Geometry primitives required

`member` dominates, but with a property no other system needs: a **curved member**. A
lath is not a straight segment between two nodes; it is a continuous spline through many
nodes. `MemberGeometry` must therefore accept a polyline or curve path, not only a
start–end pair:

```python
class MemberGeometry(BaseModel):
    type: Literal['member']
    path: list[Vector3Value]      # 2 points = straight; N points = curved lath
    profile: str
    roll: Vector3Value
    min_bend_radius_m: float | None = None
```

`box` carries nodes and blocks and is architecturally central. `quad` carries cladding
with a planarity check. `extrusion` carries abutments.

## Datum chain specialisation

```text
DATUMS   target_surface_generator, mesh_module, lath_section, species,
         min_bend_radius, shear_layer_type, boundary_type
   ↓
FORM FINDING   compass / geodesic mesh relaxation on the target surface
   ↓
LATTICE  grid_node[i][j]  (two-index, like the cable net)
   ↓
ELEMENTS laths as splines through node rows and columns; diagonals from cell
         diagonals; nodes from crossings; edge beam from the boundary row
```

The lattice is a **two-index node mesh on a curved surface**, so IDs stay self-locating:
`TGS-NODE-I014-J006`, `TGS-LATH-A-ROW014`. Crucially, the mesh must be generated by a
relaxation that keeps lath spacing roughly constant along each lath — a naive UV mesh on
the surface produces varying spacings that cannot be built from a flat mat.

## Legal variables and starting ranges

| Parameter | Starting range | Owner |
|---|---:|---|
| `mesh_module` | 0.5–1.5 m | score (`density`) inside clamp |
| lath section | 35 × 35 to 60 × 60 mm | tectonic |
| lath layers per family | 2–4 | tectonic |
| `min_bend_radius` | ≈ 200–300 × lath depth | material; never score |
| `rise_to_span` | 1 : 4 to 1 : 8 | tectonic; score selects inside |
| span | 10–60 m | program and tectonic |
| shear layer type | diagonal / cable / block / sheathing | tectonic |
| cladding panel planarity | ≤ 1 : 150 of diagonal | fabrication; never score |

## Forbidden operations

- generating the mesh as a naive UV grid on a target surface;
- any lath curved tighter than the declared minimum bending radius;
- a quadrilateral mesh with no shear layer;
- rigid nodes on an elastically formed shell;
- treating laths as independent straight segments between nodes;
- a boundary with no edge beam and no thrust resolution;
- letting a score dimension change the bending radius, lath section, or shear strategy;
- reporting a node count without reporting unique node types and unique lath lengths.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | rise-to-span, primary versus secondary shell lobes |
| Repetition | mesh module — the dominant visual channel |
| Variation | bounded module change between declared zones |
| Density | mesh module, lath layer count, diagonal presence |
| Continuity | how far each lath runs before a scarf joint |
| Interruption | openings in the mesh, a lobe boundary, a skylight ring |
| Polyphony | two lath families plus the diagonal layer as three woven voices |
| Tension / Release | rise-to-span inside the legal band; interior volume change |
| Tempo of Change | frequency of module change along a lath direction |

## Program negotiation

| Program condition | Gridshell-specific response |
|---|---|
| single large hall, workshop, market | the native fit |
| subdivided rooms | poor fit; the gridshell becomes a roof over separate structure |
| controlled daylight | the mesh is a diffuser by default; blackout requires a liner |
| acoustic control | the open lattice reads well acoustically but provides no isolation |
| fire and egress | exposed slender timber has limited char reserve; check occupancy early |
| facade | the boundary is the elevation; the edge beam is the architectural datum |

## Grasshopper / Rhino modelling guideline

1. Declare the construction route before anything else.
2. Generate a target surface, then relax a compass or geodesic mesh onto it holding lath
   spacing constant.
3. Extract node positions as the registration lattice.
4. Build laths as splines through node rows and columns, not as per-cell segments.
5. Run the bending radius check on every lath and stop if it fails.
6. Add the declared shear layer and verify that every cell is braced.
7. Generate node elements, classify them into unique types, and record rotation allowance.
8. Generate the edge beam along the boundary row and resolve thrust with ties or
   abutments.
9. Report unique lath lengths, unique node types, and scarf joint positions.
10. Bake lath families, diagonals, nodes, edge beam, cladding, and supports separately.

## Typology notes

- **Library:** a gridshell over a single reading hall, with the collection housed in a
  conventional structure — the same pairing logic as the concrete shell.
- **Theater:** good for a foyer or a seasonal venue; the auditorium needs isolation.
- **Museum:** good for a circulation hall or courtyard cover; poor for controlled galleries.

## Validation

- the construction route is declared and every rule matches it;
- every lath passes the minimum bending radius check;
- every mesh cell is covered by the declared shear layer;
- node types are classified and unique-type count is reported;
- lath continuity and scarf joint positions are modelled;
- the boundary has an edge beam and a resolved thrust path;
- cladding panels satisfy planarity or are flagged;
- re-running the relaxation with identical inputs reproduces the node mesh within
  tolerance.

## Limitations

No bending stress, buckling, or node slip analysis; no green-timber creep or moisture
behaviour; no forming-sequence simulation; no connection design. The bending radius rule
here is a proportional heuristic that must be replaced by species- and grade-specific
data. Every element remains `professional_review_required`.
