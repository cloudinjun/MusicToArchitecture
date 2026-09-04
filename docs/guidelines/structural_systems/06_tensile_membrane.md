# 06 — Tensile Membrane System

- `system_id`: `STR-SYS-TENSILE-MEMBRANE`
- `tectonic_family`: `tensile`
- `material_system`: `tensile_membrane`

## Scope and research basis

A tensile membrane has no free geometry. Its shape is the **equilibrium result** of
boundary positions, prestress, and load — you do not draw it, you solve it. Every other
system in this library lets the designer place geometry and then check it; this one
inverts the order, and that inversion is the whole reason it belongs in the shortlist.
It is also the system that most directly rewards the score's tension and release
vocabulary, and the one most likely to produce dishonest work if form finding is faked.

Canonical references:

1. Frei Otto and Rolf Gutbrod, **German Pavilion, Expo 67**, Montreal — the prototype for
   large-scale physically form-found tension surfaces.
2. Frei Otto with Behnisch & Partner, **Munich Olympiapark**, 1972 — form finding taken
   to urban scale (see also guide 07: the roof is a cable net with panels).
3. SOM, **Hajj Terminal**, Jeddah, 1981 — 210 fabric cones on a repeated module, showing
   that a membrane system can be a rigorous kit of parts.
4. Fentress Bradburn with Severud, **Denver International Airport**, 1995 — a repeated
   peaked-mast membrane bay carrying a regional image.

Primary sources:

- [ASCE/SEI 55-16, Tensile Membrane Structures](https://sp360.asce.org/personifyebusiness/Merchandise/Product-Details/productId/233135208)
- [ASCE/SEI 7-22, Minimum Design Loads and Associated Criteria](https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22)
- [IASS, International Association for Shell and Spatial Structures](https://iass-structures.org/)
- [ASCE Structural Engineering Institute standards committees](https://www.asce.org/communities/institutes-and-technical-groups/structural-engineering-institute/committees)

## Structural thesis

A doubly curved, anticlastic membrane carries load in tension only. Its curvature in two
opposing directions is what makes it stable under both downward load and wind uplift.
The membrane terminates on cables, and cables terminate on masts, arches, rings, or a
boundary frame, which in turn terminate on anchors and foundations. Prestress is a
design variable, not a detail. Compression and bending live only in the boundary system.

## Invariants

- `TM-INV-01` — the membrane surface is produced by a declared form-finding method (force
  density, dynamic relaxation, or physical analogue), with the method, prestress ratio,
  and convergence tolerance recorded. Extrusion, lofting, or draping a drawn surface
  fails outright.
- `TM-INV-02` — the surface maintains anticlastic double curvature, or a named alternative
  stability strategy (pneumatic, ballasted, mechanically stiffened) is declared.
- `TM-INV-03` — every boundary is a modelled element: edge cable, ridge cable, valley
  cable, clamped line, or rigid boundary member. A free membrane edge does not exist.
- `TM-INV-04` — reactions are computed and published at every mast head, ring, and anchor.
  A membrane without reactions is a rendering.
- `TM-INV-05` — the compression and bending system (masts, arches, rings, frame) is
  modelled as a separate element family with its own load path to foundation.
- `TM-INV-06` — enclosure, acoustics, thermal control, fire, and drainage are routed to a
  declared secondary system whenever the membrane alone cannot satisfy the program.

## Element taxonomy

| Kind | Primitive | Form | Starting range | Located by |
|---|---|---|---|---|
| `membrane_patch` | **mesh_surface** | form-found anticlastic surface | 200–2 000 m² per patch | boundary set + prestress solve |
| `edge_cable` | member | spiral strand, catenary | Ø 20–60 mm | patch boundary, free edges |
| `ridge_cable` | member | spiral strand | Ø 24–70 mm | high line between mast heads |
| `valley_cable` | member | spiral strand | Ø 24–70 mm | low line between anchors |
| `mast` | member | CHS, tapered | Ø 0.4–1.2 m, h 8–40 m | declared high points |
| `compression_ring` | member ×N | closed CHS polygon | Ø 0.5–1.5 m | ring-and-cable configurations |
| `boundary_arch` | member ×N | CHS or box arch | depth ≈ span/50 | rigid boundary configurations |
| `guy_cable` | member | spiral strand | Ø 20–50 mm | mast head to ground anchor |
| `tie_down` | member | rod or cable | Ø 16–40 mm | low points to anchor |
| `clamp_plate` · `keder_rail` | box | aluminium extrusion | 0.1–0.3 m | every membrane boundary line |
| `corner_plate` | box | steel fabrication | 0.4–1.2 m | cable and membrane junctions |
| `anchor_block` | extrusion | mass or piled foundation | 1.5–6.0 m | every cable and mast base |
| `cutting_pattern` | metadata | flattened strip set | width ≤ 2.0–3.2 m | derived from the found surface |
| `drainage_path` | metadata | polyline on surface | — | valleys and low points |

## Geometry primitives required

This system requires a **fifth primitive that decision 0008 does not yet define**:

```python
class MeshSurfaceGeometry(BaseModel):
    type: Literal['mesh_surface']
    vertices: list[Vector3Value]
    faces: list[tuple[int, ...]]
    form_finding_method: Literal['force_density', 'dynamic_relaxation', 'physical']
    prestress_warp: float
    prestress_weft: float
    convergence_tolerance: float
```

`member` carries every cable and every compression element. `box` carries clamps and
plates. `extrusion` carries anchor blocks. Selecting this system therefore extends the
primitive contract, and that extension must be recorded as a schema change, not smuggled
in as a mesh export.

## Datum chain specialisation

The level table does not exist here. The lattice is a **boundary and prestress datum**.

```text
DATUMS   boundary_polyline_set, high_point_set, low_point_set,
         prestress_ratio (warp : weft), mast_height, curvature_target
   ↓
FORM FINDING   solve equilibrium -> membrane_patch vertices
   ↓
LATTICE  found surface + its boundary curves + node set
   ↓
ELEMENTS cables from boundary curves; masts from high points; anchors from
         low points and cable ends; cutting pattern from the found surface
```

Geometry is *downstream of a solve*. This is the single biggest workflow difference in
the library, and it means the pipeline needs a solver stage between the datum stage and
the element stage. Grasshopper's Kangaroo or an equivalent must sit inside the accepted
route, not beside it.

## Legal variables and starting ranges

| Parameter | Starting range | Owner |
|---|---:|---|
| prestress ratio warp : weft | 1 : 1 to 2 : 1 | tectonic; score selects inside |
| membrane prestress level | 2–6 kN/m | tectonic; never score |
| mast height | 8–40 m | score (`hierarchy`) inside clamp |
| curvature (rise / span) | 1 : 8 to 1 : 12 minimum | tectonic; never score |
| bay module (repeated cones) | 15–45 m | score (`repetition`) |
| patch count | 1–40 | score (`density`) |
| cutting pattern strip width | ≤ 2.0–3.2 m | fabrication; never score |
| edge cable sag ratio | 1 : 8 to 1 : 14 of chord | tectonic |

## Forbidden operations

- producing the surface by extrusion, loft, subdivision smoothing, or sculpting;
- a synclastic or flat membrane region with no declared alternative stability strategy;
- a membrane edge with no cable or clamped boundary;
- publishing geometry without mast, ring, and anchor reactions;
- letting a score dimension change prestress, curvature ratio, or cable diameter;
- ignoring ponding: every low point needs a drainage path;
- claiming enclosure performance (acoustic, thermal, fire) that a single membrane layer
  cannot deliver.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | mast height distribution, primary versus secondary high points |
| Repetition | bay module of repeated cones or arches |
| Variation | bounded high-point height family change across bays |
| Density | patch count, cable family count per patch |
| Continuity | whether ridge cables run continuously across bays |
| Interruption | a missing bay, a rigid infill bay, an open courtyard |
| Polyphony | membrane, cable net, and mast system as three readable voices |
| Tension / Release | prestress ratio selection inside the legal band; rise-to-span |
| Tempo of Change | frequency of high-point height change along the long axis |

Note that `tension_release` maps here more directly than in any other system — and that
this is exactly why it must be clamped hardest.

## Program negotiation

| Program condition | Membrane-specific response |
|---|---|
| any enclosed conditioned room | declare a secondary enclosure system; the membrane is a roof |
| auditorium, acoustically controlled | membrane alone fails; a separate acoustic envelope is required |
| gallery, light-sensitive collection | membrane translucency is usually incompatible; declare a liner |
| public circulation, entry | the strongest fit: covered open space under a found surface |
| snow, rain, ponding regions | valleys and low points drive the form before architecture does |
| fire and egress | membrane material class and smoke behaviour govern occupancy |

## Grasshopper / Rhino modelling guideline

1. Author the boundary polylines, high points, and low points as an explicit datum set.
2. Run form finding with a recorded method, prestress, and convergence tolerance.
3. Freeze the found surface as the accepted geometry; downstream steps read it, never
   edit it.
4. Extract boundary curves and generate cable elements from them.
5. Generate masts, rings, or arches from the high-point set, with guy and tie-down cables.
6. Compute and publish reactions at every mast, ring, and anchor node.
7. Generate the cutting pattern by flattening the found surface into strips; report the
   strip count, maximum width, and compensation assumption as unresolved.
8. Diagram the drainage path on the surface and check every low point.
9. Bake membrane, cable families, compression system, anchors, and pattern to separate
   layers.

## Typology notes

- **Library:** poor fit for the collection and reading core; strong fit for an entry
  canopy, courtyard, or event terrace attached to a conventional building.
- **Theater:** strong fit for an outdoor or seasonal venue; poor fit for a controlled
  auditorium.
- **Museum:** poor fit for galleries; strong fit for a covered forecourt or an outdoor
  sculpture court.

An honest reading is that this system usually pairs with a second system rather than
carrying a whole institutional program. Declaring that pairing is part of the selection.

## Validation

- the form-finding method, prestress, and convergence tolerance are recorded;
- the surface is anticlastic everywhere, or every exception is declared;
- every membrane boundary resolves to a cable or a clamped rigid boundary;
- reactions exist at every mast, ring, and anchor, and every anchor reaches a foundation;
- every low point has a drainage path and a ponding note;
- wind uplift and reversal cases are named, even if not yet solved;
- cutting pattern strip widths are inside the fabrication limit or flagged;
- re-running form finding with identical inputs reproduces the surface within tolerance.

## Limitations

No membrane stress analysis, no cable force solution, no wrinkling or slack check, no
patterning compensation, no wind tunnel or dynamic behaviour. Form finding here produces
a geometrically plausible equilibrium shape, not a verified structure. Every element
remains `professional_review_required`, and this system in particular must never present
a rendered surface as engineering.
