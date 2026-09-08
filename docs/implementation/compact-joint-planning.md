# Compact joint planning

Separate repair following `diversity-22`. Evidence target: V2/V3, facade spatial
demand reaches upstream Program Volumes before detailed members are emitted.

`compiler_v3.plan_building_systems` is extracted from the existing compiler tail.
The public compile and proposal planner now share selection, capability screening
and sizing; no alternative selection matrix or relaxed sizing rule was introduced.
The function retains the existing process-local site-load context and is called
sequentially within a process.

`candidate_planning.plan_compact_candidate` runs actual volume authoring, shared
spatial preparation, then shared system planning and FacadeControl. Two proposal
rounds are permitted. If facade demand exceeds the arrival reserve or crosses the
setback polygon, a new proposal receives the resolved arrival allowance and a larger
inward facade reserve. Site geometry, setback, room areas, required dimensions,
floor count and gross-area ceiling remain unchanged. The previous proposal remains
in the evidence. A failed last proposal cannot return earlier volumes as its result.

`weather_plane_site_overflow` measures the actual setback polygon, including concave
boundaries. The final compiler invokes the same measurement and refuses overflow
before member emission. This closes a missing site-to-facade boundary check. It
checks weather planes only; complete outboard screens and physical thickness still
need their own emitted-body checks. Critical Regionalism's depth remains provisional.

`LegacyLayoutControls.hall_depth_position` adds an optional area-preserving main-hall
proportion proposal. Its range is derived from the brief's minimum dimensions and
the available plan span. The old deepest-fit mode remains default. The explicit
score-composition mode uses the existing confidence-clamped variation datum and
preserves unknown readings as fixtures. This is an unselected design hypothesis;
it does not release the fixed backbone topology.

Verification: 32 focused candidate/facade tests, 13 legacy-layout tests pass. The
earlier extraction-stage facade/massing suite passed 31 tests in 169.42 seconds;
that run preceded the new final site gate and does not verify the later gate.
The new gate has a direct test that ensures member emission is never reached after
weather-plane overflow. No capacity, site or professional approval was added.

Actual evidence is under `artifacts/skill_runs/2026-09-08-small-site/`:
`joint-planning-23/` retains initial diagnosis and rejected score-composition trial;
`joint-planning-24/carefree/planning.json` records both feedback proposals under the
final source fingerprint. No successful new full building or native export is claimed.

The next architectural repair is a small set of joint hall/backbone/arrival proposals
that can fit the real facade reserve. Do not pursue detail embellishment, randomly
seed more buildings, weaken the site gate or reduce declared room areas to make the
fixed composition survive.

The next checkpoint is `joint-planning-31/report.md`. The experimental rear-commons
path now keeps hall, galleries and upper clearances in a transactional search batch,
with cooperative work across two root proposals. Backbone and foyer remain fixed
before that search: the complete architectural joint planner is still incomplete.
Real facade-reserved runs remain unsuccessful; asymmetric-core/service-group trials
were not selected. This work supports workflow tests, not a candidate-quality claim.

## Terminal-based network and transactional budgets

`terminal-network-35/report.md` records the next two bounded architectural trials.
Authored stair run axes now propagate from Program Volumes through massing/datums
into core reservations and actual compiler geometry. The horizontal-core experiment
uses the same physical stair sizes and leaves the independent World XY grid intact.

The horizontal spine and hall returns now meet actual core-access terminals rather
than extending to the exterior core face. On unchanged inputs circulation fell from
504.213 to 457.196 m², still above the 450 m² brief. Floor/circulation union budgets
now reject whole room/route batches inside transactional search, with rejected
batches consuming the same node budget. Final checks use the same area measurement.

The latest partial proposal retains 282 of 309 m² authored room area and is missing
three owners after 32 nodes in 11.438 s. These are upstream proposal figures; no
new delivered-area or native-candidate claim is justified. The fixed rear core band
still dominates inspected views. Next work is joint core placement, functional
level distribution and route topology; more local coordinate trials or extra
detailing do not address that restriction. No promotion or acceptance was written.

## Shared access and joint occupied-level proposals

`shared-access-40/report.md` records a further architectural repair. The experimental
rear-commons path now prioritizes existing public-route frontages, interleaves
permitted storeys, and offers large program anchors to uninhabited sectional levels
before filling one storey twice. Whole-path checks retain connected volumes and
occupied-level owners; registered connectivity uses export's existing 0.1 mm grid.
No room area, route width, site boundary or search budget changed.

Core facing now checks the actual supported approach against cores/lift/carved
floor, and preplaced archetype terminals use exact PV owner bounds instead of
rounded carve coordinates. The frozen first round allocates 308.99/309 m² with
zero unplaced/short rooms and an empty public-circulation unresolved map in 4.132 s.
Its circulation union is 425.049 m² against the unchanged 450 m² budget.

The real facade demand still rejects that round: 1.11588 m required offset exceeds
the proposed 0.4 m reserve. A second upstream proposal inside the smaller domain
fails the whole hall in 0.477 s. No detailed model/native export follows, and no
earlier volume is returned as the final candidate. The next missing composition
decision is entrance/hall/core placement under the actual facade demand. The fixed
rear core band, diversity, student details and complete native delivery remain open.

## Architecture checkpoint 48

`architecture-checkpoint-48/report.md` supersedes the last feasibility observation.
Arrival side selection now protects the existing backbone, and exact-area room contact
reuses measured full-width public landings. The final 1.11588 m facade-reserved baseline
allocates all 309 m² briefed rooms (308.97 m² registered), compiles and exports a Rhino
candidate plus eight A1 SVG sheets. Circulation union falls from 434.1465 to 405.1474 m².
Spatial checks still fail and two joists are explicitly withheld pending replacement
framing; there is no candidate selection, accepted Rhino or completed Blender delivery.

The opt-in `distributed_cores` composition turns the second full stair along the east
side and routes hall galleries to public terminals. It remains an unselected experiment:
all five whole hall proposals in run 47 already exceed the unchanged 450 m² circulation
budget. It is not a score-selected branch or evidence of diversity. Next work must
jointly place core access, foyer and entry; do not continue detailed member embellishment
or multiply fixed backbone presets. Read the checkpoint's actual sheets and failures.

## Localized hall access 53

The distributed-core experiment now reuses the common full-width room connector
instead of requiring two complete end galleries. Catalogue-sized hall bearings remain
independent; no physical containment, door or egress gate changed. Compatibility rear
layouts and the general legacy cell-gallery path retain their previous behavior.

On unchanged run-50 controls and the final facade-reserved brief, run 53 completes
all room allocation in 2.330 s (308.97/309 m², no short/unplaced rooms). Run 51 with
mandatory galleries timed out at 20.441 s with only 160 m² authored. This is useful
placement evidence, not readiness: both theater owner routes remain unresolved.
The author connects arbitrary usable faces while the compiler reads separately chosen
terminal points. Unify that access interface next; do not add fixed layout presets or
pay for detailed exports before the shared preflight closes. Exact provenance and
limitations are in `localized-hall-53/report.md`; no candidate is selected.

## Shared owner access 54

`room_access.py` now provides terminal positions and front-aisle bounds to both
upstream layout and downstream compiler/floor readers. On the same controlled input,
all rooms, preflight public routes and facade-site checks pass in 4.940 s. The full
27.40 s compile emits 5,453 elements and is retained with a Rhino candidate and eight
A1 diagnostic sheets in `shared-owner-access-54/`. Internal-solid containment is zero,
but physical navigation still fails; no candidate is selected or accepted.

The next root cause is explicit: the partition emitter ignores the foyer's named
shared-route relationship and closes the auditorium approach with foyer walls.
Read `shared-owner-access-54/report.md` for measured body IDs and retained failures.
Project shared-route ownership into partition boundary identity next; do not nudge
individual doors or confuse preflight connectivity with an operable built route.

## Shared boundary 55 and architecture diversity 56

The partition emitter now reads explicitly named shared public-route boundary
intervals for unrated circulation owners. Full replay 55 retains exactly the same
serialized Program Volumes as 54; sampled navigation failures fall from 65 to five
foyer samples. Two ramp-flush findings and three unverified upper lift portals remain.
Native Rhino and eight diagnostic sheets were exported, but no candidate is selected
and no Blender/accepted-Rhino claim is made. Fifteen focused boundary/emitter tests
passed; the broad partition regression finished with 53 passed and two door-description
assertion failures in 906.54 seconds. The tests expect clearance/rated-self-closing
claims where current output records unverified performance. Do not insert unsupported
claims to make those assertions green. See `shared-boundary-55/report.md` for identities
and exact test names; historical attribution remains unestablished.

Four-track replay 56 holds the 500 m² site, 309 m² theater brief and distributed-core
controls constant. All four spatial preflights pass. Normalized pairwise level-union
differences are nonzero, but the inspected massing previews retain one recognizable
composition. This is insufficient evidence of significant architectural diversity.

The source boundary matters: `organize_program_volumes` returns through the bounded
legacy author whenever `project_brief` is present, before calling the score-driven
`choose_program_volume_grammar`. The bounded author fixes the backbone's parcel-side
relationships, keeps the auditorium/stage pair on the ground, assigns other rooms by
program preference and area load, and uses variation chiefly for room aspect ratio.
The explicit test pins compound that limitation. No claim is made that all legal
layouts are identical.

Prioritize a bounded, score-driven whole-layout decision surface with joint core,
hall, route and room feasibility. Preserve exact room areas, site reserve, independent
World XY structure and shared PV ownership. More seeds, global transformations or
local detailing cannot stand in for that repair. Keep the lightweight four-track
comparison before paying for multi-track native exports. Evidence:
`architecture-diversity-56/{report.md,experiment.json,diversity.json}`.

### Next source repair boundary (not implemented)

Run `score-composition-59/report.md` tests the existing musical hall-proportion
control under actual facade feedback. Three of four preflights fit; Night in Venice
needs a 1.23046 m facade reserve and then leaves its 8 m² refuse room unplaced.
Requested depth positions span 0.3033–0.8709, realized hall depth only 6.75–7.0215 m;
all eight previews retain the same root composition. This control is now tested and
insufficient: do not repeat its tuning as the next diversity repair. No compiler
change, candidate selection, native export or professional approval occurred.

`joint-root-61/report.md` records the first experimental root interface, exposed by
`plan_compact_candidate(..., joint_layout=True)`. Complete author calls now restart
with branch-specific hall/core/arrival stations. Existing default layout remains.
Both music-selected terminal relationships execute, but all four real runs fail:
three intersect the complete arrival reservation, and separated terminals exceed
the circulation budget (468.637/450 m²). Carrier overlap was removed between runs
60 and 61; ramp overlap remains. The general joint solver described below is still
incomplete. Next construct arrival before solving the actual residual polygon;
replace the inherited full side-gallery strip with real-terminal routing. Do not
promote this new interface or its unit tests as a feasible/diverse building.

`residual-root-63/report.md` supersedes the hall-domain failure: generated roots
retain hall area/proportion while the existing solver places it after subtracting
the complete arrival. Carefree and Funky Boxstep preflights fit; Couperin still
exceeds exact circulation union and Venice fails after actual facade feedback.
Carefree full compilation emits 6,711 elements but loses all four lift landing doors
and one facade-return dependency. No native export or selection follows. Next
propagate actual lift-door approach demand upstream into the shared entry platform;
do not claim the preflight has closed physical coordination or diversity.

The immediate implementation seam is the root of the bounded search. Today the two
cores, lift, arrival and foyer are all committed to `placed` before `search_layout`
starts; the solver cannot backtrack their relationship to the hall. Moving another
room preference will leave that limitation intact.

Make the complete dominant assembly a root proposal transaction: hall pair, complete
core reservations, lift, arrival, shared foyer and their real full-width connections.
Resolve stations from the hall and remaining parcel domain, rather than assigning
another fixed set of parcel-side coordinates. The score should express a spatial
relationship (concentrated threshold or separated terminals), while geometry decides
whether and where that relationship fits. Record both proposal and rejection; never
silently substitute a successful unrelated arrangement. Keep the theater's existing
longitudinal axis and independent World XY grid in the first repair to avoid coupling
this change to seat/carver orientation migration.

Verification must show the root can be rejected/backtracked as a whole; core sizes,
all room areas, accessible approaches and parcel limits remain unchanged; and two
score proposals change relative core/hall/route organization after global XY
normalization. Keep the existing explicit controls as reproducible diagnostic pins.
The four-track preflight remains the first output gate, followed by complete emitted
geometry checks for any candidate entering native delivery. This is planned work,
not evidence that whole-layout score ownership is already available.
