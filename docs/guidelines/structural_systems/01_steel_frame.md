# 01 — Structural Steel Frame System

- `system_id`: `STR-SYS-STEEL-FRAME`
- `tectonic_family`: `frame`
- `material_system`: `structural_steel`

## Scope and research basis

The steel frame separates a discrete skeleton from every other building layer. Load
arrives at a countable set of nodes; floors are lightweight composite decks; lateral
resistance is a declared, isolatable subsystem. Its architectural value is that the
structural decision is visible and separable — a reader can trace one column to one
footing.

Canonical references:

1. Mies van der Rohe, **S. R. Crown Hall**, IIT, 1956 — four exposed plate girders carry
   a column-free interior.
2. SOM (Bruce Graham, Walter Netsch), **Inland Steel Building**, Chicago, 1958 —
   perimeter columns and an external service core free the floor plate.
3. Foster Associates, **Hongkong and Shanghai Bank**, 1985 — suspension trusses convert
   the frame into an explicit hierarchy of primary masts and hung floors.
4. Piano, Rogers and Franchini, **Centre Pompidou**, 1977 — cast gerberettes make the
   transfer between primary trusses and the facade zone a legible component.

Primary sources:

- [AISC ANSI/AISC 360, Specification for Structural Steel Buildings](https://www.aisc.org/aisc/publications/current-standards/aisc-360/)
- [AISC current standards, including the Seismic Provisions](https://www.aisc.org/aisc/publications/current-standards/)
- [ASCE/SEI 7-22, Minimum Design Loads and Associated Criteria](https://www.asce.org/publications-and-news/codes-and-standards/asce-sei-7-22)
- [Steel Joist Institute standard specifications](https://steeljoist.org/specifications/)

## Structural thesis

A regular orthogonal grid of columns supports a two-tier spanning hierarchy (primary
girders, secondary beams or joists) and a thin diaphragm deck. Lateral load is taken by
a small number of named braced or moment bays that stay continuous from roof to
foundation. Everything else is infill.

## Invariants

- `STF-INV-01` — every gravity element reaches a foundation through an explicit chain of
  member end nodes; no floating member.
- `STF-INV-02` — columns align across levels, or a named transfer truss or transfer
  girder resolves the offset and publishes its reactions.
- `STF-INV-03` — the lateral system is a declared continuous set of bays; it is never
  inferred after the fact from whatever members happen to be present.
- `STF-INV-04` — the spanning hierarchy is at least two tiers deep; an "all beams equal"
  frame fails the profile fit check.
- `STF-INV-05` — every member carries a named section from the profile library. A member
  without a section is unresolved geometry, not steel.
- `STF-INV-06` — deck span direction is explicit and consistent with the secondary tier.

## Element taxonomy

Primitives per [decision 0008](../../decisions/0008-element-taxonomy-and-datum-chain.md).

| Kind | Primitive | Section / form | Starting range | Located by |
|---|---|---|---|---|
| `column` | member | W or HSS | W250–W360 family | grid node `(i,j,k)→(i,j,k+1)` |
| `primary_beam` | member | W girder | depth ≈ span/20 | node `(i,j,k)→(i±1,j,k)` |
| `secondary_beam` | member | W | depth ≈ span/24 | bay divided by `joist_spacing` |
| `open_web_joist` | member | chord + web | depth ≈ span/20, 1.5–3.0 m o.c. | alternative secondary tier |
| `roof_truss` | member ×N | chords + Warren or Pratt web | depth ≈ span/12…span/8 | long-span zones only |
| `brace` | member | HSS, X · K · chevron | 150–250 mm square | declared lateral bays |
| `moment_zone` | metadata | haunch or reduced-section region | — | declared lateral bays |
| `metal_deck_slab` | extrusion | composite deck + topping | 0.13–0.20 m | plate polygon per level |
| `slab_edge_angle` | member | angle or plate | 0.2–0.4 m | plate boundary polyline |
| `collector` · `chord` | member | W or plate | — | diaphragm boundary to lateral bay |
| `base_plate` | box | plate + anchor group | 0.4–0.9 m | column base node |
| `footing` · `pile_cap` | box | pad | 1.2–2.4 m | column base node |
| `column_splice` | metadata | bolted or welded | every 2–3 levels | column at splice level |

## Geometry primitives required

`member` dominates at roughly 70 % of instances. `extrusion` carries the decks. `box`
carries bases and footings. `quad` is not required by this system; it belongs to the
envelope layer.

## Datum chain specialisation

The registration lattice is the plain orthogonal one implemented in the fidelity probe.

```text
DATUMS   bay_x, bay_y, floor_to_floor, joist_spacing, truss_depth, truss_panels
   ↓
LATTICE  level_table[k].z  ×  x_lines[i]  ×  y_lines[j]
   ↓
ELEMENTS every member = f(two lattice nodes)
```

Bay dimensions are chosen from deck capability, girder depth budget, service penetration
depth, and erection piece size, in that order. `bay_x` and `bay_y` may differ; the longer
direction should carry the secondary tier.

## Legal variables and starting ranges

Project-authored experiment defaults, to be clamped by the resolved code profile.

| Parameter | Starting range | Owner |
|---|---:|---|
| `bay_x`, `bay_y` | 5.6–9.0 m | score (`density`) inside tectonic clamp |
| `joist_spacing` | 1.5–3.0 m | score (`density`) |
| `floor_to_floor` | 3.9–5.4 m | score (`tension_release`) |
| primary girder depth ratio | span/18–span/24 | tectonic |
| `truss_depth` | span/12–span/8 | score (`hierarchy`) inside clamp |
| `truss_panels` | 4–10 | score (`hierarchy`) |
| lateral bay count | 2–6 per direction | tectonic; never score |
| cantilever | 0–0.35 × adjacent span | score (`continuity`) inside clamp |

## Forbidden operations

- resizing a lateral brace or a transfer member from a score dimension;
- deleting a column from a braced bay to open a program view;
- a beam that changes depth continuously along its length without a named haunch;
- decks spanning with no declared direction or support edge;
- serving a long-span program zone by stretching an ordinary beam rule instead of
  selecting a truss, girder, or transfer candidate;
- claiming a moment frame without modelling the connection zone.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | truss depth, primary/secondary depth ratio, open ground-level height |
| Repetition | bay module regularity, joist cadence |
| Variation | bounded bay-width family change along one axis |
| Density | bay span, joist spacing, secondary-tier count |
| Continuity | cantilever depth, whether plates align or step |
| Interruption | atrium void count and position, transfer level |
| Polyphony | independent primary, secondary, and bracing readings |
| Tension / Release | floor-to-floor, open piloti level, double-height zones |
| Tempo of Change | frequency of bay-family change along the long axis |

## Program negotiation

| Program condition | Steel-specific response |
|---|---|
| reading room, gallery, auditorium | select a declared long-span topology; publish the clear-span range |
| public circulation, egress | hard column-exclusion zone; the lateral bay relocates, not the egress path |
| stacks, archive, plant | sourced load class; deck and beam tier re-checked, not silently reused |
| service risers, wet stacks | penetration coordinated with the secondary tier before the primary tier |
| facade | publish edge reactions and support points along `slab_edge_angle` |

## Grasshopper / Rhino modelling guideline

1. Build the level table and grid lines first; publish them as their own layers.
2. Instantiate columns from lattice nodes and carry the splice level as metadata.
3. Generate the primary tier on both axes, then subdivide bays for the secondary tier.
4. Declare lateral bays explicitly and generate braces from bay corner nodes.
5. Emit deck as an extrusion with an explicit span-direction attribute.
6. Trace the load path as a graph and store `supports` / `supports_elements` edges.
7. Sweep named sections last; the analytical line model stays the authority.
8. Bake per-tier layers so structure can be isolated in the viewport.

## Typology notes

- **Library:** stacks load classes and long reading-room spans are the two governing
  cases and usually want different bay dimensions in the two directions.
- **Theater:** the fly tower and the auditorium force a transfer level; the lateral
  system must survive the resulting discontinuity.
- **Museum:** column-free gallery runs and heavy point loads from art handling drive the
  primary tier; flexible partitions favour a regular grid.

## Validation

- 100 % of members resolve to two lattice nodes and a named section;
- every column has a continuous path to a footing, and every footing has a column;
- lateral bays are continuous top to bottom, or a transfer element is named;
- deck span direction is declared for every plate;
- span, cantilever, and spacing stay inside profile ranges or are flagged;
- no member intersects a program exclusion, egress, or accessible clearance zone;
- identical inputs reproduce identical element IDs and topology.

## Limitations

Sizes here are architectural conventions at study-model resolution, not analysis results.
Connections, fire protection, camber, erection sequence, and seismic detailing are
outside this guide. Every element remains `professional_review_required`.
