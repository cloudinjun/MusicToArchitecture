# Small-site main chain

2026-09-08. V2 coordination / V3 change propagation. Repair work, not a promoted candidate.

## Ownership

- `ProjectBrief`: actual parcel <= 500 m², setback, facade reserve, room areas and circulation budget. Setbacks remain unreviewed studio assumptions.
- `ProgramVolumeModel`: free-XY composition, per-level unions, room owners, circulation carriers and roof control. Its grid registers geometry; it does not set the structural pitch.
- `world_xy_grid`: fixed world origin and pitches, independently serialized through `ProgramVolumeModel -> ProgramMassing -> Lattice`. The new legacy-layout adapter derives pitches from score datums. A differing explicitly supplied pitch is a design fixture.
- Shared compiler: reads those authorities, fits actual members against floor minus holes and core/opening keep-outs. Cores cannot re-phase an explicit world grid. Existing massings without that field retain their previous route.

## Implemented and verified

The independent regular nodes now reach actual column and grid-span beam emission. Frame sizing reads the same pitch. `test_world_xy_frame_integration.py` executes real sizing and structure emission, measures node coordinates and whole column footprints, verifies beam support IDs, and changes grid origin while keeping plates unchanged. This is an emitter-level test, not a complete building test.

`test_legacy_program_layout.py` exercises the public volume entry, actual inset containment, serialized room areas, deterministic output and registration round-trip. The normalized brief and original provider responses remain in `artifacts/skill_runs/2026-09-08-small-site/`.

## Integration findings

1. `frame-integration-01/building_result.json`: complete building compilation stopped at circulation carrier placement. Whole-building sampling missed a carrier sized for one core. The search now includes actual carrier-boundary contact events; complete-footprint checks remain.
2. `frame-integration-02/building_result.json`: circulation placement proceeds; roof containment rejects `STR-PRL-P00-B00`. The current roof connector algorithm joins neighbouring trusses across their overlapping Y intervals without proving the intervening complete purlin stays inside the non-rectangular roof union.
3. Roof connectors now use full-width, support-to-support containment. `roof-integration-01` passed that failure and exposed an entrance face narrower than the existing entrance requirement. Candidate face selection now applies that width requirement before the downstream threshold is built.
4. `entry-integration-01/building_result.json`: the complete compile finished in 13.79 s, but delivered 0 of 458 m² of requested rooms. Compilation completion did not establish architectural validity.
5. `owner-integration-01/building_result.json`: direct use of exact-area registered room owners improved delivery to 10 of 458 m² (one janitor room; 15 rooms unplaced), in 12.74 s. Spatial and dependency reports still failed. The theater sectional carve, room access, and full-height circulation remain unresolved. This is diagnostic evidence, not a candidate-ready result.

The bounded regression run on 2026-09-08 passed 16 tests across legacy layout, actual World XY frame emission, and roof spans. These tests do not prove that the whole small-site building works, or replace dedicated tests for the new direct-owner allocation path.

## Remaining architectural seams

- Boundary-intersection column candidates still do not drive members. Their registered nodes, edge beams and explicit transfer conditions must be consumed together; the planner's `supported` status is only geometric floor containment.
- Roof connector containment is repaired for the tested cases; complete roof coverage across disconnected truss spans remains unverified. Do not fill roof concavities or relax the containment gate.
- Full compilation now produces a diagnostic model, but it fails functional and coordination requirements. There is no new candidate-ready Blend, Rhino file or drawing set.

## Architecture-first work order

Per the user's direction, prioritize the interfaces that determine the whole building:

1. **Resolve space once.** The brief owns required areas; Program Volumes own room placement, sectional clearance and circulation reservations. Downstream allocation should validate those owners without silently repacking them into structural-grid bands. Preserve explicit rejection when an owner cannot work.
2. **Prove the spatial proposal before detailing.** Validate required rooms, connected room access, usable sectional voids, and stairs/lift landings serving occupied levels together. A geometric volume union alone is insufficient. Use a lightweight diagnostic path before paying for full member generation and exports.
3. **Coordinate systems against that proposal.** Keep the independent World XY frame; integrate boundary members and explicit transfer conditions. Roof and facade consume the same volume boundary, with only declared outboard offsets.
4. **Deliver only after the main chain works.** Run one complete small-site candidate, then verify student-level model-derived sections and native deliverables. Do not use facade element count or successful serialization as evidence of improvement.

Near-term progress is measured by required program delivered, occupied levels actually served, and cross-system geometry/dependency failures resolved. Additional report layers, styles, connection details, material polish and high-cost renders wait. Retain failed evidence; do not shrink requirements or weaken checks to improve these figures.

## Spatial-stage repair, 2026-09-08

`prepare_massing` now owns the common carve/core/allocation stage. Full compilation calls it; `run_small_site_study --spatial` inspects it without member emission. The study's `--compile` first runs this same stage and stops before detailed geometry when rooms are unplaced/short or public circulation is unresolved. The general compiler still supports diagnostic incomplete models; no acceptance status was changed.

Two upstream assumptions were corrected:

- The legacy adapter now reads the shared theater sectional height instead of reserving exactly one upper storey. This music/brief requires 9.2 m including floor build-up, reaching both L02 and L03. Rooms are assigned after those reservations. Upper airspace stays in the envelope; it is excluded from the gross **floor** area budget in both authoring and massing validation.
- The legacy carve guard required at least 120 m² of residual floor. For an authored Program Volume level, it now measures preservation of every non-clearance owner's complete footprint, including circulation. The separate connected-floor and public-route checks remain active. Unauthored legacy levels retain the original heuristic. Current regression tests check the coordinated fixture's connected residual floor and reject a cut through an authored room; they do not independently demonstrate a residual floor below 120 m².

`spatial-integration-01` delivered 50/458 m² at the shared spatial stage (1.72 s), before the residual-floor correction. `spatial-integration-02` placed the actual theater bowl and stage at 109.98/458 m² (2.12 s), with 14 rooms still unplaced and public circulation unresolved. Its `building_result.json` records `building_compile_not_run`; no detailed model or native artifacts were generated. This is improved spatial preparation, not a candidate-ready building or a whole-pipeline speed benchmark.

The next architectural defect is visible in the plan and route report: the fixed core carriers have no protected approach network reaching their south-facing doors and the separate room faces. Touching room volumes cannot supply that network, and tall-room airspace cannot act as an upper-floor bridge. Replace that upstream layout relationship before spending another full compile. Keep independent World XY framing and the unchanged 448 m² parcel/458 m² room brief.

Next work stays on these cross-system interfaces. Detail-joint refinement, cosmetic corrections, additional styles and expensive exports are deferred. `latest/` and Rhino acceptance are untouched.

## Authored circulation integration, 2026-09-08

The following changes close shared-authority seams without introducing another detailed generator:

- Program Volumes now declare stair/lift source carriers and a separate entrance carrier. Core centres resolve from those carriers; downstream placement does not independently guess them. The schema and browser types carry the same references.
- Upstream room placement and downstream public circulation share the orthogonal routing helper. The author reserves complete-width approaches, room branches, and connected ground-floor galleries/returns before allocating later rooms. Upper sectional airspace remains unavailable for walking.
- Exact authored rooms can share boundaries. Allocation no longer subtracts an extra corridor buffer around every such room; actual public paths still reserve their complete width and must avoid occupied rooms. Room areas remain unchanged.
- Non-ground rooms may try another permitted storey; available face spans supply area-preserving proportions. The structural grid does not repack these rooms.

### Scope and evidence

The original 448 m² narrow parcel with a 300 m² circulation budget was rejected by the explicit circulation reservation. Two declared diagnostic premises followed: a squarer 448 m² parcel with 380 m² circulation, then a 25 x 20 m parcel (500 m²) with 450 m² circulation. Both retain the 458 m² room brief, four floors and 900 m² gross-floor ceiling. They are agent-proposed study assumptions, not additional LLM-provider responses or music-only controlled comparisons. The source responses and each input patch remain archived in the run directory.

`circulation-integration-08` reached 407.99/458 m² at the shared spatial stage, with three unplaced rooms and an unresolved stage connection. This is an intermediate diagnostic result, not the current validated design. Subsequent arrival-clearance and gallery-connectivity corrections expose an upstream placement failure: current-source `circulation-integration-11` cannot place the 12 m² ground-floor fire-support room (`SP-FIRE`). Its 12.94 s authoring run stops before spatial compilation or member emission. This demonstrates a limitation of the current greedy proposal, not proof that the brief cannot fit any 500 m² parcel.

Current compiler-source fingerprint: `3faebdf8dbf75a0d2a930e506e925d7c3190b11a24307c7c316e0589e8c8c846`.

Verification: 91 targeted tests passed (core references, routing, exact owners, brief/volume contracts and semantics, actual World XY frame emission and roof spans); the six legacy-layout tests separately passed on the current source. These are bounded suites, not a full-repository pass. A broader circulation suite still reported `test_every_core_is_inside_declared_carrier_on_every_served_floor[PVG-SPLIT-BRIDGE]` failing for the second core; no baseline comparison establishes whether that defect predates this repair. Three incomplete semantic-export test fixtures were updated to include the actual model's optional `project_brief` field and now pass.

### Next architectural gate

Coordinate a whole floor's rooms and access together, with bounded reconsideration of earlier placements. A locally feasible first room currently strands a later mandatory room. Do not continue adding isolated dimension adjustments or infer parcel infeasibility from that greedy failure. Required rooms and connected circulation must pass the shared spatial stage before full structure, facade detailing, drawings or native exports are attempted.

Independent World XY boundary-intersection members and transfer conditions remain unfinished. No new candidate-ready `.blend`, accepted `.3dm`, or issued drawing set was produced in this phase; no current model was promoted.

## Group-level spatial decision and full compile, 2026-09-08

The next repair separates an author's spatial decision from a kernel's bounded search:

- `LegacyLayoutControls.room_groups` names rooms that share a width or depth in a strip. The author supplies room IDs, an axis and a reason, never emitted coordinates. The kernel computes the unchanged individual areas, checks every minimum dimension and reserves an independent approach to each member. Group members remain separate Program Volume owners. Unknown/duplicate owners, archetype owners and mixed level preferences are refused.
- `layout_search.search_layout` backtracks a room/group and its new routes as one transaction. It retains the initial backbone, deterministic best-depth partial output, named unresolved items and a strict candidate-batch node budget. The node budget is not a bound on all geometry operations or wall-clock runtime. Proposal enumeration is finite and capped per room/group per permitted level; exhaustion is not a proof of site infeasibility.
- No structural pitch, room area, setback or hard gate was changed to obtain a fit. A geometric-candidate helper was simplified to use one occupied union per shape search; the unused first-match wrapper was removed.

### Experiment results

`coordinated-layout-01` tested the ungrouped input with 64 search nodes. It exhausted the budget in 199.84 s without placing the ground-floor fire-service owner. This is negative evidence for relying on room-level backtracking as the fast default design strategy. Later unvisited rooms are reported unresolved; that does not prove those upper rooms cannot fit.

The explicit input `coordinated_group_premises.json` groups the 12 m² fire-service reservation and 16 m² refuse room in a shared-width strip. Both still need independent access and future service/public route and fire-separation review. All areas, the 500 m² parcel, four floors, setbacks, 450 m² circulation ceiling and 900 m² floor ceiling are unchanged from the preceding parcel study. This is an agent-authored coordination decision, not a new musical measurement or an automatic discovery of architectural intent.

`coordinated-layout-02` generated 57 volume rectangles in 6.09 s using 13 of 32 search nodes. The shared spatial stage took 0.16 s and delivered 457.99/458 m² with no unplaced or short rooms and no unresolved public-circulation connections. This demonstrates the bounded spatial repair; it does not establish lift access, complete structure or candidate readiness.

`coordinated-building-01` then compiled the same input through the full public compiler in 27.77 s after authoring/preflight. Its model is `building-v3-bd58bc820e26`. All rooms remain allocated. The 16 spatial violations concern conflicting walking surfaces at the podium/entry and public approach. Dependency checks fail for core-wall/floor/roof load paths and several facade returns; the transfer report says hall boundary piers have no base plate registration. The lift has no landing doors on the four occupied levels and the accessible entrance route remains unresolved. The organic facade's minimum-fragment gate fails and closure grammar remains unevaluated. The model's zero PV containment/collar findings do not cancel these failures. This is a complete diagnostic compile, not a coordinated building suitable for issue.

The bounded regression run passed 105 tests, including group area/minimum-dimension checks, deterministic room/route rollback, the real legacy public entry, World XY member emission and roof/volume contracts. A final identical-input compile after removing the unused helper is archived separately in `coordinated-building-02`: 6.21 s authoring, 0.16 s spatial preparation and 26.92 s full compilation, 5,089 elements, model `building-v3-833f74750ee1`, source `6f63cefda7ef332d5e8990b15f979de203f1069fc6781a2962024d8d388c3f05`. Its source remained unchanged during the run. All rooms remain allocated and the same 16 walking-surface violations, dependency failures and facade gate failure remain visible. The inspected plan/axonometric PNGs show Program Volumes only, not a review of the full physical model.

### Next main-chain work

Keep the now-complete spatial proposal fixed while resolving:

1. Registered boundary support stations and core foundations through the independent World XY frame and theater transfer chain; frame-to-soil continuity must be measured on actual elements.
2. One shared vertical/entrance access plan: lift landing approaches, grade/podium/floor datums and stair/ramp footprints. A room-route pass cannot stand in for a functioning lift or entrance.
3. Facade support continuity against that frame. Local fragments and presentation polish follow these interfaces.

No native export, Rhino acceptance or `latest/` promotion occurred. The full goal remains incomplete.

## Core-to-foundation datum repair, 2026-09-08

The compact grade/first-floor interval is 0.3 m, equal to the floor build-up. `_emit_core_walls` correctly emits no exposed wall in that interval, but previously skipped its raft too. The next storey's walls then referenced nonexistent `L00` wall segments. This is a datum/ownership defect shared by every low-entry model, independent of facade styling or room packing.

Raft generation now follows the first physically emitted core-wall interval. The raft top meets that wall's base; its bottom is the existing practice embedment relative to the lattice grade, not a world-Z literal. First jambs reference the real raft without a wall-piece suffix. The axis graph recognizes walls actually borne by footings, independent of their level label. Soil, foundation capacity and construction design remain unverified.

Same-input `core-foundation-01` preserved the exact Program Volume JSON hash (`6e93fd3890c0b77209647c1fee9734bf4ca8d83a5586c2ca3cbaacaa98ad1f90`) from `coordinated-building-02`. Authoring took 6.23 s, shared spatial preparation 0.16 s and complete compilation 26.92 s. Current model `building-v3-bbd0049e5820`, source `d7ec918ab8306a0ceffbc9d93917bb0b65e527843f9db6453ba2a49b541c39e3`; source unchanged during the run.

Two physical core rafts were added (total footing count 5 -> 7). Core-wall missing-support findings fell 10 -> 0, and core-wall soil-path failures 48 -> 0. Across the whole model, those checks still fail on 32 and 260 elements respectively; no aggregate pass is claimed. All requested rooms remain allocated. The 16 surface conflicts and other perimeter/transfer, lift, approach and facade limitations remain.

Verification: 42 targeted tests passed across physical core-footing contact/support IDs, compact and normal first spans, unchanged World XY registration, core frames, carrier references and roof spans. The existing full model test `test_cores_left_to_the_compiler_get_a_grid_drawn_to_them` also passed (22.75 s). No full-repository pass is claimed; native files and issued drawings were not regenerated.

Remaining frame root cause located for the next repair: `hall_enclosure.enclosure_geometry` brackets the hall with regular grid indices outside its extents, while `transfer_structure` assumes those outer stations have in-bound base support. An independent World XY grid can bracket the entire small parcel outside its boundary. Boundary intersections therefore need their own registered physical support stations and transfer endpoints; inserting their coordinates into the regular pitch or fabricating dependency IDs would violate the current contract. Lift landing approaches likewise need upstream reserved floor; a shaft carrier alone does not supply a lobby.

## Boundary station integration, 2026-09-08

`Lattice.world_xy_column_plan` now persists the station registry. `world_xy_frame.py` emits boundary columns by registry index, leaving the World XY origin, pitch and regular line arrays unchanged. Complete column footprints must fit each successive floor minus cores/openings; stacks stop at the first interruption. Overlapping discoveries are suppressed, with taller grounded stacks preferred. Boundary sections use catalogue designations but remain architectural conventions without calculated utilisation.

The stage order is regular beams -> boundary gap spans -> slab support collection. Boundary spans join real column tops on the original grid lines, fit the available floor and do not duplicate existing collinear beams. The registry's geometric candidates do not imply that every candidate was physically emitted or transfer-resolved.

Same-input diagnostic `boundary-frame-03` preserves the exact PV hash recorded above. It took 5.99 s for form, 0.16 s for spatial preparation and 27.31 s for the full compile; model `building-v3-5b5303b124f0`, unchanged source `211b5f4052cfdbce9acb0cb5613242724277ae983ce25e29e755f7be4bef22f8`. It adds 49 boundary column segments and 18 boundary spans. Independent checks of the serialized elements find zero same-level column overlaps and zero duplicated collinear primary spans. Twenty-one slab pieces reference boundary beams. Existing structural-element soil-path failures fall 260 -> 0; eleven facade returns still lack support chains. This is topology evidence, not foundation/connection capacity or proof that all required structure exists. The dependency report also downgrades 152 unsupported geometric relation claims to rule-placed relations.

Intermediate runs remain diagnostic: `boundary-frame-01` had 13 column overlap pairs; `boundary-frame-02` removed collisions but exposed a stage-order regression that left slabs without their new beam references. Neither is selected as a coordinated candidate. The corrected source passed 47 focused tests for station serialization, actual frame emission, upper retreats, beam-before-slab ordering, core foundations/frames and roof spans. The prior legacy full-model regression and TypeScript check also passed; no full-repository pass is claimed.

### Main-direction priority

Keep the fitted 500 m² parcel and 458 m² program fixed. Next close the hall transfer endpoints and shared vertical/entrance access reservation, then facade-to-frame hosting. The hall transfer report still fails; all four lift landing doors and the accessible entrance remain unresolved, alongside 16 walking-surface conflicts. These are cross-system interfaces and outrank panel fragments, furniture, material polish and construction detailing. No new architectural-family expansion or unbounded candidate search is justified by this repair. Native `.blend`, accepted `.3dm`, issued drawings and current-model publication remain outstanding.

## Coupled access experiment and runtime stop, 2026-09-08

Hall retrieval confirmed that geometry, roof reactions, transfer planning and emission all assume Cartesian regular-grid indices. Replacing only one endpoint coordinate would leave the other consumers naming the old piers. No hall generator was changed in this phase; the missing station-to-reaction-to-element interface remains a main architectural repair.

The lift experiment reserves shaft and landing together before rooms, with the landing directly on the public spine. Three isolated placements failed: west core front (`lift-backbone-01`, 156.69 s, dressing room stranded), inside the core pair (`02`, 1.40 s, loading room stranded), and east core front (`03`, 160.49 s, dressing room stranded). Later unvisited rooms are listed unresolved, not proven infeasible. Those experimental source versions are not current defaults and no failed layout reached building emission.

Current `LegacyLayoutControls.lift_layout='core_front_inner'` exposes the coordinated assembly as an explicit experimental input. The default `legacy_rear` preserves the earlier diagnostic proposal, including its known unresolved lift; it is not a service claim. `coordinated_lift_premises.json` also moves the core pair outward as one backbone choice, retaining every room area/minimum, parcel, setback and budget. This fourth source-repair probe (`lift-backbone-04`) still failed to place the service group. It is negative evidence: adding a landing and moving cores alone does not coordinate the whole floor. Stop isolated relocation probes; next author the core/lift/landing and neighbouring service rooms jointly.

The search now has a **20 s cooperative room-search budget** alongside its node budget. Checks occur inside rectangle and route enumeration, including while an iterator has not yet yielded a node. A timeout preserves the deepest complete room/route transaction, distinguishes time exhaustion from node exhaustion and retains unresolved rooms. It cannot produce a candidate or continue to structure/export. This is not a hard process deadline: initial backbone/ellipse preparation and a single geometry operation are outside preemption; timed-out partial states are diagnostic and not promised byte-identical across machines. Other geometry errors still propagate.

`lift-backbone-04` stopped at 21.02 s total, with 6/32 nodes and an explicit time-budget finding; no native export ran. Its premises differ from `01`/`03`, so these timings are not a same-input speedup benchmark. Verification passed 29 bounded tests covering existing volume/site/area contracts, partial lift reservation evidence, transactional timeout, error propagation and World XY integration. Tests of a retained lift reservation do not establish that every room fits or that a lift operates.

Compatibility was independently recompiled on the original grouped premises: `bounded-baseline-01`, model `building-v3-667ae09b3f15`, source `97c5988d0eee54127dc8093a4de480bb45dc1085e498ab64041d17f83f736e2a`, unchanged during generation. Form took 6.03 s, shared spatial preparation 0.16 s and full compilation 27.10 s. All 457.99/458 m² remain allocated. Hall transfer, four lift landing doors, entrance access, surface conflicts and facade support failures remain unresolved. This phase improves bounded failure handling and exposes the correct joint-layout responsibility; it does **not** improve the visible building or produce a new coordinated/native deliverable.

## Whole-group ordering closes the lift landing interface, 2026-09-08

The failed joint proposal exposed an ordering defect: a 28 m² service-room group inherited the search position of its first 16 m² member. A 22 m² foyer therefore claimed space before the larger group. Search items now sort within their preferred floor by the whole transaction's room area, with stable room IDs breaking ties. This preserves the existing area-first heuristic while making its unit agree with the room-group/route transaction; no extra placement coordinates or room reductions were introduced.

Keep `coordinated_lift_premises.json` unchanged for this comparison. `joint-backbone-01` passed form in 8.75 s but hit a floating-point core-face mismatch. Its calculated core extended outside the serialized face by only 6.0e-15 m². Core containment and pair overlap now use the existing core-site search's 1e-7 m identity tolerance; other callers of `_box_overlaps` retain their strict default. Tests retain rejection of real 1 mm plate intrusion and stair/lift overlap. `joint-backbone-02` is a second intermediate diagnostic, stopped on the same face identity issue at the adjacent shaft.

`joint-backbone-03` completes the public chain: 8.76 s form, 0.18 s spatial preparation, 30.13 s full compilation; 5,144 elements; model `building-v3-05231ae2fa55`; unchanged source `a0b5411ee4092973ba23786e47e4a2b384e3b5b75f0172b8a158c9a41bf3348f`. All 457.99/458 m² remain placed with no unresolved public room routes. PV hash is `629cb47400e23394cdf779ee297f43ac747ba7286fc0a98abddea51911b6c170`. The 500 m² site, setback/collar, room minima and independent World XY origin/pitches remain unchanged from the joint premises. The score/brief are the same Couperin source used in preceding studies; the core/landing arrangement is an explicit agent-authored coordination choice, not a new musical measurement.

Actual geometry and portal evidence now show four lift doors and four lift landings, L01–L04. Every landing-side approach has zero unsupported area and no clash; every shaft aperture is clear. The single schematic car is positioned at L01, so only its portal is a walking edge; upper shaft sides correctly remain non-passable in this snapshot. No four-floor operating/accessibility approval is claimed. The generated plan and axonometric PNGs were inspected as Program Volume evidence only, not as full-model renders.

The improvement is local and real, but the candidate is not ready: hall transfer still fails; the entrance ramp is unresolved; surface conflicts remain (16 -> 14); unsupported facade returns increase 11 -> 14. Those fourteen IDs are **all facade returns**, not car objects. Existing structural members retain a soil-root chain, while hall-cap absence is separately reported. Do not promote this run or describe the whole building as coordinated.

Verification: 30 targeted tests passed (39.86 s), including whole-group ordering, numeric core identity with millimetre counterexamples, existing layout/time-budget behavior and actual World XY frame emission. Next hold this joint spatial proposal fixed and close registered hall support/reaction endpoints, then entry-surface ownership and facade return hosting. No native export, Rhino acceptance or current-model publication occurred.

## Hall station → reactions → physical hosts, 2026-09-08

The hall no longer borrows out-of-volume Cartesian endpoints. `hall_stations.py`
registers boundary-derived axes alongside the unchanged World XY grid. The same
registry drives roof reactions, transfer nodes, catalogue piers and roof framing.
Pier profiles are checked through the intervening Program Volume sections; the cap
is clipped to its actual enclosing volume. Retained-floor edge supports have their
own continuous stacked-volume range, and reuse a coincident regular column identity
with its full tributary load instead of emitting a duplicate column.

`hall-stations-03` holds `coordinated_lift_premises.json` fixed. Its Program Volume
SHA remains `629cb47400e23394cdf779ee297f43ac747ba7286fc0a98abddea51911b6c170`,
identical to `joint-backbone-03`: 500 m² parcel, 457.99/458 m² rooms, four occupied
floors and unchanged World XY origin/pitches. Form took 8.54 s, spatial preparation
0.17 s and building compilation 30.40 s. Model `building-v3-45468e1c3d24` has 5,201
elements; source `7bc3f5de80c041fe59fe1708dc998ef07fc7c536d5280bbd0f7ea1d0ec908fcf`
remained unchanged during generation.

Two calculated transfer frames, actual boundary piers, 29 hall framing members and
two missing-cap roof pieces now emit. Measured uncovered hall area falls 21.838 →
0 m². Reference integrity, member-end contact and structure-to-soil topology pass;
an independent pairwise physical-column projection check finds zero same-storey
overlaps. These checks do not prove foundation, connection or lateral capacity.
The matched X=13.471 m sections in `hall-stations-03/section_comparison/` are direct
model cuts, visually inspected. Their manifest names both source model hashes.
The new transfer and its continuous boundary piers are visible below L04. They are
diagnostic sections, not issued or accepted Rhino drawings.

Negative evidence is retained: `hall-stations-01` still rejected an out-of-volume
retained-edge pier; `02` emitted the cap but duplicated four existing column
segments. `03` resolves those duplicates. The whole candidate remains incomplete:
26.717 m of hall wall heads lack measured closure (44.333 m before); 14 entry/podium
surface conflicts persist; 20 facade returns lack support chains (14 before this
repair). The entrance ramp remains unresolved. No native file, Rhino acceptance,
student-detail readiness promotion or `latest/` update is claimed.

The source passed the 12 structural-capability tests, including both real-track
hall fixtures with full member-footprint checks; TypeScript also passed. The
bounded hall/station/World XY suite passed 36 tests, including the shared-column
identity regression. Next close the shared wall-head/facade host boundary and
entry-surface ownership, keeping this spatial proposal fixed; do not polish panel
fragments or add construction details before those interfaces work.

## Envelope boundary interface checkpoint, 2026-09-08

The envelope emitter now consumes inner weather rings as well as the exterior
ring through the same selected grammar. Level returns read actual hall caps in
addition to floor slabs. A short edge return can declare direct attachment only
when it shares a real vertical face with a slab/cap and its whole footprint stays
within the declared collar reach. Attachment capacity remains unverified. Nominal
boundary intent remains separate from actual bearing geometry: a missing slab
piece must not manufacture a new facade boundary.

`enclosure-interface-03` completes the public diagnostic chain with unchanged
production source `e86ab1f369212558f6a94f238eb3708f4daf5540b46e4f0e1b478129b119b096`.
Model `building-v3-0a985f88f5f6` contains 5,309 elements. Form/spatial/building stages
took 8.61/0.17/30.58 s. Program Volume SHA is still
`629cb47400e23394cdf779ee297f43ac747ba7286fc0a98abddea51911b6c170`;
the 500 m² parcel, 457.99/458 m² program and independent World XY grid are unchanged.
Unsupported envelope assemblies fall from 20 to 6: five head-return panels and
one closure member. This is partly corrected host attribution and partly newly
emitted inner enclosure, not twenty physically rebuilt connections.

The roof remains fully covered in the hall report, but measured open wall heads
remain 26.717 m. Fourteen walking-surface conflicts and the inaccessible entrance
remain. The axis report also retains 13 disconnected boundary-column axis records;
passing structure-to-soil dependency topology does not close that separate check.
The full model has not received visual review or native export in this checkpoint.
No candidate readiness, student-detail readiness, Rhino acceptance or publication
is claimed. The 121 focused envelope/control/hall tests pass, including courtyard
orientation and continuity, actual cap bearing, and rejection of corner-only,
overlong and vertically separated direct-host claims.

Per the user's main-direction priority, stop individual panel repair at this
checkpoint. Next work is limited to two whole-building interfaces: (1) shared
enclosure/cap boundary ownership and physical closure; (2) grade, entry platform
and occupied-floor access as one assembly. Recompile and compare whole-model
views after each interface change. Keep remaining findings visible; defer detailed
fasteners, furniture, decorative refinements and additional style families.

## Parcel reaches site construction, 2026-09-08

The upstream parcel/offset/massing check was real, but `_emit_site` still used a
150 x 130 m display earth patch, a first-floor outline expanded by 4.5 m, and three
fixed background steps. Those objects did not read the brief parcel. The actual
public stair and fallback access stair came from a separate circulation emitter.
This was a downstream contract gap, not evidence that the brief permitted more land.

`lattice_for` now carries the normalized brief parcel as `Lattice.site_boundary`;
the existing World XY and Program Volume registrations are unchanged. A bounded
site emits earth and paving within that boundary, from the ground datum. A floor
whose underside reaches grade and its arrival landings own their footprint, so
the same place is not also outdoor paving. Ground under genuinely lifted floors
is retained. Old inputs without a parcel keep their explicit legacy display path.
No fixed display steps emit on the bounded path. The public entry is still the
circulation assembly's responsibility, not a replacement decorative site stair.

`PV-CIRC-SITE-CONTAINMENT` measures full physical bodies of the emitted exterior
approach, including rails. Being an exception to the internal PV check gives no
permission to cross the parcel. Missing geometry stays unevaluated. The check
does not clip flights, certify accessibility, or waive any existing failure.

Same-input `site-boundary-01`, model `building-v3-4b56c662841a`, compiled with
unchanged source `b4de0bade910cfd47edd15ce41879f357a2b89d1ca16a7aa348b350cd3323933`:
8.68 s form, 0.17 s spatial, 31.18 s full building. Exact PV SHA remains
`629cb47400e23394cdf779ee297f43ac747ba7286fc0a98abddea51911b6c170` and all
457.99/458 m² rooms remain allocated. Earth projection now measures 500 m²
(old display patch 19,500 m²); exterior paving 160.628 m² (old plinth 804.290 m²).
Walking-surface conflicts fall 14 -> 4 with the checker unchanged. The remaining
four concern the public stair/landing assembly, not first-floor paving ownership.
Six unsupported envelope assemblies, the hall wall-head gap and the inaccessible
entrance remain. A new measured failure names 40 exterior approach parts leaving
the parcel, with 4.512 m² union outside. No existing stairs were truncated to pass.

Matched full-height model sections at world Y=10.43 m, bearing 0 degrees, share
extents and scale in `site-boundary-01/section_comparison/`. Both PNGs were visually
inspected; the unchanged building and the now-exposed out-of-parcel entry are
visible. This revision corrects boundary authority and exposes a real defect; it
is not selected as a visually improved, coordinated or deliverable candidate.
The manifest binds both model hashes and confirms unchanged production source.
100 focused tests plus seven existing circulation-family/rotation/fallback tests
pass, and TypeScript passes. No full repository pass or native export is claimed.

### Next architectural repair: reserve the arrival before rooms

The room-layout backbone currently reserves the inner entry carrier, then the
downstream approach derives a ceremonial stair of at least 4 m depth regardless
of the available parcel. For this entry, only 1.75 m lies between its PV boundary
and the west parcel edge. A three-stage cascade climbing 0.3 m also overlaps its
own intermediate landings. Panel-level or tread-level patches will not resolve
that mismatch.

Move ownership of the complete arrival assembly upstream: parcel + entry datum
-> stair/ramp/landing feasibility and reserved exterior region -> circulation
backbone -> room placement -> frozen assembly consumed by the compiler. The
reservation must account for complete landings and the weather offset, connect
to the public spine, and leave the selected program areas/minima unchanged. A
family that cannot fit must return an explicit candidate decision before full
building emission. Do not move the parcel, silently lower the brief, clip a ramp,
or keep an unfit fixed cascade merely because the style named it. Preserve the
three families where their complete geometry fits; use a bounded whole-assembly
choice for compact arrivals. This is the next main-chain task, ahead of detailing.

### Whole-arrival and shared-public-floor implementation

`shared-arrival-05` now carries the whole low-rise stair/ramp/landing/gallery
assembly through the PV entry station before room search. The bounded legacy
controls expose `arrival_layout=west_forecourt` and
`foyer_layout=hall_front_shared`; these remain explicit agent-authored test choices.
`shared_route_volume_ids` names the public carrier/connector claims a circulation
room may share. Actual core, void, archetype and other-room exclusions remain
unconditional; category alone grants no sharing. Final room branches are registered
with the commons after backtracking. The 22 m² foyer keeps its exact rectangle and
reaches a stair through the measured public network. The freed east pocket holds
the 12 m² dressing room. All 457.99/458 m² program is delivered.

Whole-floor connectivity is now checked during upper-room proposals when the
theater clearance is detached from the backbone. Exact union rings drop redundant
collinear vertices so one physical entry face can span a room/spine seam without
moving its geometry. World XY origin and pitches remain unchanged.

The final model `building-v3-17ed7fe2ccb7` has 5,175 elements; generation takes
7.63 s form + 0.17 s spatial + 30.06 s building with unchanged fingerprint
`54f3731a62a79042ced46470f53f45780939974a90a1f637968759bee8f13d16`.
Emitted approach containment changes from 40 off-parcel parts to zero, and the
ramp's evaluated geometry checks pass. A real-flange/roof-underside contact check
replaces an axis-crossing surrogate that rejected a supported narrow infill; no
unbacked support or no-contact exemption was introduced.

Matched whole-model sections were inspected and hash-bound. This is **not selected
as candidate-ready**: no facade entrance portal is emitted; the complete arrival
claim has not reached site paving, and walking-surface findings change 4 -> 5.
Primary core/carrier containment still fails, five envelope returns lack structure
paths, and hall wall heads remain open. The detailed run report lists verification
scopes, including one failing split-bridge core regression; no full-suite or native
delivery claim. Next main-chain work is the registered entry aperture and complete
arrival floor ownership across facade, site and circulation.

## 2026-09-08 — Site handoff closed; next work is whole-backbone placement

`shared-site-06` reads the same complete ArrivalAssembly footprint for volume
placement and site paving. Full compile: 5,173 elements, 28.69 s, all 458 m²
requirements fitted. Exact paving/arrival overlap changes 13.6343 -> 0 m²
within numerical tolerance; surface findings 5 -> 2. PV geometry and World XY
are unchanged. Diagnostic sections and physical measurements are hash-bound
in that run's `review/comparison.json`; no native or readiness promotion.

The entry aperture is still missing. Upstream checks clear width; the remapped
facade edge also needs jambs and loses frontage at the concave offset corner.
Two isolated frontage repairs were rejected (east gallery outside; subsequent
20 s layout exhaustion) and reverted. Do not expand search or trim program.
Coordinate arrival, foyer, theater plus galleries and protected cores as one
upstream placement before the remaining rooms. The success criterion is one
full model with emitted entry portal, retained room areas and core containment;
extra detail emitters and local surface-check refinements are deferred.

## 2026-09-08 — Shared prerequisites and a demand-scale gap

`joint-carriers-11` retains early exact-foyer reservation and candidate-level
theater gallery checks, replacing post-hall companion insertion. All 458 m²
requirements still fit in the full 5,159-element model. Core/carrier coverage
now uses the same 1e-7 m identity rule as core preparation: the earlier four
failures were reconstructed floating-point bounds, not actual relocation.
Counterexamples at 2e-7 m and 10 mm still reject. 32 focused tests passed;
entry portal, route continuity, surface/dependency and native delivery remain
unresolved. Matched sections are visually essentially unchanged.

Wider frontage trials `joint-backbone-07`–`10` failed within the existing search
limit and are not retained. Do not repeat their local tweaks. The next main
architecture issue is `ProjectBrief.resolved_spaces()` ->
`constitution.support_spaces()`: 212 m² explicit compact theater program receives
246 m² automatic support, including 60 m² mechanical, 40 m² storage and 36 m²
loading defaults. They are provisional placeholders and do not consume the
site/floor scale. Carry explicit small-project support assumptions and provenance
in the upstream brief, preserving required functions and showing the revised
schedule before placement. No silent allocator shrinking or compliance upgrade.

## 2026-09-08 — Compact brief reaches member compilation

`scheduled-compact-17` compiles all 309 m² requirements after explicitly proposing
97 m² support alongside the unchanged 212 m² primary program. Form preflight:
11.23 s; 61 Program Volumes, 87 World XY candidate stations. Full member model:
`building-v3-8574805cdd42`, 4,930 elements, 31.60 s member stage.

The main workflow repair is trial-level scheduling: a rejected proportion now
yields control instead of exhausting its private search before the next proportion.
Triangle meshes are deferred on strictly orthogonal routes. The changed order is
explicitly selected in the compact input; the legacy schedule remains the default
because the larger fixture regressed under the new order. Room-side landing wall
allowances now reach authoring as well as allocation. No budgets or gates relaxed.

The matched model-cut sections show changed upper setbacks, with broadly similar
stacked-frame expression. Missing entrance portal, two surface findings, dependency
failures and native/detail delivery remain unresolved. This proves V3 failure/recovery
and the support-sizing seam; it does not prove architectural readiness or diversity.
Evidence: `artifacts/skill_runs/2026-09-08-small-site/scheduled-compact-17/report.md`.
Next priority is the entry-station / offset-facade / supported-landing contract,
before local room tuning or new detailing scope.

## 2026-09-08 — Entry chain reaches the core

`core-interface-20` preserves the 309 m² compact brief and compiles 4,905 elements.
All six PV circulation findings pass, including portal attachment and a measured
2.95 m supported interior route to the primary core. Entrance and both ground-core
portals are physically passable; the 0.60 m navigation probe is not code approval.

The architectural changes are whole-union entrance capacity before room commitment,
shared with actual offset-facade registration; profile-aware compact-arrival rail
termination outside the landing clear region; and floor-owned core platforms,
independent of whether a short intervening flight is emitted. Core landing emission
and slab reservations consume the same served-level set. No room area, grid phase,
site boundary or quality gate was relaxed.

Same-input intermediate failures remain in entry-frontage-18 and entry-clearance-19.
Hash-bound before/after entry/core sections show the physical interface closure;
overall silhouette remains substantially similar. Two surface-height findings,
dependency failures, native/detail delivery and diversity remain open. Evidence:
`artifacts/skill_runs/2026-09-08-small-site/core-interface-20/report.md`.
# Saved-model delivery branch

`backend.scripts.package_candidate_study` connects a successful saved small-site
model to the existing drawing and native Rhino exporters without recompiling it.
Optional Blender export reuses the existing background adapter and requires the
workspace's explicit authorisation. A new output folder is mandatory; source drift
invalidates the delivery, stage failures remain independent, and acceptance is never
created. This is downstream packaging, not a second geometry pipeline.

The `core-interface-20/delivery-01` experiment produced nine A1 SVG sheets and
4,905 editable Rhino solids plus 61 PV reference bodies, with readback verification.
See its `delivery-review.md` for actual sheet observations, the failed Rhino GUI
launch, pending Blend authorisation and unchanged architecture failures. In
particular, the roof's 3.8657 m construction zone and persistent grid-like facade
deserve whole-form review before another local detail repair.
