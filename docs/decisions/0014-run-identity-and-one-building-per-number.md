# Decision 0014 — Run identity, one building per number, and the pair of exits

- Status: accepted; implemented across compiler, bundle, pipeline, and web client
- Date: 2026-09-03
- Decision owner: user (audit of the real-music demo run)
- Career-value tags: V2, V3, V4

Three blockers from the first real-music audit, and one root shared by two of them:
**identity was the audio hash**, and the audio stopped being the whole identity the
day anything else began to shape the building.

## 1. The model's identity hears every input

`model_id` — and through it the GLB, drawing, and render directories, which are all
pathed by it — is now hashed from everything that decides what gets built:

    score_id | COMPILER_VERSION | pins (massing/typology/grammar/cutaway) | four selections

Same inputs, same id: an identical re-run replaces its own identical output. Anything
different builds beside the old run instead of over it. Before this, a re-run after a
compiler change silently replaced the GLB an older stored run still pointed at (the
Glulam run's record pointing at a Steel GLB), and one MP3 could not keep two pinned
variants side by side. The run id follows: `run-` + hash of audio, compiler version,
and the model identity. `backend/app/version.py` holds `COMPILER_VERSION`; the four
selection outcomes travel in the identity beside it, so most behavioural drift changes
the identity even when nobody bumps the constant.

`write_drawing_set` also deletes stale sheets its own issue did not produce — a stale
section beside a fresh index made the script count ten drawings over a nine-sheet
payload.

## 2. One building per number

The v2 massing contract is *typed* to one building — `typology: Literal['library']`,
`grammar_id: Literal['international_style_informed']` — while the v3 selection follows
the score. The day the score first chose a theatre, `compile_analysis_bundle` summed
the theatre's checks with a library's and the status bar called the result one
building's compliance: 57 passed, 1 failed, 12 unevaluated, of which a third belonged
to a building not on screen.

The bundle now takes `companion_identity` (`typology/grammar` of the v2 chain). When
it matches, the v2 tallies join the roll-up as before. When it does not, they move to
`ComplianceRollup.foreign_tallies` — carried, labelled with the building they
describe, rendered in their own panel, and **never summed into the totals**. The
derived-fields test in `test_analysis_bundle.py` holds both directions.

## 3. Two exits are a pair, not one stair plus an afterthought

The real failure: the theatre's L04 held 119 occupants and one exit. The second core
stood in the far corner of the podium it served three storeys of — separation had
been preferred *instead of* coverage, the exact opposite of what the comment above
the code promised.

The fix is layered, each step a rule and not a patch:

- **Coverage is never traded for remoteness.** The remote second core keeps its
  podium corner; *extra cores* (`core_anchors()['extras']`) serve the storeys it
  stops short of, running to grade like any exit. Occupied storeys only — requiring
  the extra to stand inside the roof plate as well shrank its region to a sliver
  five metres from the primary.
- **1007.1.1 measures the run under trial**, not the whole building: a bar-sized
  floor is not asked for podium-scale separation.
- **When the pair that covers the top storeys fails its own third-diagonal, both
  ends move together** — the two farthest feasible points of their regions, found by
  `_stair_sites` — and the remote second is re-chosen against the moved primary.
  Guarded: a massing whose greedy pair already clears is untouched.
- **The doors of a pair open away from each other.** The exits the graph measures
  are the landings, not the anchors. On the slim, curve-ended bar the anchors can
  stand at most 9.4 m apart against a 10.3 m ask; door to door, facing away, the
  separation is 15 m. This is what a person would draw before moving either core.

Result on the demo theatre: life-safety **0 failures** (both 1006.3.2 and 1007.1.1),
spatial rules 0 violations, program 0.979 with nothing unplaced. All seven massing
families report zero spatial violations and, now, zero failures on both egress
clauses. Regression tests in `test_permit_level.py` pin the building that found the
flaw (fixtures `theater_bar_podium_*.json`).

### What the third core broke, and what that cost the tests

Adding a core exposed the same defect shape one layer down. The dependency graph hosts
a half landing on the two stringers either side of it, and it found them by *guessing*
the flight letters: `('A', 'B') if the token starts with A else ('C', 'D')`. The extra
core's half landings are named `G`, so they fell into the `else`, looked for `C`/`D`
stringers that do not exist, matched nothing, and hung off the graph entirely — two
elements with no support and no exemption, which is exactly what
`DEP-REQUIRED-COVERAGE` exists to catch. The pairing was written in two places: the
emitter named the flights, the hosting rule re-derived them. It is now written once,
in `dependencies.FLIGHT_PAIRS`, which the emitter reads; `MAX_EXTRA_CORES` is
`len(EXTRA_FLIGHT_PAIRS)`, so the cap and the names cannot drift apart.

Two tests had to change because the building got better, which is worth recording so
the change does not read as a weakened assertion:

- `test_a_plan_too_narrow_for_two_remote_cores_reports_the_failure` asserted that
  MAS-TOWER **fails** 1007.1.1. It passes now — 21.5 m against a 12.7 m ask — and no
  massing in the family set fails the clause any more. Keeping the assertion would
  have meant keeping a building broken to have something to point at. The behaviour it
  was written for is still held, at the level where it can fail: a plate deliberately
  shrunk to 16 × 13 m (measured: fits one stair, cannot separate a pair — 5.1 m
  against 6.9 m) must still get a second core rather than have it omitted, and the
  test asserts the plate is still cramped so it cannot silently stop exercising that
  path.
- A companion test now asserts 1007.1.1 is **answered on every storey that has people
  on it**. The failure mode is silence: a storey with one exit produces no pair to
  measure, so the clause goes missing rather than failing and a reader scanning for
  red sees none. Storeys with no occupants are excluded on evidence read from the
  graph — a ziggurat's top plate can shrink past a usable floor, so nobody stands
  there and the clause does not apply.

## Evidence

- `backend/app/compiler_v3.py` — identity seed; `_stair_sites`; `pick_second` /
  `pick_extras` / pair adjustment in `core_anchors`; scissor stairs facing away.
- `backend/app/analysis_bundle.py` — `companion_identity`, `foreign_tallies`.
- `backend/app/pipeline.py`, `backend/app/integration.py`, `backend/app/run_store.py`,
  `backend/app/drawings.py`, `backend/app/version.py`.
- `web/lib/types.ts`, `web/components/workspaces/ComplianceWorkspace.tsx` — the
  foreign panel.
- Decisions [0012](0012-spatial-constraint-rules.md), [0013](0013-brief-sizes-the-plate.md).
