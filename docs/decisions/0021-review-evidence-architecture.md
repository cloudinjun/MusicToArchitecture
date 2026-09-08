# Decision 0021 — Review evidence is a product of the compiler, not of a redline round

- Status: proposed; architecture plan derived from the R2 simulated plan review, staged for implementation
- Date: 2026-09-05
- Decision owner: user ("把这份建议消化后转为优化架构的方案方便适应以后的任意模型（而不是硬改单一套图）")
- Career-value tags: V2, V3, V4
- Input: `MusicToArchitecture_R2_Redline_Combined.pdf` (17 pages, 42 items: 3 图证 / 31 待核 / 8 表达; 35 P1 / 7 P2)

## 摘要

审图人的核心判断不是"图不够好看"，而是这套图**没有形成可以核验的证据链**：房间、板边、门口不在同一套边界上；下层有楼梯不等于每一层都能到达和离开；房名不是功能证明；厕所只是一块面积；图纸语言的错误不能用修画法掩盖设计缺项。42 条意见归纳为 6 个根因，每个根因都对应编译器里缺失或未到达图纸的一层数据，而不是某一张图的画法。本方案把这 6 个根因转成 4 个新契约（项目前提、单一边界、逐层可达矩阵、证据图纸）和 3 条约束规则，按审图人给的返工顺序分 6 个阶段实施，并规定每个阶段的反例测试与"任意模型都能出证据"的验收标准。方案不修这一套图；实施后任何一次编译都会自动产出报审所需的证据图纸和逐条回复表。

## 1. What the review says, and what it was looking at

The reviewer's frame is stated on page 1 and page 13 and is the frame this plan adopts:

> 本层使用空间 → 实际门口与平台 → 有身份的楼梯／所需无障碍设施 → 真实服务层 → 出口排放与场地终点。

A set is reviewable when every level can show that chain, when every room has one boundary and one declared use, and when every line on a sheet has one identity. The 42 items grade themselves honestly — three are visible contradictions on the page (R2-13 door arcs, R2-16 south rooms over the raked edge, R2-21 SEMINAR over the rotated edge), thirty-one are missing evidence, eight are drawing language — and the reviewer says explicitly that none of the 42 is a confirmed code violation and that IBC 2024 / 2010 ADA are conditional references because no jurisdiction was given.

Two facts about the input matter for what follows:

- **The nine PNGs predate the R1 source fix.** They were rasterised on 2026-09-04 00:35 from a compile of compiler ≤ 3.2 (the theatre fixture `building-v3-a1c6a17feec8`). Commit `109e1a8` (compiler 3.5.0, `docs/implementation/redline-r1.md`) landed on 2026-09-05 and already changes the model behind R2-13, R2-16 and R2-21: bands fit the rotated plate exactly, doors swing a quarter turn, `SP-ROOM-OUTSIDE-SUPPORT` measures every room against its floor. The reviewer's manifest (page 17) says it did not assume any repaired version. So the three 图证 items are answered at the model level, and **not one of them is answered on a sheet**, which is the reviewer's actual point.
- **Most of the evidence the reviewer asks for already exists on the model and never reaches a drawing.** `portals` measures every door's aperture and both landings; `life_safety.navigation` walks measured routes; `room_layout_plan` places sanitary fixtures, seats, wheelchair positions and service reservations; `archetype` derives the bowl and its sightlines; `transfer_structure`, `hall_enclosure`, `site`, `codes.JurisdictionProfile` and the release manifest of decision 0019 all exist. `drawings.py` reads geometry only. The set the reviewer saw was a picture of the model with the model's own evidence left in the payload.

The conclusion is architectural, not cosmetic: the drawing set must become a **projection of the reports**, and the compiler must carry three things it does not carry today — a premises object, boundary identity, and a per-level access record.

## 2. Six root causes behind forty-two items

| Root cause | R2 items | Exists today | Missing |
|---|---|---|---|
| **A. No project premises object.** Jurisdiction, code edition, occupancy classification, construction type, sprinkler status, site datum and height basis are scattered or unresolved, and nothing prints them. | 01, 02, 03, 04, 31, 32 | `site.SiteParameters` (SourcedValue per field), `codes.JurisdictionProfile` (unresolved placeholder), `life_safety` `occupancy_group='unconfirmed'`, decision 0019 release ids | One `ProjectPremises` contract; a general-notes sheet that prints every premise with its provenance and prints *unresolved* as unresolved; an area/occupant schedule with stated bases; release id and issue purpose on the sheet |
| **B. Boundary identity is not carried to the sheet.** The plate edge, the weather line, the usable region, a void, and the projection of another level are all drawn as lines with no identity. | 06, 16, 18, 21, 22, 24, 25 | R1 containment (`program.level_bands`, `plan_regions.usable_region`, `SP-ROOM-OUTSIDE-SUPPORT`); `Lattice.carved`; `portals` landings; `hall_enclosure` | `LevelEnvelope` naming support edge / enclosure line / usable region per level; `VoidRecord` with kind, vertical extent and protection status; boundary role on every mark and a legend; locating dimensions for rotated plates; portal landings drawn |
| **C. Access is proven per core, never per level.** `core_anchors` knows which levels a stair serves; the allocator still places program on any `occupied` level; the drawing shows flights, never service. | 07, 08, 09, 19, 23, 26, 27, 34, 40 | `core_anchors` served lists, stranded-level refusal for the theatre carve, `portals` lift landings, `navigation` routes, `ada.RampPlan`, `life_safety` without fabricated discharge | `AccessMatrix` report (level × core: up/down/landing/door/passable), the rule *occupancy follows access*, life-safety plans per level, core and approach enlargements at 1:50 along the true flight, lift service table, discharge status stated as unevaluated until a site contract exists |
| **D. Use mode is not declared as data.** The theatre exists as a carve and a seating recipe; the sheet shows FOYER and CAFE and names nothing as the house. Service rooms are labelled rectangles although reservations exist. | 11, 14, 15, 17, 20, 26, 38, 41 | `archetypes` carve + sightlines, `room_fixtures` seats/sanitary/service reservations, `constitution` delegating fixture counts, `briefs` occupancy ids | `UseMode` on the typology kit and the cover; per-room occupant table with basis; function views declared by each `Carve`; fixture and service enlargements drawn from `room_layout_plan`; riser/shaft classification; ceiling and services zone shown in section as a reservation |
| **E. Closure systems are not registers.** Voids, guards, roof drainage, glazing, exterior stair support and details are single elements or nothing, never a list a reviewer can check line by line. | 18, 24, 28, 29, 30, 35, 36, 37, 39, 42 | `hall_enclosure`, envelope closure tests, railings emitted per open edge, elevation captions stating open faces (decision 0018) | Opening register, guard register (required edges vs emitted guards), roof plan with drainage derived from a datum or an explicit *not designed* statement, glazing/guard system schedule, exterior stair support references, detail index that says what does not exist |
| **F. Drawing language and issue management.** Grid-only dimensions, projection hierarchy without labels, no keys, no view references, model id where a release id belongs, PNG instead of vector. | 04, 05, 10, 13, 25, 33, 42 | Sheet system of decision 0018 (paper, numbering, title block, key plan, captions), vector SVG on disk, quarter-turn door arcs (R1) | Dimension chains grid → structure → wall → opening, projection tags, element/material keys, section and detail callouts with sheet numbers, release id in the title block, vector PDF export, elevation depth layering |

Every root cause is a missing *contract*, and every one of the 42 items closes through a contract rather than through a change to one drawing. That is the reason this document is a decision and not a fix list.

## 3. The architecture

Four additions and three rules. Names are proposals; the fields are the point.

### 3.1 `ProjectPremises` — the sheet a reviewer reads first

`backend/app/premises.py`, one object carried on `BuildingModelV3.premises`:

- location and site datum (from `SiteParameters`), adopted building code and edition, adopted accessibility standard, occupancy classification per space type, construction type, sprinkler and alarm status, mixed-use strategy, height basis (grade plane vs roof datum), area basis (gross / net / occupant-load area), issue purpose.
- every field is a `SourcedValue`; `llm_proposed` and `code_lookup` are never strong enough to design on (decision on `site.py` stands); a missing field is `unresolved`, printed as such, and every check that depends on it stays `unevaluated`.
- consumers: `codes` (replaces the placeholder profile when resolved), `life_safety` (occupancy group, sprinkler), the cover, the closeout table.

The general-notes sheet **A-001** prints the object verbatim with provenance, so the reviewer's first question (R2-01) is answered by a sheet that cannot claim more than the object holds. This is the direct generalisation of the site rule already in AGENTS.md: a value nobody reviewed cannot become a design value, and now it cannot become a printed one either.

### 3.2 Boundary identity — one line, one meaning

A `LevelEnvelope` per level, derived from what the lattice and the envelope already know:

- `support`: the plate polygon (what carries load, the line `SP-ROOM-OUTSIDE-SUPPORT` measures against).
- `enclosure`: the weather line, from the envelope stations, or `None` with a reason on an open face.
- `usable`: `plan_regions.usable_region` (support minus voids minus cores minus reservations).
- `voids: list[VoidRecord]` — each opening in the plate with `kind` ∈ {atrium, stair_well, lift_shaft, service_riser, auditorium_volume, courtyard}, `level_span`, `guarded` (measured from emitted railings), `protection: 'unevaluated'`. The carvers (`archetypes`) and the core layout already know which void is which; today they hand the lattice bare polygons.

Rules the boundary layer enforces, each as a counterexample test:

- rooms ⊂ usable ⊂ support (R1 holds the first; the second is new for enclosures that cantilever past the plate, which must name their support or fail).
- a door on a boundary is drawn only where `portals` reports both landings supported; otherwise the opening is drawn as an aperture with an unresolved tag, never as a swinging leaf.
- a plan mark carries a `boundary_role` (`support_edge`, `enclosure`, `void_edge`, `projection_above`, `projection_below`) and the sheet prints a legend and a tag on each line class; the dashed outline of the storey above is captioned with that storey's id.
- a rotated plate is dimensioned from a fixed datum: corner coordinates, rotation angle, and core-to-edge clear distances, not only grid intervals.

### 3.3 `AccessMatrix` — occupancy follows access

`backend/app/access.py`, carried on `BuildingModelV3.access`:

```
level_id | kind | served_by: [{core_id, kind: stair|lift|ramp|entrance, up, down,
            landing_id, portal_id, passable, status}] | entrances | discharge | occupied_program
```

- rows are derived, not declared: from `core_anchors` served lists and landing ids, from `portals` (`kind='lift'` and entrance portals with `passable`), from `navigation` routes reaching each landing, and from `ada.RampPlan` for the approach.
- `discharge` is `unevaluated` until a site contract exists (`life_safety` already refuses to fabricate it); the matrix prints that word rather than a blank.
- **Rule: occupancy follows access.** A level with no verified stair service cannot receive occupied program. The allocator takes `served_levels` from the matrix; a level nothing serves keeps its plate and is recorded with `access_status='unserved'` and the reason, and the cover's level table prints it. The theatre-carve refusal already applies this for one case; the rule makes it general. A level's `kind` stays as it is, because too many consumers read it; the matrix is the authority on service.

Sheets the matrix drives: **A-4nn life-safety plans** per occupied level at 1:200 — measured routes with their lengths, portals with pass/fail, exits with core ids, `unevaluated` printed at every discharge; **A-5nn core enlargements** at 1:50 — plan and a section that follows the flight (the section frame already accepts any bearing; the enlargement adds a plane per flight through its centre-line), with UP/DN, riser and tread counts, landings, clear widths from the model; the lift with its service table; the approach ramp with its segment gradients from `RampPlan`.

### 3.4 Evidence sheets — the set as a projection of the reports

`drawing_evidence.py` beside `drawings.py`. An `EvidenceViewSpec` names a source report, a kind, a scale and a scope (`per_level`, `per_space`, `per_core`, `set`). Specs come from three places so that any model gets them without a person deciding:

- the compiler, for every model: A-001 premises, A-002 occupancy and area schedule, A-4nn life-safety plans, A-5nn cores and restrooms, A-7nn registers (openings, guards, roof drainage, glazing and guard systems, detail index).
- the typology kit, per archetype: each `Carve` returns `evidence_views` — the theatre's section on the stage axis through house and stage with the sightline rows, the museum's enfilade section, the library's reading-room section. A kit that carves without declaring its evidence view fails the kit registry, the same way a kit without a carver already does.
- the reports themselves: a report that produces findings declares how they are drawn (route as polyline, portal as aperture with side regions, reservation as hatched region, unevaluated as a labelled grey band).

Three properties hold on every evidence sheet:

- a mark drawn from a report carries the finding or record id, as building marks carry element ids, so the audit can count evidence marks the way it counts elements.
- a sheet cannot show a status a report does not hold; `unevaluated` is drawn, never omitted.
- the same `SheetSpec`, paper, numbering, title block and key plan of decision 0018 apply; the title block gains the release id and issue purpose from decision 0019's pointer, and `export_drawing_pdf` writes a vector PDF with searchable text from the SVGs (R2-05).

The Blender-side `ViewSpec` in `blender/render_model_review.py` is the presentation twin of this: same kinds where they overlap (`occupied_floor_slice`, `theatre_overview`, `portal_closeup`), so a reviewer can find the render of the sheet and the sheet of the render.

### 3.5 `CloseoutTable` — the reply the reviewer asked for, generated

Page 16 demands that every reply say what was done, on which sheet, closed by what evidence. `review_closeout.py` takes a review manifest (items keyed to root cause and evidence requirement) and fills each row from the model: report id and status, sheet number, measure, and `not produced by this compiler version` where the pipeline has no evidence. The table is a document that outlives the round: the R2 manifest is the first instance, an R3 manifest is the next, and no row is ever hand-written.

### The three rules, stated once

1. **A sheet claims only what a report measured, and the report id travels on the mark.**
2. **Occupancy follows access; use follows a declared mode.** No program on a level nothing serves; no assembly space without a `UseMode`.
3. **A boundary line has one identity, and the identity is drawn.**

## 4. Staging, in the reviewer's order

Each stage lists the modules it touches, the counterexample tests it adds (the R1 pattern: inject the failure, watch the rule fire), and the acceptance test, which is the same for every stage: **every model in the 20-recording corpus issues that stage's evidence without exception, and the closeout table has no `not produced` row for that stage's items.**

| Stage | Reviewer's group (p16) | Modules | Counterexample tests | Done when |
|---|---|---|---|---|
| 0 Premises | 01 确认项目与使用前提 | `premises.py`, `codes`, `life_safety`, `drawing_sheet` (A-001, A-002, release id), `review_closeout.py` | an unresolved jurisdiction prints *unresolved* and yields no `pass`; a proposed value cannot appear as a design value on the sheet; the closeout table refuses a hand-written status | A-001/A-002 issue for every corpus model; R2-01–05, 31 rows filled |
| 1 One boundary | 02 统一房间、围护和楼板 | `datums` (`VoidRecord`), `envelope`, `plan_regions`, `drawings` (boundary roles, legend, locating dimensions), `geometry_review` | an enclosure past its plate without support fails; a door on a boundary with an unsupported far side is drawn as an aperture; a projection line without its storey tag fails the sheet audit; a rotated plate without corner coordinates fails | R2-06, 16, 18, 21, 22, 24, 25 rows filled |
| 2 Every level reachable | 03 证明每一层能够通行 | `access.py`, `compiler_v3` (served levels into allocation), `drawing_evidence` (A-4nn, A-5nn), `ada` | a level with no stair receives no program; a lift without a passable landing portal is not service; a route that leaves the free floor is not drawn; discharge without a site contract prints *unevaluated* | R2-07–10, 12, 14, 19, 23, 27, 34, 40 rows filled |
| 3 Names become functions | 04 把房名兑现成实际功能 | `typology` / `archetypes` (`UseMode`, `evidence_views`), `room_fixtures` (already emits; drawings read it), `drawing_evidence` (A-6nn, restroom and service enlargements), `life_safety` occupant table | a kit without a use mode fails registration; an auditorium with no emitted seats reports zero fixed occupants, not an estimate; a restroom with no fixtures prints *not designed*; a riser drawn with a room door fails | R2-11, 15, 17, 20, 26, 38, 41 rows filled |
| 4 Closure | 05 闭合消防、防护与防候 | `registers.py` (openings, guards), roof plan derivation or explicit statement, glazing/guard schedule, exterior stair support references, detail index | an open plate edge above the fall threshold without an emitted guard is listed as required-and-missing; a void without a kind fails; a roof without falls prints *drainage not designed*; a detail index that lists a detail with no sheet fails | R2-18, 24, 28–30, 32, 35–37, 39, 42 rows filled |
| 5 Language and issue | 06 修复图纸语言与索引 | `drawings` (dimension chains, projection tags, keys, callouts, elevation depth classes), `export_drawing_pdf.py`, title block | a section mark without a sheet reference fails; a key without a schedule entry fails; the PDF carries searchable text at the sheet's paper size; every stroke width remains in the ISO series | R2-04, 05, 10, 13, 25, 33, 42 rows filled |

Stages 1 and 2 are the ones the reviewer says block substantive review; stage 5 is deliberately last, because the reviewer's last sentence is the rule: do not dress a set nobody can verify as a construction set.

## 5. Ownership and interfaces

The peer session owns the compiler's interior work — portals, navigation, room fixtures, transfers, hall enclosure. This plan reads their reports and asks three things of the compiler side:

- `served_levels` and landing ids from `core_anchors` exposed on the lattice or the model, so `access.py` does not re-run the core search;
- `VoidRecord` kinds set where voids are made (carvers, `_core_layout`, atrium seeding in `datums`);
- `UseMode` and `evidence_views` on each `Carve`.

Everything else in stages 0–5 is on the evidence and drawing side and touches the compiler only to consume.

## 6. What this decision refuses

- No code-compliance claim is produced. `pass` requires a resolved premise; everything else prints `unevaluated`. The reviewer's own grading is kept: a missing sheet is *missing evidence*, never *violation*.
- No jurisdiction is defaulted. The closeout table for R2 will show R2-01 and R2-31 as *unresolved by input* until a person sets the premises.
- Nothing is drawn that the model does not carry. A roof without a drainage derivation says so; a restroom without fixtures says so; a discharge without a site says so.
- No sheet is retouched. Fixing A-104 by hand closes nothing; the next compile would reopen it.

## 7. R2 traceability

| Item | Grade | Root cause | Stage | Evidence artefact | State on 2026-09-05 |
|---|---|---|---|---|---|
| R2-01 code premises | 待核 P1 | A | 0 | A-001 from `ProjectPremises` | premises unresolved; nothing printed |
| R2-02 area ≠ occupants | 待核 P1 | A/D | 0, 3 | A-002 schedule with area basis and occupant basis | occupant bases exist on `life_safety` nodes; no sheet |
| R2-03 no site plan | 待核 P1 | A | 0 | A-001 states site unresolved; site plan when a site contract exists | no site contract |
| R2-04 issue management | 表达 P2 | F | 0, 5 | release id, issue purpose, revision on title block | decision 0019 ids exist; title block prints model id |
| R2-05 PNG not reviewable | 表达 P2 | F | 5 | `export_drawing_pdf` | SVG vector on disk; no PDF |
| R2-06 L00 outline identity | 表达 P1 | B | 1 | boundary roles and legend; enclosed/open ranges | open faces captioned on elevations only |
| R2-07 stair to exterior | 待核 P1 | C | 2 | A-4nn routes and discharge status | discharge unevaluated by design; not drawn |
| R2-08 accessible approach | 待核 P1 | C | 2 | approach enlargement from `RampPlan` | `accessible_route` on model; no sheet |
| R2-09 lift service | 待核 P1 | C | 2 | lift service table; landing portals | `portals` lift kind; no table |
| R2-10 grid-only dimensions | 表达 P2 | F | 5 | dimension chains | grid strings only |
| R2-11 where is the house | 待核 P1 | D | 3 | `UseMode`; function section; house/stage labels | carve exists; not on a sheet |
| R2-12 doors on the edge | 待核 P1 | B/C | 1, 2 | portal-gated door symbols; side regions drawn | `portals` measures both sides; not drawn |
| R2-13 door arcs | 图证 P2 | F | done (R1) | quarter-turn arcs, no duplicate leaf | fixed in 3.5.0; not yet re-issued |
| R2-14 furniture vs routes | 待核 P1 | C/D | 2, 3 | routes on A-4nn; reservations drawn | `navigation` + `room_layout_plan`; not drawn |
| R2-15 plant/service rooms | 待核 P1 | D | 3 | service reservations and equipment envelopes drawn | `emit_service_room` reservations exist |
| R2-16 rooms over the raked edge | 图证 P1 | B | done (R1) + 1 | containment held; boundary identity drawn | containment fixed in 3.5.0; identity not drawn |
| R2-17 restroom placeholder | 待核 P1 | D | 3 | restroom enlargement 1:50 from `room_layout_plan`; *not designed* where empty | sanitary recipes exist; not drawn |
| R2-18 central rectangle | 表达 P1 | B/E | 1, 4 | `VoidRecord` kind and span; OPEN TO BELOW label | voids are bare polygons |
| R2-19 L02 access | 待核 P1 | C | 2 | `AccessMatrix` row; core enlargement | served lists in `core_anchors`; not exposed |
| R2-20 riser as a room | 待核 P1 | D | 3 | riser classification; access panel vs door | not classified |
| R2-21 SEMINAR over the edge | 图证 P1 | B | done (R1) + 1 | as R2-16 | as R2-16 |
| R2-22 doors on a moved wall | 待核 P1 | B/C | 1, 2 | as R2-12 | as R2-12 |
| R2-23 tower without a core | 待核 P1 | C | 2 | occupancy follows access; matrix row | theatre-carve refusal only |
| R2-24 multi-storey void | 待核 P1 | E | 4 | opening register | not registered |
| R2-25 rotated plate dimensions | 表达 P2 | F | 5 | corner coordinates, rotation, clearances | grid strings only |
| R2-26 L05 occupied but empty | 待核 P1 | C/D | 2, 3 | occupancy follows access; use per level | allocator places on any occupied level |
| R2-27 L05 access | 待核 P1 | C | 2 | as R2-19 | as R2-19 |
| R2-28 roof drainage | 待核 P1 | E | 4 | roof plan with falls or *not designed* | flat deck, no statement |
| R2-29 edge protection | 待核 P1 | E | 4 | guard register | railings per open edge; no register |
| R2-30 open vs glazed vs cutaway | 待核 P1 | B/E | 1, 4 | enclosure line per face; cutaway refused (R1) | captions only |
| R2-31 building height basis | 待核 P1 | A | 0 | premises height basis | roof datum only |
| R2-32 fire protection of steel | 待核 P1 | A/E | 0, 4 | construction type premise; protection schedule as unevaluated | `codes.gate_frame_fire_rating` placeholder |
| R2-33 elevation layering | 表达 P2 | F | 5 | depth classes: envelope, glazing, behind | depth bands only |
| R2-34 exterior stair tangle | 待核 P1 | C | 2 | approach and core enlargements along the flight | not drawn |
| R2-35 glazing and guards | 待核 P1 | E | 4 | glazing/guard system schedule | none |
| R2-36 weathering at setbacks | 待核 P1 | E | 4 | detail index stating absence | none |
| R2-37 entrance platform support | 待核 P1 | E | 4 | support references from the dependency graph | graph exists; not printed |
| R2-38 no functional section | 待核 P1 | D | 3 | kit-declared section on the stage axis | not declared |
| R2-39 fire boundaries | 待核 P1 | E | 4 | opening register with protection *unevaluated* | none |
| R2-40 stair clearances | 待核 P1 | C | 2 | core enlargement with r/t and headroom from `geometry_review` | headroom measured; not drawn |
| R2-41 clear heights and services | 待核 P1 | D | 3 | ceiling and services reservation in section | ceilings emitted; no reservation |
| R2-42 detail index | 表达 P2 | E/F | 4, 5 | detail index and view references | none |

## Verification of this document

This is a plan, so its verification is that its claims about the codebase are true on the day it was written: the module surfaces cited in §1 and §2 were read on 2026-09-05 (`portals.py`, `navigation.py`, `room_fixtures.py`, `life_safety.py`, `archetypes.py`, `codes.py`, `site.py`, `analysis_bundle.py`, `drawings.py`, `render_model_review.py`, `redline-r1.md`), and the PNG provenance in §1 comes from the file timestamps of the reviewed rasters against the R1 commit date. Each stage's tests are the verification of the implementation, and the corpus acceptance is the verification that the architecture generalises.
