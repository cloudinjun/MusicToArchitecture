# Decision 0012 — Spatial constraint rules for a blind modeller

- Status: accepted; four rules implemented and enforced on every compiled model
- Date: 2026-09-02
- Decision owner: user
- Career-value tags: V2, V3

## Decision

The compiler carries a set of spatial rules that assert, on the finished model, the
things a person modelling by hand would never need to be told. They live in
`backend/app/spatial_rules.py`, run at the end of `compile_building_model_v3`, and the
report travels on the model as `BuildingModel.spatial` beside `constitution` and
`life_safety`.

The reason they exist is stated by the user and is worth keeping in the record:

> 人在建模的时候眼睛一看就知道有问题一定不会这么建模，而计算建模由于是盲建，则需要被规则约束。

A person laying out a plan does not run a check to discover that the lift shaft is
standing in the fire lobby, or that the ramp deck finishes 120 mm above the landing it
meets. They see it. The compiler does not see, so what the eye would have said has to be
written down.

## The four rules

Each was written against a failure that actually shipped, and each is proved by a test
that injects the failure and watches the rule fire. A constraint that cannot fail is not
protecting anything.

| Rule | What the eye would have said |
| --- | --- |
| `SP-SUBSYSTEM-OVERLAP` | Two systems standing in the same floor area. |
| `SP-SURFACE-NOT-FLUSH` | A surface you step onto that is not level with the one you step off. |
| `SP-FALL-GAP` | A slot between two walking surfaces at different heights. |
| `SP-STANDS-IN-VOID` | Something standing where the floor has a hole in it. |

Pairwise testing across every element is 6.34 M comparisons on the 3,560-element
`MAS-SLAB` library, so the rules read a coarse plan-grid `SpatialIndex` at
`CELL_M = 4.0` and compare only what shares a cell.

## Violation and warning

`SpatialReport.status` fails on violations only. A warning is a consequence the pipeline
named and could not design away; a gate that fails on those is a gate nobody can ever
clear, and a permanently red light gets read as broken rather than as informative.

The one warning in service today is the core reservation. `allocate_program` cuts the
stair and lift cores out of the floor before banding the program around them, but on a
plate too small to carry its own cores that leaves nothing to lay out on — a nineteen
metre tower lost every band on every floor and came out with no rooms in it. So the
reservation is applied where it leaves a floor to lay out on, the levels where it was not
are recorded in `ProgramAllocation.cores_unreserved`, and the overlap there is reported as
a warning that says which levels and why. A stated compromise beats an empty building,
and beats a silent one either way.

## The report has to reach the client

A constraint nobody can see is not doing its job. `AnalysisBundle` carries `spatial`
alongside the other reports, and `_tally_spatial` puts it in the status tallies counted
per rule rather than per finding — a rule that found nothing is a check that passed, and
that is the thing worth reporting.

This was missed at first, and the test that should have caught it did not, because
`test_every_report_the_model_holds_reaches_the_bundle` enumerated eight field names by
hand: a test that passes for every report nobody added to it. The whole spatial system
was computed on every model and dropped by the payload while that test reported the
bundle carried every report the model held. The material registry that resolves each
group's `material_profile` to something renderable had gone the same way. The list is
derived from the model's own fields now, with the two omissions (`units`,
`coordinate_system` — invariant literals) named and reasoned, so the next report is
covered the moment it exists.

## Required validation

- `backend/tests/test_spatial_rules.py` — every massing passes; every rule is shown
  firing on a case built to break it; the reservation is checked at the allocator as
  well as on the finished elements.
- All seven massing families report zero violations. Warnings appear only on
  `MAS-TOWER` (L01–L03) and `MAS-BAR-PODIUM` (L04), the plates that cannot carry their
  cores.

## What the rules caught

Three defects that every prior check passed, and that no amount of reading the code
found:

1. **A row of floor measured on its centre line alone.** A core standing in the middle
   of a row threw away the shorter side, so reserving 133 m² of core cost 267 m² of
   floor, and an atrium sterilised whichever side of itself was narrower.
2. **A lift shaft sized by the stair beside it.** `max(2.6, flight_width * 1.6)` meant a
   score calling for a generous stair also called for a four-metre lift bay; the
   reservation came out 11.6 m wide for a 2.6 m flight, wide enough to take the middle
   bay of a museum and both its galleries with it. A lift car is not a function of the
   stair.
3. **A cursor written backwards.** A room laid out west of a stair wrote its finishing
   edge into the cursor of the strip *east* of the stair, which begins further east
   still. The cursor then read behind that strip's own beginning, the next room started
   from it, and a theatre foyer spanned the whole plate with the lift shaft standing
   inside it — on a level where the core had been reserved and the bands correctly cut
   around it.

The third was introduced by the fix for the first and was found by re-running the rules
across all seven massings, not by reasoning about the change.

## Consequences

- Layout heuristics are A/B measured across the roomy, narrow and wide scores and all
  seven massings before they are kept. Splitting rows in y at obstruction edges with
  contact-chained stacking sounded obviously right and measured worse in every case
  (0.92 → 0.82, 0.81 → 0.62, 0.43 → 0.32); it was reverted.
- Program fulfilment fell where it had been achieved by putting rooms where the stairs
  are. The roomy library reported 1.007 before the cores were reserved and reports 0.92
  after, with the shortfall confined to a single truncated stack room and bounded, in
  test, by the floor area the cores take.

## Evidence

- `backend/app/spatial_rules.py`, `backend/app/program.py`, `backend/app/compiler_v3.py`
  (`core_anchors`, `core_reservations`, `LIFT_SHAFT_M`).
- `backend/tests/test_spatial_rules.py` — 40 tests.
- Decisions [0009](0009-program-structure-facade-coupling.md) and
  [0010](0010-component-dependency-and-attachment-graph.md) for the graphs these rules
  sit beside.
