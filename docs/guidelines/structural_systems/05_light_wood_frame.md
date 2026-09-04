# 05 — Light Wood Frame System

- `system_id`: `STR-SYS-LIGHT-WOOD-FRAME`
- `tectonic_family`: `frame`
- `material_system`: `light_wood_frame`

## Scope and research basis

Light wood frame is the only system in this library with **no column grid**. Structure is
a continuous field of small repeated members inside wall and floor planes: studs at
400 or 600 mm, joists at the same module, sheathing that turns both into diaphragms.
Nothing is a "column"; everything is a wall. Consequently the datum chain changes shape
entirely — the lattice is a set of **wall lines and openings**, not grid intersections.

This system is included because it is the honest answer for small-scale, low-rise, and
domestic-scale program, and because it stress-tests the assumption that structure means
a grid.

Canonical references:

1. MLTW (Moore, Lyndon, Turnbull, Whitaker), **Sea Ranch Condominium 1**, 1965 — light
   frame and plywood diaphragms shaped by wind and site rather than by a grid.
2. Rural Studio, **Auburn University**, ongoing — light frame as the vehicle for material
   experiment at building scale.
3. North American platform framing — the historical basis for stud module, plate, rim
   joist, header, and hold-down hierarchy.
4. Alvar Aalto, **Villa Mairea**, 1939 — light timber and infill read against a heavier
   primary order.

Primary sources:

- [AWC 2024 National Design Specification for Wood Construction](https://awc.org/resources/2024-nds/)
- [AWC 2021 Special Design Provisions for Wind and Seismic](https://awc.org/resources/2021-sdpws/)
- [ICC International Residential Code](https://codes.iccsafe.org/codes/international-residential-code)
- [APA, Engineered Wood Construction Guide](https://www.apawood.org/publication-search)

## Structural thesis

Load descends through **stacked bearing wall lines**. Each wall is a repeated stud field
with plates top and bottom; openings interrupt the field and require a header carried by
king and jack studs down to a post and a footing. Floors are joist or truss fields
spanning between bearing walls. Sheathing makes walls into shear walls and floors into
diaphragms; hold-downs anchor the shear wall ends. Nothing about this is optional — the
system fails at the first bearing line that does not stack.

## Invariants

- `LWF-INV-01` — bearing wall lines stack across levels; any offset requires a named beam
  and post, not a slightly moved wall.
- `LWF-INV-02` — every opening has a header, king studs, jack studs, and a continuous
  path from the header reaction to a footing.
- `LWF-INV-03` — the stud module is a declared datum and is the same across a wall; a
  wall with irregular stud spacing is unresolved.
- `LWF-INV-04` — shear walls are declared segments with an aspect-ratio limit and
  hold-downs at both ends.
- `LWF-INV-05` — joist direction is declared per bay and lands on bearing walls, never on
  a non-bearing partition.
- `LWF-INV-06` — large clear spans require an explicit hybrid element (steel or glulam
  beam, timber truss) or the profile fit check fails.

## Element taxonomy

| Kind | Primitive | Section / form | Starting range | Located by |
|---|---|---|---|---|
| `stud` | member | 38 × 89 / 38 × 140 mm | @ 400 or 600 mm o.c. | wall line subdivided by stud module |
| `top_plate` · `bottom_plate` | member | 38 × 89 / 38 × 140 mm | double top plate | wall line, per level |
| `king_stud` · `jack_stud` | member | same as stud, doubled | — | opening jambs |
| `header` | member | built-up or LVL | depth from opening width | opening head |
| `post` | member | built-up studs or PSL | 89–140 mm square | concentrated load points |
| `floor_joist` | member | 38 × 235–302 mm or I-joist | @ 400 or 600 mm o.c. | bay subdivided by joist module |
| `rim_joist` · `band` | member | same depth as joist | — | floor perimeter |
| `blocking` | member | joist offcut | @ 2.4 m or at panel edges | joist field |
| `roof_truss` | member ×N | prefabricated light truss | @ 600 mm o.c. | roof datum |
| `rafter` · `ceiling_joist` | member | 38 × 184–235 mm | @ 400–600 mm o.c. | roof datum, stick-framed option |
| `sheathing_panel` | quad | OSB or plywood, 1.2 × 2.4 m | t 11–18 mm | wall and floor panel layout |
| `shear_wall_segment` | metadata | declared length + aspect ratio | max 3.5 : 1 | declared wall lines |
| `hold_down` | box | strap or bolted device | 0.15–0.30 m | shear wall segment ends |
| `sill_plate` | member | preservative-treated | — | foundation top |
| `strip_footing` · `stem_wall` | extrusion | continuous under wall line | 0.4–0.8 m wide | every bearing wall line |

## Geometry primitives required

`member` again dominates, but at a far higher instance count than any other system: at
400 mm studs a modest building emits 5 000–15 000 members from walls alone. `quad`
carries sheathing panels and is genuinely structural here, not envelope. `extrusion`
carries continuous footings. This system is the strongest argument for the
`element_group` payload compaction described in decision 0008 — individual stud records
are neither useful nor affordable.

## Datum chain specialisation

```text
DATUMS   stud_module, joist_module, floor_to_floor, wall_thickness,
         opening_set, shear_wall_rule, roof_form, roof_pitch
   ↓
LATTICE  level_table[k] × wall_lines[w] × openings[w][o] × joist_bays[b]
   ↓
ELEMENTS studs from wall line ÷ stud module, minus openings;
         headers and jambs from the opening set; joists from bay ÷ joist module;
         sheathing from the panel layout on each wall and floor
```

There is no `x_lines` / `y_lines` grid. The lattice is a **planar wall-line graph**, and
its most important property is vertical stacking of wall lines between levels. That
single check replaces the column-alignment check of every other frame system.

## Legal variables and starting ranges

| Parameter | Starting range | Owner |
|---|---:|---|
| `stud_module` | 400 or 600 mm | tectonic; score selects between the two |
| `joist_module` | 400 or 600 mm | tectonic |
| joist span | 3.0–6.0 m | tectonic; program sets room width |
| `floor_to_floor` | 2.7–3.6 m | score (`tension_release`) inside a narrow clamp |
| wall thickness | 89–140 mm structural | tectonic |
| shear wall aspect ratio | ≤ 3.5 : 1 | tectonic; never score |
| opening width | ≤ 3.6 m without a hybrid element | tectonic |
| `roof_pitch` | 15°–45° | human or score (`hierarchy`) |

Note how narrow these ranges are. Light frame is the system where the score has the
least legal room, and saying so honestly is itself portfolio evidence.

## Forbidden operations

- deriving repeated framing from a commercial column grid instead of wall lines;
- a bearing wall that does not stack onto a wall or beam below;
- an opening without header, jambs, and a traced reaction path;
- a shear wall segment beyond the aspect-ratio limit;
- joists landing on a non-bearing partition;
- serving an auditorium or gallery clear span by increasing joist depth;
- omitting hold-downs and claiming a lateral system.

## Shared Score channels

| Dimension | Mapping in this system |
|---|---|
| Hierarchy | which wall lines are bearing versus infill; roof form prominence |
| Repetition | stud and joist module choice — a binary, not a continuum |
| Variation | bay width family change between rooms |
| Density | wall line count per plan area, opening frequency |
| Continuity | how many wall lines run the full plan depth |
| Interruption | opening clusters, double-height voids (each costs a hybrid element) |
| Polyphony | wall field and joist field as two grains at 90° |
| Tension / Release | floor-to-floor, ceiling height change, roof volume |
| Tempo of Change | frequency of joist-direction change between rooms |

## Program negotiation

| Program condition | Light-frame-specific response |
|---|---|
| any room wider than the joist span | insert a bearing wall or a declared hybrid beam |
| gallery, auditorium, reading room | the system usually fails here; declare a hybrid or change system |
| stacks, archive | concentrated load; light frame is rarely appropriate |
| public circulation | wall lines are the plan; circulation must be planned with them, not against |
| fire separation | wall assemblies do double duty as structure and rated separation |
| facade | the wall is the structure and the envelope; there is no separate support layer |

## Grasshopper / Rhino modelling guideline

1. Author the wall-line graph per level and check stacking before anything else.
2. Place the opening set on wall lines; generate headers, jambs, and posts from it.
3. Emit studs as an element group: wall line, module, and opening exclusions, not 5 000
   individual records.
4. Declare shear wall segments and check aspect ratio before hold-down placement.
5. Subdivide joist bays and check that both ends land on bearing wall lines.
6. Lay out sheathing panels on walls and floors; report panel count and edge blocking.
7. Generate the roof from the roof datum as trusses or as rafters plus ceiling joists.
8. Bake wall framing, floor framing, sheathing, and lateral devices to separate layers.

## Typology notes

- **Library:** only appropriate for a branch-scale or pavilion-scale library; the main
  reading room will need a hybrid element or another system.
- **Theater:** not appropriate for the auditorium; usable for support and back-of-house.
- **Museum:** generally inappropriate at institutional scale; useful for an ancillary or
  site pavilion.

Recording an honest "this system does not fit" result is a valid and valuable outcome of
the selection study.

## Validation

- every bearing wall line stacks, or a named beam and post resolve the offset;
- every opening has header, jambs, and a traced reaction to a footing;
- stud and joist modules are constant within each wall and bay;
- shear wall segments satisfy the aspect ratio and have hold-downs at both ends;
- joists land only on bearing wall lines;
- sheathing panel layout covers every declared diaphragm with edge blocking reported;
- element groups expand deterministically to the reported member count.

## Limitations

No member capacity, no nailing schedule, no fire-rated assembly verification, no
shrinkage or deflection check. The IRC prescriptive path and the NDS engineered path
differ; this guide assumes neither until the code profile is resolved. Every element
remains `professional_review_required`.
