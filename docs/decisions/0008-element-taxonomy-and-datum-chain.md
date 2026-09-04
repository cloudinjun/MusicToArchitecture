# Decision 0008 — Element Taxonomy, Geometry Primitives, and the Datum Chain

- Status: **implemented as schema 3.0**; all eight staged changes have landed
- Date: 2026-08-29
- Decision owner: user
- Career-value tags: V1, V2, V3
- Evidence: `blender/prototypes/student_model_fidelity_probe.py`,
  `artifacts/fidelity_probe/`

## Decision

Fix the **output register** first (what a run must be able to emit), then invert it to
the **datum chain** (how each element gets located), and only then change the compiler.

The target register is an **architecture studio physical study model** — white or
basswood, member-level, sectioned so envelope / structure / program read together. Not
a rendering, not a massing diagram.

Three things follow, in this order:

1. **38 element kinds** in five semantic layers (below).
2. **Four geometry primitives**, not one. The current `BuildingElement`
   (`position` + `dimensions` + optional `rotation`) is an oriented bounding box and
   can express exactly one of the four.
3. **Positioning by index into a registration lattice**, never by absolute literal.
   The lattice is derived from the score; every element is a pure function of it.

---

## Part 1 — Diagnosis of the current pipeline

```text
MP3 → audio.py (4 librosa features, 6 segments)
    → score.py (4 of the 10 shared dimensions)
    → compiler.py (LIBRARY_SPACE_SPECS fixture → ~600 boxes)
    → blender/import_building_model.py (box_mesh + one frustum)
    → GLB → web viewer
```

Five ceilings, in order of severity. Only the first is a schema problem; the rest
are consequences.

### C1 — Geometric primitive ceiling (the hard one)

`BuildingElement` is `center + size + one Euler rotation`. That primitive cannot
represent:

- a floor plate that is not a rectangle (curved end, cantilever notch, atrium void);
- a member whose two ends are at arbitrary points (brace, outrigger, truss diagonal,
  stair stringer, sloping rail);
- a section profile (W, SHS, CHS) — every "beam" is a smooth rectangular bar, so the
  structure reads as extruded diagram rather than steel;
- a thin free panel in space (glazing, spandrel, wall infill).

Adding element count on top of a box-only schema does not move the register. It just
produces more boxes.

### C2 — Level ceiling

`BuildingElement.level_id` is the constant `'L01'`. There is no level table.
`_structural_elements` hardcodes `y_lines = [-8.0, -3.4, -0.6, 6.0, 9.0]` and
`row_heights = [4.8, 5.2, reading_height, reading_height, 3.8]`. The pipeline
structurally cannot produce a second storey, therefore cannot produce a section,
therefore cannot show program stacking — which is most of what a study model is for.

### C3 — Hierarchy ceiling

Everything is one flat list at one scale order. A `facade_panel` is the same size
order as a `column`. Real models read because of a 4-tier size hierarchy
(primary frame → floor framing → envelope module → inhabitation detail), roughly
10× between tiers. Without joists, mullions, treads, and railings there is no
tertiary tier at all, so nothing establishes scale.

### C4 — Positioning ceiling (this is the "源头" problem)

`LIBRARY_SPACE_SPECS` is 21 rows of literal `x0, x1, y0, y1, height`. Every downstream
element is derived from those literals. The score can only *scale* what the fixture
already fixed — `spine_width`, `reading_height`, `service_depth`. The building's
composition is authored, not compiled. This is the reason the output looks the same
for every MP3.

### C5 — Presentation ceiling

Teal/green flat colors, three materials, one camera. A study-model read is
monochrome + shadow + edge density. This is the cheapest ceiling to lift and the
only one that is purely cosmetic — but it pays nothing until C1–C4 are fixed.

---

## Part 2 — What actually creates the studio-model read

From the reference models, the fidelity is **not** surface detail, texture, or curve
continuity. It is four measurable properties:

| Property | Threshold that reads | Current pipeline |
|---|---|---|
| Member count in the tertiary tier | ~2 000+ (mullions, joists, treads, rails) | 0 |
| Section profiles on structure | visible W / SHS / CHS | rectangular bars only |
| Slab edge thickness + cantilever | 0.25–0.35 m plate, visible fascia | flat roof panels |
| Scale anchors | 1.75 m figures, 1.05 m rails, 0.175 m risers | 1.75 m people only |

The probe hits all four: **38 kinds, 5 013 element instances, 30 290 faces**, which
renders in EEVEE in ~1.5 s per view. Fidelity here is cheap; the schema is the cost.

---

## Part 3 — Element taxonomy (种类 / 形态 / 造型)

Verified emitted counts from `artifacts/fidelity_probe/probe_report.json`.
`P` column = required geometry primitive (see Part 4).

### Layer: structure (结构) — 865 instances

| Kind | P | 形态 / 截面 | 尺寸量级 | 定位来源 |
|---|---|---|---|---|
| `footing` | box | 方形承台 | 1.6 × 1.6 × 0.9 | grid node (i,j), level 0 |
| `piloti_column` | member | CHS 圆管 | Ø0.48, h = `ground_open_height` | grid node (i,j), level 0→1 |
| `column` | member | W 型钢 | 420 × 340, tw 32, tf 48 | node (i,j,k) → (i,j,k+1) |
| `primary_beam` | member | W 型钢 | 620 × 300 | node (i,j,k) → (i±1,j,k) |
| `secondary_joist` | member | W 型钢 | 340 × 180 @ `joist_spacing` | bay 内等分 |
| `brace` | member | SHS，K 形 | 200 × 200 | 指定柱距 × 层 |
| `outrigger_strut` | member | CHS 斜撑 | Ø0.18 | 悬挑板边 → 上一层柱 |
| `truss_chord` | member | 箱形上/下弦 | 200 × 260 | 屋面层，每根 x 轴线 |
| `truss_web` | member | 箱形腹杆 | 130 × 130，Warren | span / `truss_panels` |
| `purlin` | member | 箱形檩条 | 120 × 200 | 桁架上弦节点间 |
| `floor_slab` | extrusion | 任意多边形 + 洞 | t = 0.30 | `plate_polygon(k)` − `void_polygons(k)` |
| `slab_fascia` | member | 板边加厚带 | 0.55 高 | 沿板边多段线扫掠 |
| `podium_slab` | extrusion | 台基板 | t = 0.35 | 首层轮廓外扩 4.5 m |

### Layer: envelope (外皮) — 2 322 instances

| Kind | P | 形态 | 尺寸 | 定位来源 |
|---|---|---|---|---|
| `mullion` | member | 竖挺 | 75 × 240 | 板边多段线 @ `mullion_module` = 1.24 m |
| `transom` | member | 横挺 | 75 × 140 | `transom_rows + 1` 道 / 层 |
| `glazing_panel` | quad | 玻璃嵌板 | α = 0.13 | 相邻竖挺 × 相邻横挺 |
| `spandrel_panel` | quad | 楼层实板带 | h = 0.55 | 每层底部 |
| `solid_wall_panel` | quad | 实墙板 | 模数同幕墙 | **由 program 决定**：服务/私密段不开窗 |
| `brise_soleil` | box | 水平遮阳板 | 深 0.70 | 仅南向，2 道 / 层 |
| `parapet` | member | 女儿墙 | 200 × 260 | 屋面轮廓 |
| `roof_deck` | extrusion | 屋面板 | t = 0.18 | 屋面轮廓内缩 0.6 |

`solid_wall_panel` is the one envelope kind driven by program rather than by score —
it is the demonstration that 外皮 negotiates with 使用, not only with music.

### Layer: circulation (流线) — 1 204 instances

| Kind | P | 形态 | 尺寸 | 定位来源 |
|---|---|---|---|---|
| `stair_tread` | box | 单块踏步 | riser 0.175, 每跑 ≈ 27 级 | flight (level k → k+1) 等分 |
| `stair_stringer` | member | 梯梁 | 180 × 450 | flight 两侧偏移 width/2 |
| `stair_landing` | box | 休息平台 | t = 0.24 | 折跑转折点 |
| `railing` | member | Ø64 上/中扶手 + 45 × 45 立柱 @1.5 m | h = 1.05 | 所有开敞板边 + 所有梯段 |
| `elevator_shaft` | extrusion | 竖向井道 | 3.0 × 4.2 | 服务区固定平面位置 |
| `ramp` | box | 坡道 | 1:12 | 场地 → 台基 |

Stairs and railings are 24 % of all instances. That is correct and expected: in a
study model, circulation is the thing the viewer reads first.

### Layer: program (programs) — 617 instances

| Kind | P | 形态 | 尺寸 | 定位来源 |
|---|---|---|---|---|
| `program_zone_{public,private,circulation,service}` | box | 楼板上的 0.11 m 薄色板 | 分区外接矩形 | 层 k 的分区表 |
| `partition` | box | 隔墙 | 0.20 × 2.90 | 分区长边 |
| `shelving_run` | box | 书架列 | 4.2 × 0.55 × 2.10 | stacks / collections 分区网格 |
| `desk` / `seat` | box | 桌 1.6 × 0.8 / 椅 | h 0.75 | reading / seminar 分区网格 |
| `figure` | box | 1.75 m 人形 | 躯干 + 头两块 | 每层 18 个 + 楼梯 + 场地 |

Program is deliberately emitted as a **thin plate on the slab, not a full-height
volume**. A full-height program box destroys the section — which is the current
pipeline's single biggest presentation mistake.

### Layer: site — 5 instances

`site_ground`, `site_step`, and the podium. Kept minimal and separately identified so
it can never be mistaken for accepted architectural geometry (per Decision 0005).

---

## Part 4 — Geometry primitives: what the schema must gain

| Primitive | Signature | Status | Consumers |
|---|---|---|---|
| **box** | `center, size, rot_z` | ✅ supported today | footing, tread, landing, partition, furniture, louver, figure, zone plate |
| **member** | `p0, p1, section_profile, roll` | ❌ **missing** | column, piloti, primary_beam, joist, brace, strut, truss chord/web, purlin, mullion, transom, fascia, parapet, railing, stringer — **14 of 38 kinds** |
| **extrusion** | `polygon[], z0, z1` | ❌ **missing** | floor_slab (curved end + cantilever + atrium void), podium, roof_deck, elevator_shaft |
| **quad** | `a, b, c, d` | ❌ **missing** | glazing_panel, spandrel_panel, solid_wall_panel |

A `member` also needs a **section profile library** — `W_column`, `W_primary`,
`W_secondary`, `SHS_brace`, `CHS_strut`, `truss_chord`, `truss_web`, `mullion`,
`transom`, `rail`, `post`, `stringer`, `piloti`, `purlin` — 14 named profiles, each a
2-D point list. Profiles are what make steel look like steel.

Proposed schema shape (tagged union, backwards compatible):

```python
class BoxGeometry(BaseModel):
    type: Literal['box']
    center: Vector3Value
    size: Vector3Value
    rotation_z: float = 0.0

class MemberGeometry(BaseModel):
    type: Literal['member']
    start: Vector3Value
    end: Vector3Value
    profile: str          # key into the profile library
    roll: Vector3Value = Vector3Value(x=0, y=0, z=1)

class ExtrusionGeometry(BaseModel):
    type: Literal['extrusion']
    boundary: list[Vector2Value]
    holes: list[list[Vector2Value]] = []
    z_base: float
    z_top: float

class QuadGeometry(BaseModel):
    type: Literal['quad']
    corners: tuple[Vector3Value, Vector3Value, Vector3Value, Vector3Value]
```

`BuildingElement.geometry: BoxGeometry | MemberGeometry | ExtrusionGeometry |
QuadGeometry`. Keep `position` / `dimensions` as derived read-only bounding data so
the existing Grasshopper reader, the web viewport filters, and
`mapping_report.py` do not break in the same commit.

### Payload control

At 5 013 elements a full JSON record each is ~2 MB, which is acceptable. But
`railing` (966), `transom` (920), and `glazing_panel` (690) are 51 % of the payload
and carry no individual design decision. Emit those as **`element_group`** records —
one rule plus a parameter table that expands deterministically in Blender and
Grasshopper — with IDs recoverable by index formula so `mapping_report.py` can still
name affected elements.

---

## Part 5 — 反推到源头：the datum chain

This is the answer to "how does anything get located". Replace absolute authoring with
a four-stage derivation. **No element may contain a coordinate literal.**

```text
architectural_score.json      10 scalars
        ↓  (only this stage reads the score)
DATUMS                        13 scalars: floor_to_floor, bay_x, bay_y,
                              joist_spacing, mullion_module, transom_rows,
                              cantilever, plate_step, void_count, truss_depth,
                              truss_panels, ground_open_height, level_count
        ↓
REGISTRATION LATTICE          level_table[k] : z, plate_polygon, void_polygons
                              x_lines[i], y_lines[j], apse_nodes[a]
        ↓
ELEMENT EMITTERS              every element = f(lattice indices)
        ↓
GEOMETRY                      box | member | extrusion | quad
```

### Score → datum mapping (as implemented in the probe)

| Datum | Formula | Value @ probe score | Driving dimension |
|---|---|---|---|
| `floor_to_floor` | `lerp(3.9, 5.1, x)` | 4.72 m | `tension_release` |
| `level_count` | `round(lerp(4, 7, x))` | 6 | `tempo_of_change` |
| `bay_x` | `lerp(7.8, 5.6, x)` | 6.52 m | `density` |
| `bay_y` | `lerp(8.4, 6.2, x)` | 7.12 m | `density` |
| `joist_spacing` | `lerp(2.6, 1.5, x)` | 1.96 m | `density` |
| `transom_rows` | `round(lerp(2, 4, x))` | 3 | `density` |
| `mullion_module` | `lerp(1.55, 1.15, x)` | 1.24 m | `repetition` |
| `cantilever` | `lerp(0.6, 3.6, x)` | 1.92 m | `continuity` |
| `plate_step` | `lerp(0.0, 5.5, x)` | 1.98 m | `variation` |
| `void_count` | `round(lerp(0, 3, x))` | 2 | `interruption` |
| `truss_depth` | `lerp(1.5, 3.0, x)` | 2.55 m | `hierarchy` |
| `truss_panels` | `round(lerp(4, 9, x))` | 8 | `hierarchy` |
| `ground_open_height` | `lerp(4.2, 6.0, x)` | 5.46 m | `hierarchy` |

`polyphony` and `genre_style` drive nothing yet and must stay declared as unsupported
in `mapping_report.json` rather than being given a decorative binding.

### Element ID = lattice coordinate

```text
STR-COL-X03-Y02-L04          column at grid (3,2) rising from level 4
STR-BEAM-X-X03-Y02-L04       primary beam, x-direction, same node
STR-JOIST-X03-S02-L04        joist, bay 3, subdivision 2
ENV-MULL-L04-S027            mullion, level 4, perimeter station 27
CIR-TREAD-F02-S014           tread 14 of flight 2
```

An ID that is a lattice coordinate is *self-locating*: given the level table and grid
lines, any consumer can recompute the element's position without reading its geometry.
That is what makes Grasshopper re-derivation, diffing between runs, and honest
mapping reports possible.

### Score bindings live on datums, not on elements

Today every element carries its own `score_bindings`, computed at emit time. At 5 000
elements that is both noise and a traceability lie — a mullion did not individually
negotiate with the music. Instead:

- each **datum** records `{dimension, value, rule_id, formula, applied_value}`;
- each **element** records `datum_refs: list[str]`;
- `mapping_report.py` joins them, so `affected_element_ids` is computed rather than
  accumulated.

Coverage ratio then means something real: *what fraction of the geometry is reachable
from a datum that a score dimension actually moved.*

### The single most important source-side change

`LIBRARY_SPACE_SPECS` must stop being 21 rows of `x0, x1, y0, y1`. Program becomes an
**area program allocated onto the lattice**:

```python
("open_stacks", "public", area_m2=340, level_preference=2,
 daylight="preferred", adjacency=["adult_reading"], depth_max=18.0)
```

and `_program_spaces` becomes an allocator that packs those areas into
`plate_polygon(k)` between grid lines. Until that inversion happens, the score can
only rescale a fixed plan, and every MP3 will keep producing the same building.

---

## Part 6 — Implementation staging

Each stage is independently shippable and independently demonstrable.

| Stage | Change | Unblocks | Evidence gate |
|---|---|---|---|
| S1 | Add `Level` + `Grid` + `Datum` tables to `BuildingModel`; emit `level_count` storeys of the existing box program | multi-storey, section views | a 4-storey run with a clipping-plane section |
| S2 | Add `MemberGeometry` + profile library; convert column / beam / joist / brace to members | steel reads as steel; joist tier appears | close-up render showing W sections |
| S3 | Add `ExtrusionGeometry`; floor plates become polygons with cantilever + voids | non-rectangular plan, atrium | plan + section pair |
| S4 | Add `QuadGeometry` + envelope emitter at `mullion_module` | 外皮 tier (~2 300 instances) | elevation at 1:200 read |
| S5 | Circulation emitter: treads, stringers, landings, railings | scale anchors, program legibility | the sectioned three-quarter view |
| S6 | Program allocator replaces `LIBRARY_SPACE_SPECS` literals | score actually changes the plan | two MP3s → two visibly different plans |
| S7 | `element_group` payload compaction + datum-based `score_bindings` | honest mapping report at 5 000 elements | coverage ratio recomputed from datums |
| S8 | White-model presentation profile in Blender | the studio-model read | the five probe views regenerated from the real pipeline |

S1–S3 are the schema break and should land together behind a `schema_version: '3.0'`.
S4–S6 are additive. S7 is a correctness fix that becomes urgent at S4.

### Implementation status, 2026-08-30

| Stage | Status | Where |
|---|---|---|
| S1 level table, grid, datums | **done** | `backend/app/datums.py` |
| S2 `member` + profile library | **done** | `backend/app/geometry.py`, sections chosen by `sizing.py` |
| S3 `extrusion` with holes | **done** | plate polygons, voids, cores, podium |
| S4 `quad` + envelope emitter | **done** | glazing, spandrel, solid panel at the mullion module |
| S5 circulation emitter | **done** | treads, stringers, landings, railings |
| S6 program allocator | **done** | `backend/app/program.py`: an area brief packed onto the plate |
| S7 `element_group` compaction | **done** | 3 650 elements in 69 groups; payload down 56 % |
| S8 white-model presentation | **done** | `blender/import_building_model_v3.py` |

Measured on the 44 s MP3 fixture: 3 117 elements across 36 kinds and five semantic
layers, carried as 68 element groups, compiled in 0.1 s and exported to a 2.5 MB GLB of
28 merged objects in 17 s.

**The datum set now has 34 entries and every variable one is score-driven.** Amendment
0004 extended the extractor so all ten shared dimensions carry real audio evidence, and
the datum table grew from 15 to 34 to give each of them something to move:

| Dimension | Datums it drives |
|---|---|
| `tempo_of_change` | level count |
| `tension_release` | floor-to-floor, shading rows, shading depth |
| `density` | bay x, bay y, joist spacing, transom rows |
| `continuity` | cantilever, apse radius, circulation allowance, flight width |
| `repetition` | mullion module, spandrel height, guard post spacing |
| `variation` | plate step-back, plate rotation per level |
| `hierarchy` | truss depth, truss panels, open ground height, entry canopy span |
| `interruption` | void count, void scale, terrace count |
| `polyphony` | envelope offset, envelope layer count, braced bay count |
| `genre_style` | opaque fraction, fin depth |

Coverage is reported two ways because one number hides the truth. **Overall coverage is
85 %**; the remaining 15 % are the five tectonic constants — slab thickness, edge fascia,
riser, guard height, figure height — which are fixed by the structural system and the
code, not by the brief. **Variable coverage is 100 %**: every datum the music is
permitted to move is moved by the music.

Two tectonic clamps were added when the expanded set proved able to overreach. Plate
step-back is capped at 3.5 m per level, and at most one occupied level in three may lose
its envelope to become a terrace. Past those limits the score stops composing a building
and starts dismantling one.

A sweep across all ten dimensions at their extremes:

```text
score          elements  levels  height   bay  mullion  offset  layers  opaque  canopy  voids  rotation
all low            3113       6   20.2m  7.69     1.53    0.28       1    0.35     0.5m      0     0.15
as recorded        3117       6   23.9m  6.96     1.49    0.51       2    0.31     7.3m      3     2.22
all high           7201       9   43.2m  5.71     1.17    0.77       3    0.20     8.6m      3     2.85
```

### What S6 changed

The plan is now a result rather than a drawing. `program.py` states the brief as areas
and requirements -- 430 m2 of open stacks, minimum dimension 9 m, prefers a low level,
7.18 kPa -- and an allocator cuts each level into strips between the structural grid
lines, measures each strip against the real plate polygon minus its voids and core, and
packs the brief into them. Large rooms span two or three contiguous strips rather than
becoming corridors.

Three consequences follow, and all three are the point:

- **The score decides whether the brief fits at all.** A four-level result delivers 75 %
  of the brief and names the three rooms it could not place; a seven-level result fits
  everything at 100 %. The allocator reports the shortfall instead of shrinking rooms
  quietly.
- **Room proportions come from the grid.** Band depth is the bay dimension, so changing
  `density` changes the shape of the reading room, not just its position.
- **The load calculation closes the loop.** The governing occupancy per level now comes
  from what was allocated there, so the column stack sums the real per-level loads
  instead of repeating the heaviest room on every storey. On the fixture that moved the
  column from SHS-350x350x10 at 0.96 to SHS-350x350x8 at 0.87.

---

## Limitations of this decision

- The probe is a **target-state demonstration**, not pipeline output. It hardcodes a
  library composition to prove the primitives and the datum chain; it does not read
  `architectural_score.json` and has no acceptance authority.
- The probe's structural members are dimensioned by architectural convention, not by
  analysis. Every structural claim stays `professional_review_required` per
  Decision 0002.
- No connection detail, no envelope build-up, no code compliance. A study model shows
  member presence and hierarchy, not constructability.
- The taxonomy above is derived from **system 01, structural steel frame**. Decision
  0002 is an N-choose-1 over ten executable systems, each with its own guideline in
  [`docs/guidelines/structural_systems/`](../guidelines/structural_systems/README.md).
  Selecting a different system replaces the structure layer's 13 kinds and, for four of
  the ten, extends this document's primitive contract:
  systems 06 and 08 require a `mesh_surface` primitive, system 09 requires a curved
  `member.path` with a bend-radius limit, and system 07 requires a pretension state on
  `member`. Systems 01-05 and 10 fit inside the four primitives defined here.
  The datum chain, the ID-as-lattice-coordinate rule, the datum-level score bindings,
  and the envelope, circulation, and program layers survive every selection.
- Stage C of the structural selection should close before stage S2 of the staging plan
  begins, because the selected system decides which primitives S2 must implement.

## Amendment — type, form, style and structure become consequences of the score (2026-08-31)

A fourteen-track corpus run produced fourteen buildings that shared thirty-five of their
thirty-six element kinds. The counts varied by up to 1.9x; the *vocabulary* varied
between 35 and 36. That is the precise shape of "the models all look the same": the datum
chain was moving quantities inside a single building, and nothing was moving the building.

Four decisions were module constants:

```
models.py:105        typology: Literal['library'] = 'library'
models.py:106        tectonic_system: Literal['frame'] = 'frame'
compiler_v3.py:39    STRUCTURAL_SYSTEM_ID = 'STR-SYS-STEEL-FRAME'
datums.py:285        PLAN_X_MIN, PLAN_X_MAX = -14.0, 22.0
```

Two were *type-level* constants, not overridable defaults. And `screen_project` — the
whole coupling and code-screening layer, ten structural systems and ten facade grammars —
was called only by a report script. It had never been a pipeline stage.

### What changed

**`massing.py`** — seven silhouette families. The footprint, how it changes with height,
and the storey band are properties of the family; cantilever, step-back and rotation
remain the score's perturbations *within* it. `PlanBounds` now travels on the lattice, so
the sectional cut and the atrium void seeds are fractions of the plan a building actually
occupies rather than the coordinate literals they were.

**`briefs.py`** — museum, theatre and pavilion, beside the library that was already
there. A brief is not a style: two libraries in different grammars are one building
differently dressed, while a theatre and a pavilion differ before anything is drawn.

**`tectonics.py`** — eight envelope families and four frame families, defined by the
*operation* they perform rather than by their dimensions. A curtain wall subdivides, a
punched wall subtracts, a lattice overlays, an expressed frame recesses. Six of the ten
structural systems are still screened out with a stated reason; approximating a shell on
a level lattice would be the failure this project exists to avoid.

**`grammar_specs.py`** — every number transcribed from the ten written style guides,
which existed and had never reached the compiler. The load-bearing field is
`score_authority`: Minimalism's guide caps score-driven variation at 12 % in writing,
Parametricism expects the field to swing, and the emitter honours the difference. Two
grammars under the same music now produce differently *disciplined* buildings.

**`facade_gates.py`** — the Validation section of each guide, run on the emitted geometry.
Verdicts are three-valued: a gate the pipeline cannot evaluate returns `unevaluated` and
never `passed`, which is why Critical Regionalism's orientation gate reports the missing
site data instead of defaulting quietly.

**`selection.py`** — the stage `coupling.py` deliberately left empty. The screen decides
what may exist and contributes no number; the score chooses inside what survives and can
eliminate nothing.

### Three mistakes worth keeping on the record

**Nearest-neighbour selection has dead options.** The first three versions searched for
the closest grammar in a four-dimensional axis space, and each collapsed onto whichever
option sat nearest the middle of the corpus — first two grammars taking ten of fourteen
tracks, then one taking seven. Sharpening the weights only moved the winner. It is not a
tuning problem: nearest-neighbour selection over a fixed option set always concentrates
near the data's centre of mass, and the options at the corners stay unreachable however
the metric is scaled. Worse, tuning constants against fourteen recordings is the
overfitting the audio calibration went to some trouble to avoid, applied to architectural
positions that have no business being fitted to a corpus. The choice is now a short
sequence of discrete questions asked against single axes at full resolution, and the
tests sweep the space to prove every leaf is reachable.

**A branch added for a capability that does not exist never fires.** `FRM-CONCRETE` was
defined, positioned, and unreachable, because the system behind it was screened out for
having no ACI 318 check. Writing the tree around a leaf nothing could route to produced
exactly the same silent dead option as a constant. The check now exists — Whitney stress
block with a real tension-controlled test, phi*Vc with no stirrups designed, the tied-column
axial cap with a stated slenderness reduction — and the reinforcement ratios are reported
as assumptions on every member rather than buried.

**Averaging destroys the ends of a range.** An axis built as the mean of two dimensions
is more mid-range than either, so every recording landed between 0.29 and 0.62 on an axis
running 0 to 1 and the grammars positioned at the ends were unreachable. The same defect
appeared one level up in the weighting and one level down in the massing thresholds,
where the ziggurat branch was left a window 0.04 wide. Taking the more decisive of two
readings rather than their average is the correction, and it is the same architectural
principle each time: a building takes its identity from what the music is most decisive
about, not from the average of four things it is lukewarm about.

### Result

Across the same fourteen recordings: 6 massing families, 3 typologies, 9 distinct
footprints, storey counts from 6 to 9, 6 facade grammars, 3 structural systems, and 11 of
14 element vocabularies distinct — against 1 before. Program fit improved from 8/14 to
11/14, because a brief now matches the building it is tested against. All sixty facade
gates pass, four models having self-corrected once each.

`compile_building_model_v3` accepts `massing_id`, `typology` and `grammar_id` overrides.
They exist because comparing two recordings is only meaningful with the other variables
held: several existing tests had quietly become assertions about whichever building the
fixture happened to produce, which is not what any of them were written to check.

## Amendment — the circulation core meets the floors it serves (2026-08-31)

Once the footprint became a property of the massing family, the stairs stopped meeting
the building. The circulation emitter was authored entirely in coordinates taken from
the original thirty-six by twenty-two metre slab:

```
v3(16.0, south, levels[0].z)               the external approach
ax = min(p.x for p in plate) - 1.5         the switchback, 1.5 m outside the plate
v3(1.6, -3.6, levels[k - 1].z)             the interior flight
v2(18.4, 5.2) .. v2(21.4, 9.4)             the lift shaft
v3(26.0, -2.0, -0.4)                       the ramp
```

Measured across the fourteen-track corpus: **8 of 78 landings sat on the plate they
claimed**, and 33–56 % of treads stood outside the building entirely — 211 of 373 on a
compact tower. The compiler's own docstring forbids absolute coordinate literals in
emitters; this module had a dozen, and they had been harmless only for as long as there
was one footprint.

### What a landing has to do

Two conditions, and the old emitter met neither reliably. **On the plate** means a person
can reach it. **Flush** means the top of the landing *is* the floor — a landing sitting
proud or shy of the slab is a trip hazard drawn to look like a landing. `stair_landing`
and `stair_half_landing` are now separate kinds, because a half-landing is the turn
between flights and is flush with nothing; keeping them as one kind made "does this
landing meet a floor" an unaskable question.

`_stair_anchor` applies the invariant the column stack already kept: a node is usable
only if *every* plate from the ground to the top contains it — and contains the stair's
whole footprint, landings included. Checking the flight width alone was the first
attempt, and it produced landings that were flush with a floor and a metre and a half
outside it, which is worse than the failure it replaced.

Where no single core can serve every level, the stair serves the tallest run it can and
the model records which levels it could not reach. Falling back to a plan centroid was
the other first attempt: it kept the run alive and served nothing.

### Three massing defects the stair check exposed

None of these showed on a six-storey slab, and all three are real.

**The taper leaned.** A tapering family narrows from both sides, but the score's
step-back was subtracted from the east edge only. On a ten-storey tower the east edge
came in from 11.7 m to 2.0 m while the west edge never moved. A centred profile now takes
the step symmetrically; an end-anchored one — slab, ziggurat, split — keeps the east-only
step, because there the step-back from one end is the reading rather than an accident.

**The stack walked.** Plate rotation was `deg * (level - 1)`, unbounded, applied about
each plate's *own* centroid. At ten levels the top plate had turned far enough, about a
centroid that moved with the taper, to sit fifteen metres west of a footprint whose west
edge is at minus seven. The angle is now capped and the turn is about a fixed point.

**The minimum-plate guard was checked too early.** `_profile_extent` tested its own inset
before the score's step-back applied, so a tower reached a top floor 3.6 m across. The
guard now runs after every narrowing, and a plate too small to hold a stair landing is
where the building stops rather than a floor nobody can reach.

### Result

Across the same fourteen recordings: **114 of 114 floor landings flush and on the plate**,
**zero occupied levels without a landing**, and **zero of 2,686 non-entry treads outside
every plate**. The entrance flight still starts on the ground outside the building, which
is what an approach from grade does; its top landing is checked for flushness like every
other. Towers now reach twelve and thirteen storeys usefully, because the levels that
were being generated and abandoned are either usable or absent.

Five tests in `backend/tests/test_differentiation.py` hold this: landings flush and
on-plate for every massing family, a landing at every level a flight arrives at, only the
entrance flight outside the building, the lift core inside the storey each segment spans,
and no circulation element sitting where the old slab's literals used to be.

## Amendment — the accessible approach complies with ADA §405, or it is a stair (2026-08-31)

The accessible route was one box:

```
BoxGeometry(center=..., size=v3(2.4, max(3.0, rise * 6.0), 0.28))
```

`rise * 6.0` is a **1:6 slope** — exactly twice the maximum §405.2 allows — and it was
1:6 on all fourteen corpus models. It carried 4.6 to 5.8 m of rise in a single run where
§405.6 caps a run at 760 mm, and it had no intermediate landings, no handrails and no
edge protection. A wheelchair user cannot climb 1:6 and can lose control descending it.
It was a ramp in name and a hazard in fact.

### The rule

`ada.py` computes what §405 actually requires and returns one of two answers: a plan
whose `compliance()` is empty, or nothing. There is deliberately no third outcome. **An
almost-compliant ramp is worse than no ramp**, because it occupies the place the
accessible route belongs and reports the problem as solved; a stair with a stated reason
leaves the problem visible.

Every constant cites its clause — 405.2 slope, 405.5 clear width, 405.6 run rise,
405.7.3 landing length, 405.7.4 turn landings, 405.8 handrails, 405.9.2 edge protection,
505.4 and 505.10 for handrail height and extensions — and the model carries the plan it
was checked against rather than a claim about it.

### Why the ramp folds

At 1:12 with runs capped at 760 mm of rise, a five-metre podium needs eight runs and
about sixty-five metres of ramp. Nothing in front of these buildings is sixty-five metres
long, so the route switchbacks: each run crosses the available frontage, the direction
alternates, and a 1525 × 1525 mm landing sits at every turn.

The frontage available is the half *beside* the entrance stair, not across it. The first
version spanned the whole elevation and the two ran through each other — the ramp from
x −13.7 to 19.3 and the stair descending at 4.9, both between ground and podium. A
switchback that crosses the front door is not a route; it is a collision drawn twice. The
approach steps were narrowed for the same reason: they spanned forty-six metres at a
literal x of 4.0 and sat underneath the ramp.

### Result

Across the fourteen recordings: **11 compliant ramps at exactly 1:12**, run rises 662 to
750 mm against the 760 mm cap, zero violations, zero clashes with the entrance stair —
and **3 stair fallbacks**, all three of them the compact-tower massing, where a
twenty-two metre frontage genuinely cannot hold a switchback beside the door. That split
is the rule working: a tower with a five-metre piloti and a narrow frontage has no room
for an accessible ramp, and the model says so instead of drawing a 1:6 slope.

### A measurement trap worth recording

A swept deck's bounding box includes its own thickness, so dividing box height by box
length makes a compliant 1:12 run measure about 1:8.6. The first check written against
the emitted geometry reported violations that were not there. The test now reads the
member centre-line — two points and the line between them — which is how the run was
drawn and how the standard measures it.


## Amendment — from coordination model to permit-level record (2026-08-31)

Four things separate a model that coordinates systems from one a plan checker can read,
and the pipeline was missing all four.

### 1. Members were correct calculations of shapes nobody rolls

`sections.py` generated its steel from proportions:

```
for d in (200, 250, ... 1000):
    for ratio, tw_f, tf_f in ((0.50, 0.020, 0.032), ...):
```

Every property computed correctly, and `I-450x225x9x14` is not orderable. `registry.py`
now lists real products with the standard each is made to -- ASTM A992 W shapes, ASTM
A500 Grade C square HSS, EN 14080 glulam, ANSI/APA PRG 320 CLT, cast concrete on
formwork increments with ASTM A615 bar. Properties are still computed from the published
dimensions rather than transcribed, because a number nobody can recompute is a number
nobody can audit, and the published values ride alongside for one purpose:
`verify_against_catalogue()` reports the deviation.

**It found three transcription errors immediately.** The plastic modulus of W10X49,
W12X65 and W12X87 had been entered against the wrong conversion, 11-13 % high. After the
correction all 85 comparisons sit in a tight one-sided band -- area -1.8 % to 0.0 %, Ix
-2.5 % to -0.5 %, Zx -2.3 % to -0.6 % -- which is the root fillets the idealised geometry
has none of, consistently and conservatively.

**It also found an unconservative idealisation.** A cold-formed HSS has an outside corner
radius of about 2t, and the sharp-cornered box overstated area by 2-3 % and Ix by up to
9 %. That direction matters: for a W-shape the missing fillets make the computed
properties *low*, which can be reported and left alone, but for an HSS they make them
*high*, so a column sized on them is weaker than the calculation says. `hss_section`
models the corners; the area now lands within 0.9 % across the whole range.

### 2. A ratio under one is not a calculation record

`sizing.py` returned four utilisations. A plan checker asks which clause governed, under
which combination, and which clauses were skipped. `validators.py` returns a
`ClauseCheck` per clause, each naming its section of its standard, and `unevaluated`
clauses appear on **every member record** rather than only in a project preamble --
because a reviewer reads a member calculation, not a preamble.

**The clause that was assumed away.** `steel_flexural_capacity` returned phi*Fy*Zx and
its docstring said "continuously braced compression flange assumed". A girder braced only
where its joists land is not continuously braced. AISC F2.2 is now implemented in full
and reproduces the published bracing lengths for W18X50 -- Lp 1788 mm against a published
5.83 ft, Lr 5173 mm against 17.0 ft. It governs: on an unbraced eight-metre span that
section reads 0.55 on yielding and **1.71 on lateral-torsional buckling**. `select_beam`
now rejects on the full clause record, so the selection can no longer choose a member
that does not work.

Bracing is stated rather than assumed: a joist is braced continuously by the deck it
carries, a girder at its joist spacing, and both are passed in.

The other additions: all seven ASCE 7-16 2.3.1 strength combinations rather than one;
NDS volume factor CV and beam stability factor CL for glulam, taken as the lesser per
NDS 5.3.6; ACI 318-19 minimum flexural reinforcement and the tension-controlled check
beside the flexure and shear that already existed; St Venant torsion and warping
constants so F2 has the properties it needs.

### 3. A brief is not a building

`briefs.py` listed what a client asks for. The base-building support constitution in
`docs/guidelines/program_constitution_guideline.md` had never reached the code, so every
typology was allocated with no public restrooms, no janitor's closet, no electrical or IT
room, no fire service entry, no refuse holding and no riser zones. Validated against the
constitution, the four briefs satisfied **2 to 4 of 15 support requirements**.

`constitution.py` implements §5 and generates what a brief omits. Areas are the honest
part: where the guideline delegates a quantity to a code profile -- restroom fixtures to
the adopted plumbing code, mechanical area to the system selection -- the area is a
placeholder that **says so in its own reason**, because a placeholder that announces
itself is usable and one that does not is a fabricated compliance.

Occupant load comes from IBC Table 1004.5 rather than a guess, which is what makes
everything downstream of it checkable: 668 occupants for the library, 787 museum, 882
theatre, 358 pavilion.

All four typologies now satisfy 15/15. **The program fit rate fell from 11/14 to 5/14**,
and that number is the true one: the buildings were only fitting because the brief was
missing the rooms every building needs.

### 4. Drawing stairs is not egress design

`life_safety.py` builds the graph IBC Chapter 10 is written about -- spaces as nodes,
stairs and discharges as exits, edges carrying the distance walked -- and asks 1004.5,
1005.3, 1006.3.2, 1007.1.1, 1011.2 and 1017.2 of it.

**It found a real violation on the first run.** Exit remoteness failed at 2.11 against
the one-third-diagonal rule: a building with 419 occupants had one stair core, and one
core is not two exits however many landings it has. A second core is now placed by
maximising distance from the first, and it serves the storeys it can reach rather than
being forced to the top -- a plan whose upper floors shrink has only one region common to
all of them, and two coincident stairs are not an egress strategy.

Where no remote pair fits, the best available second core is still built and the graph
**fails the clause**. A twenty-two metre tower cannot put two stairs a third of its
diagonal apart; the honest report is the failure, not an omitted stair and not a quietly
passed check.

Five clauses return `unevaluated` and say why -- common path of egress travel needs a
corridor branch the graph does not model, and calling a flight a protected stair is a
label the model has not yet earned.

### What is still not permit level

Wind and seismic are absent and both need a site. Snow has a function and no assigned
ground load. Connections are designed in no material, and in timber they commonly govern
the member. Fire-resistance ratings are screened but not delivered. Floor vibration is
unchecked and governs long-span library floors. Every one of these appears as an
`unevaluated` clause on every member record, which is the point: a permit set that
silently omits a check is worse than one that lists it.


## Amendment — a proposed location, a code lookup, and a seam for a person (2026-08-31)

Five clauses returned `unevaluated` on every member for one reason: wind, seismic and
snow are properties of a place, and the project had none. `codes.UNRESOLVED_JURISDICTION`
said the same thing from the other end -- every code gate ran against placeholder tables
because nobody had said where the building was.

### The chain, and why the third step is the design

1. **A location is proposed**, by an LLM provider, a static provider, or a person.
2. **The code parameters are looked up from it** -- basic wind speed, mapped spectral
   accelerations, ground snow load, the adopted code edition and amendments.
3. **Any value can be replaced by a human, one field at a time.**

Step three is what the structure is built around. Every parameter is a `SourcedValue`
carrying `source`, `set_by` and `needs_review`, so

```python
site = override(site, by='J. Ito, SE', basic_wind_speed_ms=51.4)
```

replaces one number, marks that one `manual`, and leaves the other thirteen with their
own provenance. Nothing is re-derived and nothing inherits authority it does not have.
`mark_verified` is the other half: the same number, but somebody has now checked it
against the published source.

### A value nobody has reviewed cannot become a design value

The lookup table holds figures **recalled by a language model**, not read from ASCE 7's
maps or a jurisdiction's amendments. They are the right order of magnitude and they are
not authoritative, so every one leaves the table with `needs_review=True`.

That flag propagates. `site_loads` computes snow, wind and seismic as soon as a site
exists, and each result carries the weakest provenance among its inputs. A clause fed by
an unreviewed parameter appears on the member record with the **figure shown** and the
status `unevaluated`: a base shear derived from a recollection of a seismic map is a
guess with a citation attached, which is more dangerous than a guess without one. The
same rule reaches the code gates -- `to_jurisdiction` returns `status='resolved'` only
when every value is human-set or human-verified, because a gate returning `pass` on an
LLM-recalled code edition would be worse than the placeholder it replaced.

### What is computed

- **Snow**, ASCE 7-16 7.3.1, complete for a flat roof. Drift, sliding and unbalanced
  cases are not.
- **Wind**, 26.10 velocity pressure and a 27.3 windward-plus-leeward base shear. No
  internal pressure, no components and cladding, no torsional cases -- enough to say
  whether wind governs the lateral system, not enough to size anything.
- **Seismic**, 12.8.1 equivalent lateral force, with R taken from Table 12.2-1 for the
  four systems this compiler can build. A system with no R gets no base shear rather
  than an invented one. Vertical distribution, drift and redundancy are not computed.

### That the loads follow the place is the test that matters

Miami comes out a wind problem, Los Angeles a seismic one, Chicago the only one of the
three with snow. On the same building: Miami wind 2,907 kN against seismic 339 kN; Los
Angeles seismic 7,423 kN against wind 694 kN. If those did not flip, the lookup would be
decoration.

### Replacing the whole thing with human input

`compile_building_model_v3(..., site=parameters)` takes a fully human-authored
`SiteParameters`; the LLM provider is only the default. A project with a real site skips
steps one and two entirely, and the reports then show fourteen values a person set
rather than fourteen a model proposed.


## Amendment — interior partitions that enclose, are rated, and open (2026-08-31)

The pipeline drew a partition like this:

```python
if zone.category in ('private', 'service'):
    b.add(..., 'partition', ...,
          BoxGeometry(center=v3((x0 + x1) / 2.0, y0, level.z + 1.35),
                      size=v3((x1 - x0) * 0.9, 0.20, 2.70)), ...)
```

One box, along the south edge of a rectangle, 200 mm thick and 2.70 m tall whatever the
storey height. It enclosed nothing, had no type, no fire rating, no acoustic separation
and no door. Public zones got none at all.

### Three questions, none of which were being asked

**What has to be separated.** The program constitution already carried `must_separate`
and `access_class`, so the model knew a staff workroom is not a gallery and that refuse
must not open onto the entrance sequence. Partitions are how those relations become
geometry, and until now the vocabulary existed with nothing built from it.

**What rating the separation needs.** IBC Table 509 rates the walls around incidental
uses at one hour and admits a sprinkler in lieu for some of them -- which is why the
site's `sprinklered` flag reaches this far, and why a storage room in a sprinklered
building gets no rating while a mechanical room still does. IBC 707.4 rates a shaft at
one hour below four storeys and two at four and above. IBC 1020.1 rates a corridor at
one hour only when the building is unsprinklered.

**What the room needs acoustically.** ANSI/ASA S12.60 sets 50 for a teaching space; the
rest are ordinary practice and are labelled as practice rather than as code. A room
beside plant is held to 55 whatever it would ask for on its own.

Fire and acoustics are answered separately because one does not imply the other: the
two-hour masonry wall in this module is acoustically *worse* than the one-hour
double-stud partition, so a selector that used either as a proxy would pick wrongly in
both directions.

### What gets built

`select_partition` takes the lightest assembly that satisfies both, because a two-hour
wall where an hour is required is not safer -- it is heavier, thicker and more expensive.
That makes the ordering of the assembly list the design objective, and the hand-written
order had the STC 60 double-stud wall sitting after the two-hour ones; it is now sorted,
and a test holds it there.

Every opening is a real door: a 915 mm leaf giving the 815 mm clear width ADA 404.2.3
requires, with a **head over it** so a rated wall carries its rating across the doorway.
A rated wall that stops at the door head is not rated, and the head is the piece a box
partition never had.

A wall nothing asks for is not built. Two rooms in open categories -- public or
circulation -- with no rating and no acoustic target stay open, so the plate still reads
as one floor. The first version of that rule tested only the corridor edge and still
walled the lobby off from the room beside it, because a lobby's category is
`circulation`.

### Result

On the same slab massing, each typology gets the partition mix its program asks for
rather than the same box:

| | segments | doors | assemblies used |
|---|---:|---:|---|
| library | 52 | 26 | one-hour stud, glazed screen, high-isolation double stud |
| museum | 74 | 37 | + one-hour acoustic |
| theatre | 64 | 32 | one-hour stud and high-isolation only -- no glazing, because a theatre is all acoustically demanding rooms |
| pavilion | 82 | 41 | + two-hour shaft wall at the riser |

Every partition carries the clause that rated it and the source of its acoustic target,
and every rated door says that its opening protective has not been selected -- which is
true, and is the kind of gap that belongs on the element rather than in a note.

### Two constraints a rating and an STC target cannot express

Reading the emitted schedule found both, and neither is visible in the two numbers
the selector started with.

**A store must not be seen into.** The museum came out with glazed screens on its
collection store, because 0 hours and STC 35 is exactly what a glazed screen delivers
and nothing said a store is different. Excluding glazing alone then put a demountable
panel system there instead -- opaque, and still not an enclosure.
`OPAQUE_REQUIRED_TYPES` excludes both.

**A loading bay needs a wall that survives a trolley.** The acoustic target beside a
noise source is 55, masonry delivers 52, so the selector reached for a 250 mm
double-stud gypsum wall -- which is quiet and is destroyed in a year. Trading one
against the other is the wrong move in both directions, so the answer is a real
assembly that does both: 190 mm masonry with an independent stud lining, two hours
and STC 60. Plain masonry still serves a quiet store, so the composite is for the case
that needs it rather than the default.


### Postscript — half a frame was being checked

A scan for unused imports found `validate_concrete_column` and `validate_steel_column`
imported into `sizing.py` and never called. Beams carried a clause-by-clause record;
the columns holding them up carried four utilisations and nothing else. Columns now
produce the same record -- E3 flexural buckling, E2 slenderness, B4.1a element
slenderness, with H1 combined axial and flexure and E4 torsional buckling listed as
unevaluated, because a gravity-only frame puts no moment in a column and any lateral
load makes H1 govern.

A timber column returns no clause record rather than a steel one. The NDS column
stability check still runs and still governs the selection; what does not exist yet is
the clause-level write-up, and attaching a steel record to a glulam post to fill the gap
would be worse than the gap.

The gap was found by a lint pass rather than by a test, which is its own finding: a
validator that is imported and never called looks exactly like one that is working.
