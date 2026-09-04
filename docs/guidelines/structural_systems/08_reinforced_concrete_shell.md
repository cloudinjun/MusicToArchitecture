# 08 — Reinforced Concrete Shell System

- `system_id`: `STR-SYS-RC-SHELL`
- `tectonic_family`: `shell`
- `material_system`: `reinforced_concrete_shell`

## Scope and research basis

A concrete shell carries load by **membrane action in a curved continuous surface**: a
thin plate that is stiff only because it is curved. The classic shells are extraordinarily
thin — 40 to 60 mm over spans of 30 m and more — and that ratio is the whole point. The
architectural consequence is that form, structure, and enclosure are one object, and the
governing constraints are curvature, boundary conditions, buckling, and formwork, not
member sizing.

Canonical references:

1. Félix Candela, **Los Manantiales restaurant**, Xochimilco, 1958 — intersecting
   hyperbolic paraboloids in a shell of roughly 40 mm thickness.
2. Pier Luigi Nervi and Annibale Vitellozzi, **Palazzetto dello Sport**, Rome, 1957 — a
   ribbed dome of prefabricated ferrocement units on Y-shaped buttresses.
3. Eduardo Torroja, **Zarzuela Hippodrome**, Madrid, 1935 — cantilevered hyperboloid
   canopy shells at extreme thinness.
4. Heinz Isler, **Swiss shell roofs**, 1955–2000 — hanging-model form finding as the
   generator of compression-only shapes.

Primary sources:

- [ACI 318 Building Code Portal](https://www.concrete.org/topicsinconcrete/318buildingcodeportal.aspx)
- [ACI Committee 334, Concrete Shell Design and Construction](https://www.concrete.org/committees/directoryofcommittees.aspx)
- [IASS, International Association for Shell and Spatial Structures](https://iass-structures.org/)
- [ASCE/SEI 7-22, Minimum Design Loads and Associated Criteria](https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22)

## Structural thesis

A doubly curved continuous surface carries load predominantly in-plane. Bending appears
only near boundaries, supports, and openings, which is exactly where the shell needs
local thickening, edge beams, or ring stiffeners. The two governing failures are
**buckling** (the shell is too thin or too flat) and **boundary incompatibility** (the
edge is restrained in a way the membrane state cannot accept). Formwork is not a
construction afterthought; it decides whether the geometry is buildable at all.

## Invariants

- `RCS-INV-01` — the surface geometry comes from a declared generator: a ruled family
  (hypar, conoid), a surface of revolution, a hanging-model or thrust-network form
  finding, or a stated free-form with a curvature audit. A sculpted surface with no
  generator fails.
- `RCS-INV-02` — Gaussian curvature is non-zero over the load-carrying area, or a named
  stiffening strategy (ribs, folds, corrugation) is declared for the flat regions.
- `RCS-INV-03` — every boundary is a modelled element: edge beam, ring, valley, free edge
  with stiffener, or continuous support.
- `RCS-INV-04` — every opening has a reinforced edge and triggers a new stability check;
  an opening never simply subtracts from the surface.
- `RCS-INV-05` — a buckling and thickness-to-radius state is recorded for every shell
  region, even when the value is `unresolved`.
- `RCS-INV-06` — the formwork strategy is declared (reusable ruled formwork, inflated,
  earth-form, segmented precast) and the segmentation is modelled.

## Element taxonomy

| Kind | Primitive | Form | Starting range | Located by |
|---|---|---|---|---|
| `shell_surface` | **mesh_surface** | continuous doubly curved plate | t 0.04–0.12 m | generator + boundary datum |
| `shell_thickening` | mesh_surface | local variable-thickness zone | t up to 0.30 m | boundary and support regions |
| `edge_beam` | member | rectangular or tapered | depth ≈ span/40 | free shell edges |
| `boundary_ring` | member ×N | closed curved member | Ø or box 0.4–1.2 m | dome and vault perimeters |
| `valley_stiffener` | member | rectangular rib | 0.2 × 0.5 m | intersection lines between shells |
| `rib` | member | curved rectangular | 0.10 × 0.30–0.60 m | ribbed-shell variant |
| `fold_line` | metadata | crease geometry | — | folded-plate variant |
| `opening_edge_ring` | member ×N | closed curved member | 0.2 × 0.4 m | every opening boundary |
| `tie` | member | rod or post-tensioned cable | Ø 25–60 mm | thrust resolution at springing |
| `abutment` · `buttress` | extrusion | mass concrete | 1.5–5.0 m | every support line |
| `support_line` | metadata | continuous or point set | — | shell springing |
| `formwork_segment` | metadata | reusable unit | ≤ 6 × 12 m typical | surface segmentation |
| `footing` | extrusion | spread or piled | 2.0–6.0 m | abutment base |

## Geometry primitives required

Like guide 06, this system needs the `mesh_surface` primitive that decision 0008 does not
define, and additionally needs **variable thickness** on that surface. `member` carries
edges, rings, ribs, and ties. `extrusion` carries abutments and footings. `box` and
`quad` are barely used. This is the primitive profile furthest from the current schema.

## Datum chain specialisation

```text
DATUMS   surface_generator, span, rise_to_span, thickness_law,
         boundary_type_set, opening_set, support_line_set, formwork_strategy
   ↓
GENERATION   ruled family / revolution / form finding -> shell_surface
   ↓
LATTICE  surface + its boundary curves + the isocurve or thrust network
   ↓
ELEMENTS edges and rings from boundary curves; ribs from the isocurve family;
         opening rings from the opening set; abutments from support lines
```

The lattice is the **surface's own curve network** — parameter isocurves, principal
curvature lines, or a thrust network — rather than a table of levels. Element IDs
therefore index into surface parameters: `SHL-RIB-U012`, `SHL-EDGE-V003`. Recording which
curve network was chosen is as important as recording the surface, because it decides
where ribs, formwork joints, and reinforcement directions go.

## Legal variables and starting ranges

| Parameter | Starting range | Owner |
|---|---:|---|
| `rise_to_span` | 1 : 5 to 1 : 10 | tectonic; never score |
| shell thickness | 0.04–0.12 m over 15–40 m span | tectonic; never score |
| thickness-to-radius ratio | ≥ 1 : 500 as a review trigger | tectonic; never score |
| `span` | 12–45 m | program and tectonic |
| shell unit count (repeated bays) | 1–24 | score (`repetition`) |
| rib spacing | 1.2–3.0 m | score (`density`) inside clamp |
| opening area share | ≤ 15 % of a shell unit | tectonic; score selects inside |
| edge beam depth ratio | span/35–span/50 | tectonic |

## Forbidden operations

- generating the surface by sculpting or subdivision smoothing without a declared
  generator and a curvature audit;
- a flat or near-flat region carrying load with no stiffening strategy;
- an opening subtracted from the surface with no reinforced edge and no new stability
  check;
- a free shell edge with no edge beam or stiffener;
- letting a score dimension set thickness, rise-to-span, or edge beam depth;
- omitting the thrust resolution at springing — a shell that pushes into nothing;
- calling curved massing a shell when no structural surface has been solved.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | primary shell unit versus secondary shells; abutment prominence |
| Repetition | number and rhythm of repeated shell units |
| Variation | bounded rise or span family change between units |
| Density | rib spacing, unit count per plan area |
| Continuity | whether adjacent shells merge at valleys or stand separate |
| Interruption | skylight openings, a missing unit, an open valley |
| Polyphony | shell surface and rib network as two readable orders |
| Tension / Release | rise-to-span selection inside the legal band; interior height change |
| Tempo of Change | frequency of unit-geometry change along the plan axis |

Note that most of this system's expressive channels are *counts and rhythms of whole
units*, not continuous deformations. That is the honest reading: the score composes
shells, it does not shape them.

## Program negotiation

| Program condition | Shell-specific response |
|---|---|
| large single volume, hall, market | the native fit; shell span sets the room |
| subdivided program, offices, stacks | poor fit; the shell becomes a roof over a separate structure |
| gallery, controlled light | openings are structurally expensive; plan them with the generator |
| acoustic control | concave surfaces focus sound; declare an acoustic treatment early |
| services and plant | there is no ceiling void; routing must be planned into the section |
| facade | the shell often *is* the facade; the boundary condition is the elevation |

## Grasshopper / Rhino modelling guideline

1. Choose and record the surface generator before drawing anything.
2. Generate the shell surface from span, rise-to-span, and the boundary datum.
3. Select and record the curve network (isocurves, principal curvature, thrust network).
4. Extract boundary curves and generate edge beams, rings, and valley stiffeners.
5. Place openings from the opening set and generate a reinforced edge ring for each.
6. Apply the thickness law as surface attributes and mark the thickening zones.
7. Resolve thrust at every springing with ties, buttresses, or a continuous support.
8. Segment the surface into formwork units and report the count of unique units.
9. Bake surface, edges, ribs, openings, abutments, and formwork segments separately.

## Typology notes

- **Library:** a shell over a single great reading room, with stacks and service in a
  conventional structure beneath or beside it.
- **Theater:** strong for the auditorium volume; the fly tower and the acoustic
  requirements are the hard constraints.
- **Museum:** strong for a single top-lit gallery hall; poor for a sequence of controlled
  rooms.

## Validation

- the generator, curve network, and formwork strategy are all recorded;
- Gaussian curvature is non-zero over load-carrying area or a stiffening strategy exists;
- every boundary resolves to an edge beam, ring, valley, or continuous support;
- every opening has a reinforced edge and a recorded new stability state;
- thickness-to-radius and rise-to-span stay inside the declared bands or are flagged;
- thrust is resolved at every springing with a named element;
- unique formwork unit count is reported alongside total segment count;
- regenerating from identical datums reproduces the surface within tolerance.

## Limitations

No membrane or bending analysis, no buckling calculation, no reinforcement design, no
creep or shrinkage, no construction-sequence or formwork-loading check. Thickness values
here are historical precedent, not results. This system in particular can produce
beautiful images that are structurally meaningless; every element remains
`professional_review_required` and no run may present a shell as verified.
