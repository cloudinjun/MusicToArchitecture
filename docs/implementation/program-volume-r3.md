# Program Volume R3 repairs

Status: R6 probes completed with closed hall roofs and activated transfers. R7 corrects
framing storey ownership and is running the four-track native/drawing closed loop.
This record demonstrates V2 coordination and V4 failure/recovery. It does not promote
the R2 artifacts or assert completion of the requested delivery set.

## Changes

- `approach.py` supplies one boundary-ramp planner to authoring and compilation.
  The common carrier reserves the smallest tested whole-grid width within the project
  approach budget. Frozen Couperin/Funky readings require three cells and now reach
  public circulation through the same station used by the ramp, stair, portal and canopy.
- Theater Program Volumes reserve the complete multi-storey section, including the
  raised stage. Owner-aware carving preserves the paired seam. Program stranded after
  the upper-floor cut moves with the intersecting group to restore a connected floor.
- Controlled facade mullions and screen fins retain emitter-declared supports in the
  dependency graph. Missing or non-contacting supports remain failed findings. Entrance
  brackets are checked against real slab material, including holes and elevation.
- Structural selection records `theatre_gravity_transfer` as a geometry-derived compiler
  requirement. Physical feasibility remains a separate domain. The current steel emitter
  supplies this capability; incapable caller pins fail before emission. A four-storey
  non-theater regression retains a music-driven glulam selection.

## Verification

- 139 passed: Program Volume authoring, semantics, diversity measurements, compiler
  capabilities, transfer mechanics and enclosure tests.
- 49 passed: axis skeleton, dependencies and High-Tech dependency regressions, including
  the seven previously failing entrance-bracket cases. Six pre-existing Shapely warnings.
- Nine focused cases passed after the final multi-storey clearance/stranded-room repair:
  all three theater owner grammars, both frozen arrivals and capability selection.
- TypeScript `tsc --noEmit --incremental false` passed.

Full-model probes consume the original R2 audio score records under
`artifacts/skill_runs/2026-09-07-pv-repair-r3-probes/`. These probes contain no native
presentation or accepted Rhino deliverable. Inspect their model and gate reports before
advancing to a new four-track drawing/render/Rhino candidate batch. Current-source
candidate fit, transfer sizing, sightlines, courtyard enclosure completeness and final
native deliverables still require that model-level evidence.

Probe generation-source fingerprint:
`15958502927684dfadc0ee195b0485368e8a014025aa8d2888cf976d43771f77`.

## Full-model findings

The Couperin probe completed in 859.02 seconds with 26,421 elements. All brief spaces
were allocated (`program_fits=true`, fulfilment 1.007); spatial, dependency and axis
reports passed, as did the four evaluated Organic facade gates. Those checks do not
close the candidate: transfer structure failed because no registered south boundary
pier existed, and five rear seating rows had no emitted seat pans.

Direct geometry inspection locates the seating obstruction at
`ENV-RET-L02-BASE-P000`: its horizontal spandrel occupies the row-7 footprint at
z=9.4457–9.5207 m. A floor-edge return had filled the authored sectional clearance.
Regression fixtures now exercise head and base returns through consecutive tall-room
storeys, including the actual bracket footprint.

The original union report compared gross envelope exterior with material floor after
an edge-connected section cut. Its 3,557.394738 m2 difference is retained as a descriptive
quantity. The corrected report also measures floor against upstream union minus
explicit `sectional_clearance` volumes. Downstream removals never authorize themselves;
deleting the clearance authority or restoring obstructing floor causes regression
failures. Three focused report tests pass.

A live stack sample of the Funky probe identified repeated contact-gap work inside
dependency compilation. A second sample showed progress into navigation. A bounded
contact regression reproduces 514 distance calls after contact is already established;
the intended optimization must preserve the bidirectional distance and current slack.
This is a measured kernel issue, not yet an end-to-end speedup claim.

The Funky probe completed in 1,129.65 seconds with 23,393 elements. Its complete brief,
spatial, dependency, axis and four International facade gates passed; the same missing
boundary pier and five rear seating-row failures remain in its archived R3 model.

## Follow-up source repair

- Base/head returns now subtract the actual host level's authored clearance, including
  the half-section exclusion for brackets. Both new failure fixtures pass.
- Contact-gap evaluation returns at its exact zero lower bound, visits the smaller
  vertex set first, and otherwise retains the same bidirectional distances/slack.
  Nine parity cases pass and the 514-call contact fixture now uses one distance call.
- Theater authoring fills absent north/south gallery cells beside the owner pair,
  preserving all existing room ownership. Two recordings across three grammars now
  have registered boundary-pier locations strictly inside the ground floor. The two
  selected terraced runs still fit the brief; this does not promote the other pins'
  unresolved allocations.
- Studies record the generation fingerprint, refuse stale/unrecorded-source reuse and
  abort completed-candidate claims when compiler source changes during a run.

Verification: 143 passed across volume, semantics, diversity, protocol, contact and
enclosure tests; 10 structural-capability tests passed; the additional source-change
guard test passed with the three protocol cases. The combined axis/dependency/circulation
suite and fresh full models remain running.

Follow-up probes: `artifacts/skill_runs/2026-09-07-pv-repair-r4-probes/`.
Generation-source fingerprint:
`231041c363a6dd575120475b66d55480530eeb694ef1c573f576173683f5f7e7`.
These are isolated compile probes, with no new Blender/Rhino acceptance or issued-set
promotion. Actual transfer sizing and seating recovery must be read from completed outputs.

## R4 precision counterexample and R5

R4 Couperin stopped at `ENV-RET-L03-BASE-P002`: opening a collar hole into simple
polygons created a 5-micrometre strip, x=-16.838800 to -16.838795 m, which collapsed
under the model's five-decimal coordinate registration. The companion Funky probe was
deliberately stopped before editing source; neither run is a completed candidate.

`_registered_return_solids` now rejects invalid input and non-degenerate registration
defects. It discards only a registered zero-area piece whose raw geometry is narrower
than the existing 10-micrometre model tolerance. Tests preserve representable strips
and still reject a crossing polygon. No automatic filling or geometry repair is enabled.

The actual R3 Couperin dependency graph was recomputed in 35.641 seconds and its complete
serialized result matched the stored graph exactly. That verifies optimization parity;
it is not a whole-building runtime comparison. A separate live sample exposed fixture
obstacle sweeps serializing every unrelated section profile for every member. The sweep
now reads only its named profile, with an explicit unused-profile regression.

Verification: 158 focused volume/contact/enclosure/capability cases and 23 room-fixture
cases passed. The longer axis/dependency/circulation suite remains in progress and began
before the final numerical/profile-only refinements. No native deliverables were promoted.

Current probes: `artifacts/skill_runs/2026-09-07-pv-repair-r5-probes/`, Couperin and Funky.
Generation-source fingerprint:
`a78cc8dae669e4b8960c190b1d0e37afd38e44328502d542d1b7ac7a8d0fb313`.
Both probes completed on that fingerprint. Couperin produced 29,412 elements in
453.00 seconds; Funky produced 26,283 in 484.45 seconds. Both deliver 504 ordinary
seats, two wheelchair positions and two companion seats, with no omitted seating
rows. Their complete brief, spatial/dependency/axis gates and four evaluated facade
gates pass. All five circulation findings pass, with eight ramp runs and nine landings.
Unclaimed floor difference is zero. Full swept-solid containment stays unevaluated.

Both retain a failed hall transfer: roof reaction integration omitted its west edge.
Their roofs and native/drawing packages are therefore not promoted as complete.
The long axis/dependency/circulation suite finished with 81 passed and six existing
Shapely warnings (848.43 seconds); it started before the final R5 numerical/profile
refinements, so this timing is not a final-source benchmark.

## R6 roof and transfer closure

The measured Couperin omission is 3.1903043115 m2 on the west wall-face cap. Load
integration now reads actual missing-roof bounds on all four grid edges and retains
linear overhang influence, preserving vertical force and both global first moments.
Four asymmetric/fragmented roof counterexamples verify those balances.

The uncovered load exposed a second defect: axial-only catalogue selection could stop
with excessive service drift. The existing linear truss now trials greater catalogue
area when its measured drift demands stiffness, re-solves the heavier members, and
keeps the same registered depth. This bounded uniform-stiffness trial is not a global
minimum-weight optimization. A catalogue-ceiling counterexample still fails service
drift even when every axial member is selected; independent re-solves verify actual
product weights, reactions and displacement.

Two frozen theater fixtures now prepare complete activated transfer plans with no hall
findings and no lattice changes. Full emitted geometry still requires the R6 probes.

Axis T-joint discovery now searches occupied endpoint buckets along its narrowest
indexed axis. The centimetre bucket envelope and 1 mm physical joint test are unchanged.
Exhaustive endpoint parity passes at three scales; a long 3-D diagonal regression
refuses any return to dense empty-space enumeration. The isolated unit suite passed
36 tests, plus five existing axis units. Full model parity remains under test.

R6 probes: `artifacts/skill_runs/2026-09-07-pv-repair-r6-probes/`.
Generation-source fingerprint:
`be61b2b8ddc35ce075cf19fbb1bad7fc1fa6de8041ab351159865cc976eb0446`.
Both R6 probes completed: Couperin `building-v3-07de87acb34d`, 29,935 elements in
218.57 seconds; Funky `building-v3-b230175aef84`, 26,794 elements in 237.75 seconds.
Both report activated transfers, zero uncovered hall area, zero open wall-head length,
no hall findings and no archetype findings. Brief, dependency, axis and facade gates
remain passed. These changed models are not an isolated performance benchmark.

R6 still fails Program Volume containment: 416 reference elements were tested against
the cap floor's retreating union although the framing occupies the storey below it.
The physical gate reports that same owner error. Direct solid measurements verify
the transfer parts against their actual vertical storeys; the rule was not waived.
The long R6 regression completed: 81 passed, six existing Shapely warnings, 393.43 seconds.

The four-recording, fixed-theater diversity screen was rerun on R6 under
`artifacts/skill_runs/2026-09-07-pv-repair-r6-diversity/`. All three grammars have four
distinct normalized shapes, zero exact/tolerance collision pairs and zero raw
collisions. All 12 signatures are distinct across the set. This measures form contracts
only; it does not establish visual quality, full-brief fit or native delivery readiness.

## R7 ownership and native delivery loop

Transfer frames, their posts/restraints and hall beams now register to the storey below
the cap datum. Report and support identities still name the supported cap. Geometry,
load path, Program Volumes and containment tolerances are unchanged. Two emitter-level
fixtures check more than 400 actual framing solids each: their complete vertical extent
stays within authored levels and their physical footprint fits every touched union.
A Funky chord crosses the preceding storey boundary, so checking only its host would
be insufficient; the test explicitly checks both authored airspaces.

Verification: 36 focused axis/hall/transfer/capability tests passed (12.48 seconds).
The wider axis/dependency/circulation regression passed all 81 tests on R7
(390.43 seconds; six existing Shapely warnings). Nine student-detail projection
tests also passed; this does not replace visual sheet review.

Fingerprint: `f2deca78cc067503329ce933a272c2eeb01d2aba7af35393c05f1ec978437f27`.
R7 diversity preflight repeats the four-score fixed-theater screen with zero normalized
collisions in each grammar. All four retained audio file hashes were rechecked against
`docs/experiments/visual_music_corpus_20.json` before starting native generation.

The public `run_visual_music_audit` loop ran in
`artifacts/skill_runs/2026-09-07-pv-closed-loop-r7/` with `--review --program-volume
--package-native --rhino`. Blender
uses the existing file-based exporter; the live 85-object scene was inspected through
MCP and left untouched. Rhino outputs are unaccepted candidates; no latest promotion
or acceptance sidecar is authorized by this run.

Couperin and Carefree generated Blender/GLB, model-derived sheets and review renders,
then both failed native Rhino validation at `ENV-RET-L01-BASE-S000`: the SDK faceted
Brep has an unset edge tolerance (`-1.23432e+308`). The batch was stopped after the
second matching error, while Funky was compiling; remaining tracks are incomplete.
This is an export defect, not an accepted native delivery. The error is recorded in
the global recurring-error log. Couperin's spatial, dependency and axis gates pass;
its hall has zero uncovered area and zero open wall-head length. Its base hero and
section cameras crop the larger footprint, and the structure-closeup PNG is blank.
Program Volume, structure-overlay and facade-overlay images frame the full building.
These presentation defects remain open; R7 is not promoted.

## R8 native geometry and framing repair

The native SDK failure exposed two source-body defects. At a vertical turn the
member's roll became singular and selected an unrelated world-axis frame, twisting
the profile. The shared tessellator now continues the nearest determined lateral
axis; wholly parallel straight members keep their prior convention. Planar concave
quads now use their interior diagonal, shared with the RhinoCommon adapter. Spatial
quads retain the previous fan. Paths and profile dimensions are unchanged by these
two corrections.

Head returns also had a 37.5 mm vertical leg inside a 140 mm section, folding the
station rings through each other. A turn no longer than the section depth now uses
one direct tie between the same registered slab anchor and mullion endpoint. It is
still a conceptual connection with capacity and fabrication unresolved.

159 focused native, source mesh, facade and enclosure tests pass; six optional
fabrication-union tests are skipped. `trimesh 5.1.0` was installed within the existing
fabrication requirement range to run the solid-volume tests. The native turn cases
cover four plan bearings, both path directions, rising/falling legs and `.3dm`
save/reopen; an actual enclosure emitter checks its base/head ties and support IDs.
The wider axis/dependency/circulation suite passed 81 tests in 387.28 seconds,
with six existing Shapely warnings; its geometry matches R8 but it began before
the declaration-only version bump from 3.9.1 to 3.10.0.

Study cameras now use Blender's native `camera_fit_coords`, checked against projected
building bounds. View 03 explicitly isolates structure and records that visibility.
The other four study views retain their directions and filenames. Native framing,
the complete revised models and drawing readability still require the R8 closed loop.
Rhino MCP has no connected slot; its fresh spawn attempt returned `CreateProcess
error 5` from the host Job Object. No license or application setting was changed.

R8 fingerprint: `f0208c4cae3f1b9d0273c7dc264c87fff70aa3db19230fef232a7ac4720dfba7`.
The four-score × three-grammar fixed-theater preflight has four distinct normalized
shapes and zero exact/tolerance collisions within each grammar. R8 Couperin
`building-v3-9fa98e412f77` generated in 301.55 seconds; its 29,935 canonical native
objects and 45 PV references passed SDK file geometry, serialization and saved-file
reopen checks. Native volume and Rhino GUI/architectural acceptance remain unchecked.
Carefree (216.74 seconds), Funky Boxstep (321.53 seconds), and Night in Venice
(208.55 seconds) also completed the native loop. All four retained the frozen source.
Completion means the artifact/SDK gates ran; it does not establish visual quality.

The new study framing shows the complete building and structure. Visual review
also found new roof/facade surface artifacts relative to R7. The isolated same-model
camera check confirmed the tiny near clip caused depth-precision artifacts. Camera
near/far planes now derive from actual forward geometry depths, retaining the same
framing and full scene coverage.
R7's full review is retained in its `report.md`: roof-layer poche, missing component
dimensions, repeated lift views and unresolved service-room layouts block a student
quality claim despite the presence of machine reports.

## R9 full-body facade control and adapter parity

The R8 camera isolation and shared-mesh isolation are retained respectively in
`artifacts/skill_runs/2026-09-07-pv-r8-camera-isolation/` and
`artifacts/skill_runs/2026-09-07-pv-r8-mesh-isolation/`. They read the unchanged R8
Couperin model and are diagnostic presentation outputs, never accepted/current models.
The second exposed and removed the Blender-only keyhole cap construction: extrusions
now use the same hole-preserving triangulation as the portable physical geometry and
Rhino file adapter. Roof coping consequently retains its real internal opening.
Eleven camera/extrusion tests cover scale, invalid forward depths, winding, multiple
holes, concavity and volume parity.

Blender 5.0's Python 3.11 uses the isolated optional dependency target
`.venv/blender_dependencies`. Install with its own Python executable:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.0/5.0/python/bin/python.exe' -m pip install --target .venv/blender_dependencies --no-deps -r blender/requirements.txt
```

`--no-deps` preserves Blender's bundled NumPy. This run installed Shapely 2.1.2;
neither the user's open Blender scene nor global package configuration was changed.

The large diagonal fans remaining after those two corrections are actual source
members. R8 Couperin `ENV-RET-L02-BASE-S064` spans 51.020 m to a remote slab across
the entry notch. Endpoint-only facade validation admitted the route. The emitter now
requires each tie's route inside the non-convex union of weather carrier and host
plate; the independent validator checks the complete physical body. No convex hull,
bounding-box substitution or missing-support waiver is permitted.

The first full-body recheck on the four unchanged R8 files returned 118 failed ties
for Couperin, 121 for Funky and 47 each for Carefree and Night; the latter two also
retain their existing site-dependent facade `unevaluated` status. These are raw
diagnostics, not confirmed defect counts: the new check also revealed a profile-radius
error at legitimate corner turns (0.0000721 m2 each). A rotated 75 x 140 mm section
needs its half-diagonal radius, not merely half its larger side. Four rotated
counterexamples reproduce that false finding, while the 51 m tie retains about
3.72 m2 outside even with the actual profile radius.

The focused facade/enclosure/camera suite passed 106 tests before adding those four
failing counterexamples. R9 starts from compiler 3.11.0 under the public one-track
native loop; further gate and presentation findings remain open until this exact
revision has been measured and reviewed. D3, selection and Rhino acceptance are not
claimed.

R9 completed with model `building-v3-3458a95f391e`, run `run-38aa0342e809`,
29,872 elements and 603.47 s total runtime. Allocation, dependency and axis reports
remain passing; the recorded spatial report contains 35 profile-corner false findings.
Compiler 3.11.1 corrects the return-body allowance to the measured half diagonal and
caches repeated level polygons/body domains. All 110 focused tests pass, including
the four previously failing corner cases. A retrospective full-facade check of the
unchanged R9 geometry returns zero collar findings. Its stored reports remain intact.
The preliminary R9 review preserves a separate architectural concern: some remaining
returns reach 44.658 m despite staying inside Program Volumes, with no capacity basis
for that reach. Neither spatial containment nor a clean screenshot closes that item.

### 3.12.0 — visible bearing stations; user-requested stopping point

The return emitter previously tested only the nearest point of each slab piece.
If that point was occluded by a notch, it discarded the whole slab and could choose
a remote piece instead. It now tries each real boundary segment's perpendicular
projection and endpoints before rejecting that slab, preserving the same non-convex
domain and clearance checks. This finite station search makes no claim of continuous
optimality or member capacity.

Three translated/scaled/rotated regressions selected the remote slab before the fix
and select the nearer legal slab after it. The focused facade/enclosure/camera suite
passes 113 tests; `git diff --check` reports no whitespace errors. On unchanged R9
geometry, an isolated resolver check for `ENV-RET-L01-HEAD-S111` changes its candidate
plan reach from 44.6583 m to 11.1472 m, anchored at `STR-SLB-L02`. No R9 model, native
file, render or report was regenerated or relabelled.

The remaining reach is still too large to treat as a resolved edge connection. The
stepped lower volume needs an explicit local roof/support solution; this finding
remains open, alongside student-detail readability and Rhino acceptance. V2/V4
evidence here is limited to geometric support selection and its counterexamples.
The user requested stopping the goal after this edit; no following generation or
design stage is authorized by this checkpoint.
