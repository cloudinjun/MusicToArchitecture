# 03 — Mass Timber System: CLT Panels on a Glulam Frame

- `system_id`: `STR-SYS-MASS-TIMBER-CLT-GLULAM`
- `tectonic_family`: `frame`
- `material_system`: `mass_timber_clt_glulam`

## Scope and research basis

Mass timber is a **panelised** frame. The floor is not a poured plate and not a field of
joists: it is a discrete set of manufactured panels, each with a grain direction, a
maximum width set by the press, a maximum length set by transport, and two bearing edges.
That manufacturing fact propagates all the way up into plan: the panel module becomes a
visible architectural datum, and the seams between panels are the ceiling.

Canonical references:

1. Acton Ostry Architects, **Brock Commons Tallwood House**, UBC, 2017 — CLT floor panels
   on glulam columns with concrete cores; the panel layout is the ceiling pattern.
2. Voll Arkitekter, **Mjøstårnet**, Brumunddal, 2019 — glulam frame and diagonals taken
   to high-rise scale.
3. White Arkitekter, **Sara Kulturhus**, Skellefteå, 2021 — CLT volumetric modules
   stacked between glulam trusses.
4. Shigeru Ban, **Tamedia**, Zurich, 2013 — an all-timber frame whose connections are the
   architecture (see also guide 04).

Primary sources:

- [APA ANSI/APA PRG 320-2025, Performance-Rated Cross-Laminated Timber](https://www.apawood.org/guides-tools-training/technical-document-library/standards/ansiapa-prg-320-2025-standard-for-performance-rated-cross-laminated-timber/)
- [AWC 2024 National Design Specification for Wood Construction](https://awc.org/resources/2024-nds/)
- [AWC 2021 Special Design Provisions for Wind and Seismic](https://awc.org/resources/2021-sdpws/)
- [ICC 2024 IBC Chapter 6, Types of Construction](https://codes.iccsafe.org/content/IBC2024V2.0/chapter-6-types-of-construction)

## Structural thesis

Glulam columns and beams form a frame at a bay dimension chosen from the **panel span**,
not the other way round. CLT panels span one way between beams, act as the diaphragm
through their seams and splines, and require a declared bearing at every edge. Lateral
load goes to a declared system — CLT shear walls, braced bays, or a concrete core — and
the choice is architectural, not incidental.

## Invariants

- `MT-INV-01` — every CLT panel has an explicit span direction, two bearing edges, and a
  declared layup or product class.
- `MT-INV-02` — panel width and length stay inside the declared product and transport
  limits, or the segmentation is marked unresolved. A room footprint is never exported
  as one panel.
- `MT-INV-03` — bay dimensions derive from panel span; the frame is subordinate to the
  panel module.
- `MT-INV-04` — panel seams, splines, and the diaphragm chord/collector path are modelled,
  not implied.
- `MT-INV-05` — glulam and CLT are different element types with different properties;
  they never share a generic "timber member" record.
- `MT-INV-06` — fire strategy (char depth, encapsulation, or exposed mass timber) is
  declared, because it changes member size and whether the timber can be seen.

## Element taxonomy

| Kind | Primitive | Section / form | Starting range | Located by |
|---|---|---|---|---|
| `glulam_column` | member | rectangular | 0.30–0.60 m square | grid node `(i,j,k)→(i,j,k+1)` |
| `glulam_primary_beam` | member | rectangular | depth ≈ span/16 | node `(i,j,k)→(i±1,j,k)` |
| `glulam_secondary_beam` | member | rectangular | depth ≈ span/18 | panel bearing lines |
| `clt_floor_panel` | extrusion | panel with grain direction | t 0.14–0.24 m, w ≤ 3.0 m | panel layout grid per level |
| `clt_roof_panel` | extrusion | panel | t 0.12–0.20 m | roof panel layout |
| `clt_shear_wall` | extrusion | panel wall with openings | t 0.10–0.18 m | declared wall lines |
| `panel_seam` · `spline` | member | plywood or steel spline | 0.15–0.30 m wide | between adjacent panels |
| `diaphragm_chord` | member | glulam or steel strap | — | plate boundary |
| `collector` | member | glulam or steel | — | diaphragm to lateral element |
| `concrete_topping` | extrusion | acoustic and levelling layer | 0.05–0.08 m | over floor panel set |
| `beam_column_connector` | box | knife plate or bucket | 0.2–0.5 m | every beam end |
| `hold_down` | box | tie rod and shoe | 0.2–0.4 m | shear wall ends |
| `concrete_core` | extrusion | closed profile + openings | t 0.25–0.40 m | fixed plan position |
| `footing` · `pile_cap` | box | pad | 1.2–2.4 m | column and wall base |

## Geometry primitives required

`extrusion` and `member` are equally load-bearing here, which is unusual. Panels are
extrusions with a grain attribute; the frame is members; connectors are boxes. The panel
layout means instance counts are moderate but each instance carries more metadata than
in any other frame system.

## Datum chain specialisation

```text
DATUMS   panel_span, panel_max_width, panel_thickness, floor_to_floor,
         bay_x (= panel_span), bay_y, lateral_system_type
   ↓
LATTICE  level_table[k] × x_lines[i] × y_lines[j] × panel_layout[k][p]
   ↓
ELEMENTS frame from grid nodes; panels from the panel layout; seams from panel
         adjacency; chords and collectors from the diaphragm boundary
```

The **panel layout** is a third lattice axis that no other frame system has. It is
derived, not authored: given a plate polygon, a span direction, and a maximum width, the
layout is a deterministic strip subdivision. Its seams are visible architecture, so the
layout must be published as a datum and not buried inside geometry generation.

## Legal variables and starting ranges

| Parameter | Starting range | Owner |
|---|---:|---|
| `panel_span` (= `bay_x`) | 4.5–8.0 m | tectonic; score selects inside the range |
| `panel_max_width` | 2.4–3.0 m | product; never score |
| panel thickness | 0.14–0.24 m | tectonic, from span |
| `bay_y` | 5.0–9.0 m | score (`density`) inside clamp |
| `floor_to_floor` | 3.6–4.6 m | score (`tension_release`) |
| span direction per zone | one of two axes | score (`variation`), one change rule |
| cantilever | 0–0.25 × panel span | score (`continuity`) inside clamp |
| exposed vs encapsulated | binary per zone | human; fire strategy |

## Forbidden operations

- exporting a room footprint as a single unsupported panel;
- a panel edge with no bearing element beneath it;
- panel width beyond the declared product limit without a segmentation record;
- cutting a penetration through a seam, chord, or bearing zone without a repair;
- inventing a layup, grade, char rate, or moisture class;
- treating CLT as a generic slab by giving it no grain direction;
- letting a score dimension set panel thickness.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | glulam beam depth ratio, exposed vs encapsulated zones |
| Repetition | panel module cadence, visible seam rhythm on the ceiling |
| Variation | panel span direction change between declared zones |
| Density | bay_y, secondary beam count, seam frequency |
| Continuity | whether the seam grid runs continuously across a level |
| Interruption | atrium voids that break the panel field, double-height zones |
| Polyphony | frame order and panel order read as two independent grains |
| Tension / Release | floor-to-floor, cantilevered panel edges |
| Tempo of Change | frequency of span-direction change along a circulation path |

## Program negotiation

| Program condition | Mass-timber-specific response |
|---|---|
| reading room, gallery | panel span sets the free dimension; long spans need glulam trusses |
| acoustic separation | concrete topping and floating floor; CLT alone rarely suffices |
| stacks, archive | high sustained load may exceed panel capacity; check before assuming |
| wet zones, plant | moisture class governs; timber may be excluded from the zone entirely |
| egress and fire | encapsulation requirement may forbid the exposed timber the design wants |
| facade | panel edges give a regular support line but limited tolerance |

## Grasshopper / Rhino modelling guideline

1. Choose panel span and span direction before the grid; derive `bay_x` from it.
2. Generate the panel layout as a deterministic strip subdivision of each plate polygon.
3. Verify every panel edge against a bearing element before generating any geometry.
4. Emit seams and splines as first-class elements from panel adjacency.
5. Build the glulam frame from grid nodes with connector volumes at every end.
6. Add the topping as one extrusion over the panel set, not per panel.
7. Trace the diaphragm path: panel → seam → chord → collector → lateral element.
8. Bake panels, frame, seams, connectors, and lateral system to separate layers, and
   publish a panel schedule with sizes and count of unique panels.

## Typology notes

- **Library:** the exposed soffit is a major architectural asset; stacks loads and
  acoustic separation are the two things that break it.
- **Theater:** acoustic isolation and fire strategy usually push the auditorium out of
  exposed mass timber; the foyer is where the system shows.
- **Museum:** humidity control for collections conflicts with exposed timber moisture
  class; galleries may need a separated envelope.

## Validation

- every panel has span direction, two bearing edges, thickness, and product class;
- no panel exceeds the declared width or length limit without a segmentation record;
- the unique-panel count and the total panel count are both reported;
- seams, chords, and collectors form a continuous diaphragm path to the lateral system;
- fire strategy is declared per zone and consistent with exposure;
- glulam and CLT elements are distinguishable by type in the exported model;
- identical inputs reproduce identical panel layouts and IDs.

## Limitations

No connection design, no char calculation, no vibration or acoustic verification, no
moisture or shrinkage modelling. Panel limits here are typical values and must be
replaced by a named manufacturer product before any claim. Every element remains
`professional_review_required`.
