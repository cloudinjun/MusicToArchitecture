# 10 — Steel Space Frame and Gridshell System

- `system_id`: `STR-SYS-STEEL-SPACE-FRAME-SHELL`
- `tectonic_family`: `shell`
- `material_system`: `structural_steel_network`

## Scope and research basis

A steel network shell replaces both the continuous surface of guide 08 and the elastic
laths of guide 09 with **straight members meeting at manufactured nodes**. Nothing bends;
curvature is approximated by faceting. That single fact reorganises the whole design
problem around two countable quantities: the number of *unique* nodes and the number of
*unique* panels. A geometry that produces 4 000 different node angles is not buildable;
a geometry that produces 40 node types is. The system therefore makes rationalisation —
not form — the design act.

Canonical references:

1. Foster + Partners with Buro Happold, **Great Court roof, British Museum**, 2000 — a
   single-layer steel gridshell over an irregular plan, with every panel a unique
   triangle.
2. Grimshaw with Anthony Hunt Associates, **Eden Project**, 2001 — hex-dominant
   double-layer space frames clad in ETFE cushions, chosen because planarity ceases to
   matter with pneumatic panels.
3. Foster + Partners, **Reichstag cupola**, 1999 — a single-layer steel network with
   glazed panels and an occupied ramp inside the shell.
4. Mero and Triodetic proprietary node systems — the industrial basis for double-layer
   space frames as a catalogue product.

Primary sources:

- [AISC ANSI/AISC 360, Specification for Structural Steel Buildings](https://www.aisc.org/aisc/publications/current-standards/aisc-360/)
- [IASS, International Association for Shell and Spatial Structures](https://iass-structures.org/)
- [ASCE/SEI 7-22, Minimum Design Loads and Associated Criteria](https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22)
- [ICC 2024 IBC Chapter 6, Types of Construction](https://codes.iccsafe.org/content/IBC2024V2.0/chapter-6-types-of-construction)

## Structural thesis

Straight struts join at nodes to approximate a curved surface. A **single-layer** network
carries load by membrane action like a shell and is governed by node stiffness and
snap-through buckling. A **double-layer** space frame adds a second offset layer and web
diagonals, becoming a three-dimensional truss that is far stiffer, far deeper, and far
more member-heavy. The choice between them is the first decision and changes everything
downstream.

Mesh topology is the second decision. Triangular meshes are structurally stiff and
automatically planar per panel but produce six members per node. Quadrilateral and
hexagonal meshes give fewer, cleaner members but are not planar in general and need
either a planarisation step or a non-planar cladding technology.

## Invariants

- `SSF-INV-01` — the layer configuration is declared: single-layer network or
  double-layer space frame. Rules, depths, and node types differ completely.
- `SSF-INV-02` — the mesh topology is declared (triangular, quad, hex, or geodesic) and
  the panel planarity consequence is stated and checked.
- `SSF-INV-03` — every node is a modelled element with a type, an incoming member count,
  and an angle set; unique node type count is a reported metric.
- `SSF-INV-04` — every member is straight between two nodes; a curved member belongs to
  guide 09.
- `SSF-INV-05` — the boundary collects thrust into a modelled ring, edge truss, or
  continuous support with published reactions.
- `SSF-INV-06` — for single-layer networks, node rotational stiffness and a snap-through
  buckling state are recorded, even if `unresolved`.

## Element taxonomy

| Kind | Primitive | Form | Starting range | Located by |
|---|---|---|---|---|
| `node` | box | ball, plate, or cast node | Ø 0.10–0.40 m | every mesh vertex |
| `strut_top` | member | CHS or box | Ø 0.10–0.30 m | mesh edges, upper layer |
| `strut_bottom` | member | CHS | Ø 0.10–0.25 m | offset layer, double-layer only |
| `web_diagonal` | member | CHS | Ø 0.08–0.20 m | between layers, double-layer only |
| `edge_ring` | member ×N | closed CHS or box | Ø 0.4–1.2 m | shell boundary |
| `edge_truss` | member ×N | chords + web | depth ≈ span/15 | irregular boundaries |
| `cladding_panel` | quad | glass, ETFE cushion, metal | ≤ 2.0 m edge | mesh face, planarity checked |
| `panel_bracket` | box | articulated fitting | 0.05–0.20 m | node or member attachment |
| `gutter` · `valley_member` | member | box section with drainage | — | mesh valleys |
| `bearing` | box | pinned, sliding, or fixed shoe | 0.2–0.6 m | every boundary node |
| `tie` | member | rod or strand | Ø 30–90 mm | thrust resolution at springing |
| `abutment` · `footing` | extrusion | mass or piled | 1.5–4.0 m | boundary support line |
| `layer_offset` | metadata | depth law | 0.8–2.5 m | double-layer only |

## Geometry primitives required

`member` for all struts, `box` for nodes and bearings, `quad` for cladding with a
planarity tolerance, `extrusion` for abutments. Notably this system needs **no new
primitive** — it is the only shell-family system that fits inside the four primitives of
decision 0008. That is a genuine argument in its favour for a first implementation.

## Datum chain specialisation

```text
DATUMS   layer_config, mesh_topology, target_surface, mesh_module,
         layer_offset_depth, planarity_tolerance, boundary_type
   ↓
MESHING   generate + relax the mesh on the target surface; planarise if required
   ↓
LATTICE  node[n] with an adjacency list  (a graph, not a two-index grid)
   ↓
ELEMENTS struts from mesh edges; panels from mesh faces; web diagonals from the
         layer pairing; ring or edge truss from the boundary loop
```

Unlike every other system in this library, the lattice is a **general graph** rather than
an indexed array, because an irregular boundary produces an irregular mesh. Element IDs
therefore index node numbers rather than grid coordinates: `SSF-NODE-N01472`,
`SSF-STRUT-N01472-N01489`. Stable node numbering across runs becomes a first-class
requirement — an unstable numbering destroys diffing and mapping reports.

## Legal variables and starting ranges

| Parameter | Starting range | Owner |
|---|---:|---|
| `mesh_module` | 1.2–4.0 m | score (`density`) inside clamp |
| `layer_offset_depth` | span/25–span/15 (double-layer) | tectonic |
| `rise_to_span` | 1 : 4 to 1 : 10 | tectonic; score selects inside |
| span | 15–120 m | program and tectonic |
| mesh topology | triangular / quad / hex | tectonic; score may select |
| panel planarity tolerance | ≤ 1 : 200 of diagonal | fabrication; never score |
| unique node type target | ≤ 60 | fabrication target |
| unique panel type target | ≤ 25 % of panel count | fabrication target |

## Forbidden operations

- a curved strut;
- quad or hex panels on a doubly curved surface with no planarisation step and no
  declared non-planar cladding technology;
- nodes left as geometric intersections instead of elements;
- reporting total node and panel counts without reporting unique-type counts;
- a single-layer network with no node stiffness or buckling state recorded;
- mixing single-layer and double-layer rules on one surface without a declared transition;
- letting a score dimension change layer depth, planarity tolerance, or strut diameter;
- unstable node numbering between runs.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | rise-to-span, layer depth, primary ring prominence |
| Repetition | mesh module regularity — the dominant visual channel |
| Variation | bounded module gradient across the surface |
| Density | mesh module, topology choice, layer count |
| Continuity | whether member lines run as readable great circles or as a random web |
| Interruption | oculus, skylight ring, a boundary lobe |
| Polyphony | top layer, bottom layer, and web diagonals as three voices |
| Tension / Release | rise-to-span inside the legal band; interior volume change |
| Tempo of Change | rate of module gradient along the principal surface direction |

## Program negotiation

| Program condition | Network-shell-specific response |
|---|---|
| courtyard, atrium, hall roof | the native fit; the classic institutional application |
| conditioned interior below | the network is a roof; the enclosure is glazing or ETFE |
| light-sensitive gallery | transparency conflicts with collection care; declare shading or a liner |
| acoustic control | an open network gives none; declare a separate acoustic strategy |
| snow, drainage | valleys need gutter members; plan them into the mesh, not after it |
| maintenance access | member spacing and node design must accommodate access and cleaning |

## Grasshopper / Rhino modelling guideline

1. Declare layer configuration and mesh topology before generating anything.
2. Generate the target surface, then mesh and relax it toward a constant module.
3. Planarise if the topology requires it, and report the residual planarity deviation.
4. Freeze the node graph with a stable numbering and publish it as the lattice.
5. Generate struts from mesh edges and, for double-layer, offset a second layer and
   generate web diagonals from the layer pairing.
6. Classify nodes by incoming member count and angle set; report unique types.
7. Generate cladding panels from mesh faces and run the planarity check.
8. Build the boundary ring or edge truss, bearings, and thrust resolution; publish
   reactions.
9. Report node schedule, strut schedule with unique lengths, and panel schedule.
10. Bake layers, nodes, cladding, boundary, and supports separately.

## Typology notes

- **Library:** a network roof over a central court, with the collection in a conventional
  structure — the Great Court pattern applied at a smaller scale.
- **Theater:** good for the public volume and the foyer; the auditorium needs mass and
  isolation.
- **Museum:** the strongest institutional fit of the three shell systems, because a glazed
  court between solid gallery blocks is a well-tested museum diagram.

## Validation

- layer configuration and mesh topology are declared and consistently applied;
- every strut is straight and terminates on two node elements;
- unique node type count and unique panel type count are both reported and inside target;
- every panel satisfies planarity or is declared non-planar with a technology;
- the boundary has a ring or edge truss with published reactions and resolved thrust;
- single-layer networks record node stiffness and a buckling state;
- node numbering is stable across runs with identical inputs;
- regenerating from identical datums reproduces the node graph within tolerance.

## Limitations

No member or node capacity, no snap-through or global buckling analysis, no connection
design, no glazing stress or cold-bending verification, no erection or pre-camber study.
Unique-type targets here are workshop heuristics, not procurement data. Every element
remains `professional_review_required`.
