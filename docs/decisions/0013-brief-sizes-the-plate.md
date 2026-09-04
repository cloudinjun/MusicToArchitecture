# Decision 0013 — The brief sizes the plate; the score keeps the direction

- Status: accepted; implemented in `_fit_plan_to_brief`, `backend/app/compiler_v3.py`
- Date: 2026-09-02
- Decision owner: user
- Career-value tags: V2, V3

## Decision

The user's words: 乐谱应当给的是大方向上的指导 — the score gives directional guidance.
It does not set absolute size.

So the division of authority is:

| Decision | Owner |
| --- | --- |
| Silhouette (massing family) | score |
| Storey count | score |
| Bay grain and proportion | score |
| Terraces, voids, apse — the composition | score |
| **How much building there is** | **brief** |

`_fit_plan_to_brief` scales the massing family's plan uniformly until a trial
allocation of the actual brief is housed. Uniform scaling is what keeps the direction
intact: the proportion the family declares and the bay grain the score chose both
survive, so more area means more bays, not bigger ones — a tower stays a tower, it is
simply a tower with enough floor in it.

## Why

Before this, every family carried a constant footprint (`plan_x_m × plan_y_m` in
`massing.py`) and the score could stretch it ±18%. The briefs are absolute areas. The
two never met, so whether 3,066 m² of library landed in a 1,400 m² building or a
6,000 m² one was luck. Measured with the v3_demo score, which picks MAS-BAR-PODIUM:

| typology | brief m² | fulfilment before | after |
| --- | --- | --- | --- |
| library | 3,066 | 0.388 | 1.018 |
| museum | 2,480 | 0.479 | 1.024 |
| theater | 2,481 | 0.498 | 0.973 |
| pavilion | 1,043 | 1.013 | 1.006 |

Three of four briefs could not be housed by the building their own score produced;
after the fit all four are housed with nothing unplaced, and the pavilion came out
slightly *smaller* — the fit shrinks as well as grows, because a building should be as
small as its brief allows.

A second effect was unlooked-for: the tower's `cores_unreserved` warnings fell from
eight (L01–L03) to two (L05 only). Its plate grew to hold its brief, and floors that
could not carry their own cores now can. The warning system stayed honest through the
change — the levels it names shrank because the problem shrank.

## How the fit steers

Two properties, both learned from a failure of the first draft:

1. **It steers on a trial allocation, not on gross area.** Floor is lost to
   quantisation the area ratio cannot see: rooms truncate at band edges, and a small
   change of plate can drop a whole structural row.
2. **It keeps the best state it has visited and returns that**, not wherever the last
   step landed. The first draft shrank a roomy score's plate toward the target,
   collapsed past it (a structural row vanished), hit the iteration cap mid-recovery
   and ended at 0.62 fulfilment — on its way back to a building it had already been
   inside. With best-state tracking the same walk ends at 1.004.

The walk stops at `ENOUGH = 0.97` fulfilment rather than 1.0 — quantisation keeps a
few rooms a band short of their ask on any honest plate, and chasing the last two per
cent inflates the building for nobody. When a state delivers in full it probes one
size down; if the probe loses rooms, `best` keeps the housed state.

## Direction survives, measured

On the slab with the reference library, a score that stacks few levels now buys a
broader building and a score that stacks many buys a slimmer one — the same brief
housed either way:

| score | storeys | plate | fulfilment |
| --- | --- | --- | --- |
| tight (tempo 0.0) | 4 | 54.7 × 28.2 | 0.985 |
| roomy (tempo 1.0) | 7 | 51.9 × 26.5 | 1.020 |

Before the fit the tight score simply failed its brief, which punished a direction for
being a direction. `test_fewer_storeys_buy_a_wider_plate` holds this.

## The bound where the family stops being itself

The scale is clamped to 0.7–1.5. Past those bounds a tower with a broad plate is not a
tower and the massing no longer answers the music, so the fit holds at the bound and
the rest of the brief is **reported unplaced rather than housed** — `fits=False` with
per-space reasons stays a legitimate outcome, stated on the model. The sentence
recording the fit (asked-for area, delivered area, scale, whether the bound held) is
appended to `selection.massing_reason`, so the decision is on the model where the
other massing reasoning lives.

## Evidence

- `backend/app/compiler_v3.py` — `_fit_plan_to_brief`, `PLAN_FIT_MIN`, `PLAN_FIT_MAX`.
- Library across three scores, before → after: roomy 0.924 → 1.004, narrow
  0.860 → 0.970, wide 0.438 → 1.006; nothing unplaced in any of them.
- All seven massing families: zero spatial violations.
- Decision [0012](0012-spatial-constraint-rules.md) for the reservation and rules the
  trial allocation is measured against.
