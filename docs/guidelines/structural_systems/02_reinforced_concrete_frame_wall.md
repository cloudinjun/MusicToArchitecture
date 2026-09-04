# 02 — Reinforced Concrete Frame and Wall System

- `system_id`: `STR-SYS-RC-FRAME-WALL`
- `tectonic_family`: `frame`
- `material_system`: `reinforced_concrete`

## Scope and research basis

Reinforced concrete inverts the steel frame's logic: the **surface is the structure**.
Slabs, walls, and cores are continuous monolithic plates, and the discrete members
(columns, bands, drops) are local thickenings of that continuity. The architectural
consequence is that plan freedom is high but vertical continuity is expensive — a
column that does not stack costs a transfer element, and an opening near a column costs
a punching-shear repair.

Canonical references:

1. Le Corbusier, **Maison Dom-Ino**, 1914 — the slab-and-column diagram that defines the
   free plan and the free facade.
2. Pier Luigi Nervi, **Gatti Wool Factory**, Rome, 1953 — floor ribs follow the isostatic
   lines of the slab, making force visible as pattern.
3. Louis Kahn, **Salk Institute**, La Jolla, 1965 — full-storey Vierendeel floor trusses
   turn the structural depth into occupiable service space.
4. Tadao Ando, **Church of the Light**, 1989 — the wall is simultaneously structure,
   envelope, and the entire architectural argument.

Primary sources:

- [ACI 318 Building Code Portal](https://www.concrete.org/topicsinconcrete/318buildingcodeportal.aspx)
- [ASCE/SEI 7-22, Minimum Design Loads and Associated Criteria](https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22)
- [ICC 2024 IBC Chapter 6, Types of Construction](https://codes.iccsafe.org/content/IBC2024V2.0/chapter-6-types-of-construction)
- [PCI, Precast/Prestressed Concrete Institute resources](https://www.pci.org/)

## Structural thesis

A vertical system of columns and walls supports continuous horizontal plates. The
designer chooses one explicit slab behaviour — flat plate, flat slab with drops, one-way
beam-slab, two-way beam-slab, or waffle — and that choice sets span limits, depth,
column layout tolerance, and opening rules for the whole project. Lateral load goes to
walls or cores, not to the frame, unless a moment frame is explicitly declared.

## Invariants

- `RCF-INV-01` — one named slab behaviour is selected per level and recorded; mixed
  behaviours require a declared boundary and a transfer condition.
- `RCF-INV-02` — columns and walls stack across levels; every offset is resolved by a
  named transfer beam, transfer wall, or transfer slab band.
- `RCF-INV-03` — every column and every concentrated reaction carries a punching-shear
  review zone; openings inside that zone are a hard conflict until repaired.
- `RCF-INV-04` — the lateral system is walls or cores by default; declaring a moment
  frame requires modelling the joint region.
- `RCF-INV-05` — slab thickness derives from the selected behaviour and span, not from a
  score dimension.
- `RCF-INV-06` — walls and cores are modelled as extruded closed profiles with openings,
  never as a stack of boxes.

## Element taxonomy

| Kind | Primitive | Section / form | Starting range | Located by |
|---|---|---|---|---|
| `column` | member | rectangular or circular | 0.35–0.70 m | grid node `(i,j,k)→(i,j,k+1)` |
| `shear_wall` | extrusion | closed profile + openings | t 0.20–0.40 m | declared wall lines per level |
| `core_wall` | extrusion | closed profile + door openings | t 0.25–0.45 m | fixed plan position, all levels |
| `flat_slab` | extrusion | plate + holes | t ≈ span/30 (0.20–0.35 m) | plate polygon per level |
| `drop_panel` | box | local thickening | 1.5–2.5 × column, +0.10 m | column head |
| `column_capital` | member | flared head | 1.0–1.8 × column | column head, optional |
| `slab_band` | box | wide shallow beam | 0.9–2.4 m wide | between column lines |
| `beam` | member | rectangular or T | depth ≈ span/12 | beam-slab behaviour only |
| `waffle_rib` | member ×2 families | orthogonal rib grid | 0.10–0.15 m wide @ 0.7–1.2 m | waffle behaviour only |
| `edge_beam` · `upturn` | member | rectangular | 0.3 × 0.6 m | plate boundary polyline |
| `transfer_beam` | member | deep rectangular | depth ≈ span/8 | under discontinuous column |
| `punching_zone` | metadata | review disc | 2 d from column face | every column head |
| `pile_cap` · `spread_footing` | box | pad | 1.5–3.0 m | column and wall base |
| `movement_joint` | metadata | line | 30–45 m spacing | plate subdivision |

## Geometry primitives required

`extrusion` dominates — slabs, walls, and cores are all closed polygons with holes. This
is the system that most exposes the current schema gap, because a box-only pipeline
cannot express a wall with a door or a slab with an atrium. `member` carries columns,
beams, and ribs. `box` carries drops and footings.

## Datum chain specialisation

```text
DATUMS   slab_behaviour, bay_x, bay_y, floor_to_floor, slab_span_ratio,
         wall_line_set, void_count, movement_joint_spacing
   ↓
LATTICE  level_table[k] × x_lines[i] × y_lines[j] × wall_lines[w]
   ↓
ELEMENTS columns from grid nodes; walls from wall lines; slabs from plate polygons
         minus void polygons; drops and punching zones from column heads
```

A second lattice axis exists that steel does not have: the **wall-line set**. Walls are
located by continuous vertical planes, not by point nodes, and they must be checked for
continuity as planes across levels.

## Legal variables and starting ranges

| Parameter | Starting range | Owner |
|---|---:|---|
| `bay_x`, `bay_y` | 6.0–9.0 m (flat plate 6.0–8.0 m) | score (`density`) inside clamp |
| slab thickness ratio | span/28–span/33 flat plate; span/36 with drops | tectonic; never score |
| `floor_to_floor` | 3.6–4.8 m | score (`tension_release`) |
| wall thickness | 0.20–0.40 m | tectonic |
| `void_count` | 0–3 | score (`interruption`) |
| cantilever | 0–0.30 × adjacent span | score (`continuity`) inside clamp |
| `waffle_rib` spacing | 0.7–1.2 m | score (`repetition`) inside clamp |
| movement joint spacing | 30–45 m | tectonic; never score |

## Forbidden operations

- moving a column off the stack to improve a plan without generating a transfer element;
- punching an opening inside a punching-shear review zone;
- deriving slab thickness from a score dimension;
- modelling a core as a stack of solid boxes with no door openings;
- using flat-plate spans at flat-slab dimensions because the plan looked cleaner;
- omitting movement joints on a plate longer than the declared spacing;
- treating a "concrete look" as this system without slab behaviour, wall lines, and
  punching zones.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | wall vs column ratio, core prominence, transfer level position |
| Repetition | column grid regularity, waffle rib cadence |
| Variation | bounded bay-width family change; drop-panel presence per zone |
| Density | bay span, rib spacing, wall line count |
| Continuity | cantilever depth, slab edge continuity, movement joint rhythm |
| Interruption | atrium voids, wall breaks, opening clusters |
| Polyphony | wall system and column system read as two distinct orders |
| Tension / Release | floor-to-floor, slab edge thickness, upturn vs downturn edges |
| Tempo of Change | frequency of slab-behaviour zone change along a path |

## Program negotiation

| Program condition | Concrete-specific response |
|---|---|
| gallery, reading room | flat plate maximises plan freedom; check deflection and vibration |
| auditorium, long span | leave the system: declare a beam-slab, post-tensioned, or transfer solution |
| stacks, archive, plant | high sustained load favours drops or beam-slab; flat plate often fails |
| acoustic separation | walls are already structure; use it rather than adding partitions |
| wet stacks, risers | penetrations are permanent; coordinate before the slab is committed |
| facade | slab edge is the facade support; upturn vs downturn is an architectural decision |

## Grasshopper / Rhino modelling guideline

1. Select and record slab behaviour before any geometry.
2. Build the level table, grid lines, and wall lines as three separate datum layers.
3. Extrude walls and cores from closed profiles with their openings already subtracted.
4. Generate the slab as a boundary polygon minus void polygons in one operation.
5. Place columns from grid nodes and emit the punching-shear disc as metadata geometry.
6. Add drops, bands, or ribs according to the selected behaviour only.
7. Run the opening-versus-punching-zone conflict check before sweeping any geometry.
8. Bake walls, slabs, columns, and review zones to separate layers.

## Typology notes

- **Library:** heavy stacks loads and the wish for a free plan pull in opposite
  directions; zone the plate rather than thickening it everywhere.
- **Theater:** the concrete box is excellent for acoustic separation; the auditorium roof
  almost always leaves this system.
- **Museum:** thermal mass and blackout are strengths; long clear gallery spans and
  future flexibility are the constraints to test.

## Validation

- one slab behaviour is declared per level and consistent with its thickness;
- every column and wall stacks, or a named transfer element exists with reactions;
- no opening lies inside a punching-shear review zone without a recorded repair;
- every wall and core is a closed profile with declared openings;
- span-to-thickness ratios are inside the declared behaviour range;
- movement joints subdivide every plate longer than the declared spacing;
- identical inputs reproduce identical element IDs and topology.

## Limitations

No reinforcement, no crack control, no creep or long-term deflection, no construction
sequencing or pour breaks, no fire-rating verification. Punching-shear zones here are
geometric review markers, not capacity checks. Every element remains
`professional_review_required`.
