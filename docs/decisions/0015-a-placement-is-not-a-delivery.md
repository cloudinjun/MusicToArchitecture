# Decision 0015 — A placement is not a delivery

- Status: accepted; per-space area gate, program tally, and theatre semantics implemented
- Date: 2026-09-03
- Decision owner: user (second audit of the real-music demo run)
- Career-value tags: V2, V3

## The false green light

The audit found a theatre whose auditorium asked for 680 m² and received 559 — a fifth
of the one room the building exists for — while the run reported `fits` and a compliance
roll-up of **zero failures**.

Three separate mechanisms had to line up for that:

1. `ProgramAllocation.fits` was `not self.unplaced`. It asked whether a rectangle had
   been *put somewhere*, not whether the space had been *delivered*. A room truncated
   to eighty per cent counted as fitted.
2. `fulfilment` is an average over the whole brief. At 0.979 overall, a 134 m² hole in
   one room is invisible — and the plate fit steered on that average, so it stopped
   growing the building while the auditorium was still short.
3. The compliance roll-up had no program family at all. Area was the one requirement in
   the project that no tally counted, so no shortfall could ever appear as a failure.

Each of the three is the same error the project keeps finding: **a status that was not
earned by a measurement**. This is the worst instance so far, because it sat in the
summary line a reader trusts.

## What now holds

- `SpaceRequirement.area_tolerance` — the fraction of the ask below which a space has
  not been delivered. Default 0.9, because bands quantise and a few per cent is the
  grid rounding. The auditorium and the stage are held to 0.97: an auditorium at eighty
  per cent is not a small auditorium, it is a theatre that does not work.
- `AllocatedZone.area_satisfied` carries the verdict per space; `ProgramAllocation.short`
  lists the failures; `fits` is now *placed **and** delivered*.
- `_fit_plan_to_brief` steers on `trial.fits` — per space — and grows by what the
  **worst** room is missing rather than by the overall ratio, which is nearly one when
  a single large room is down and produced steps too small to ever close the gap.
- `_tally_program` puts the brief in the roll-up beside the code checks: delivered,
  short, or unplaced. Nothing in it is unevaluated — every line of the brief either got
  floor or did not.

## The constant that caused it

Growing the plate did not fix the auditorium; it inflated the building from 48 × 27 m
to 66 × 37 m while the room stayed at 539 m². The limit was not area, it was
`_stacking_groups` enumerating spans of one, two, or three structural rows — a constant
sized for a reading room. On the theatre's plate the largest rectangle available at
three rows is 539 m²; at four it is 719 m².

The span cap now comes from the brief: the deepest room's area laid out at its own
minimum width, in bays, bounded at six. Small rooms are not dragged into deep groups,
because the placement scoring already prefers the arrangement with the least waste and a
small room in a deep group is nearly all waste. With the cap derived, the auditorium
delivers **680 / 680** and the plate settles at 57 × 32 m — *smaller* than the one the
old fit had inflated chasing a room it could not reach.

## Theatre semantics

`SP-AUDITORIUM` and `SP-STAGE` carried `space_type='exhibition_foyer'`, and `SP-FOYER`
carried `lobby_welcome_checkout` — generic types borrowed from the library brief. The
plans, which label a zone from its type, printed "Exhibition Foyer" over both the house
and the stage. A type is what the rest of the pipeline reasons from, so a room whose
type is a lie is a room nothing downstream can get right.

They are now `auditorium`, `stage`, and `theatre_foyer`, and everything that reasons
from a type was given the values those types actually imply:

- **Acoustic separation** (`partitions.STC_TARGETS`): 60 for the house and the stage,
  55 for the foyer — they had a gallery's 45. The stage and the foyer join
  `NOISE_SOURCES`; a stage is machinery and a foyer is five hundred people talking, and
  both stand against the one room that tolerates neither.
- **Occupant load** (`constitution._OCCUPANT_FACTOR_BY_TYPE`): the auditorium is
  `assembly_concentrated_chairs` (0.65 m²/person) and the stage is `stage` (1.39). Left
  unmapped they would have fallen back to `business` at 13.94 — an auditorium counted as
  an open-plan office, a tenth of the people and therefore a tenth of the egress. The
  foyer keeps the factor a lobby already had: renaming a room is not a reason to change
  its occupant load, and only the two whose previous factor was wrong for what they are
  were moved.
- **Base-building support** (`constitution._SATISFIED_BY`): `theatre_foyer` is added to
  the types that satisfy `SUP-ENTRY`. The rename cost a `missing` finding until it was,
  which is that check doing its job — the map exists precisely so a renamed room cannot
  silently satisfy a requirement.

## Two things this surfaced

**A roof slab with no load path.** The plate the fit now chooses is smaller, which
thinned the column stack on the bar-podium until its top storey had one column — so the
roof level got no primary beams, the roof slab was emitted declaring no support, and the
truss that bears on that slab stood on nothing. The dependency graph reported it
correctly. The fix is not to invent a load path but to stop choosing such a plate:
`_frame_closes` tests whether the top level still has a bay a girder can span, and the
fit will not prefer a scale whose frame does not close over one that does. Plate size is
still a free variable at that stage, so this costs nothing.

**A theatre that was under-provisioned for egress all along.** With the auditorium
counted correctly, `MAS-SPLIT` reports 1174 occupants on L01 needing four exits against
three modelled, and an egress width short of 1005.3.1. Under the old gallery factor the
same auditorium counted 244 people and the deficiency was invisible. This is a true red
light replacing a false green one, and it is reported rather than hidden — but the core
system currently adds cores for *storey coverage*, not for *exit count*, so providing
the fourth is outstanding work. It needs the exit demand, which is a function of the
program, fed back into core placement, which the program is laid out around: a two-pass
compile, and its own measured round.

## Evidence

- `backend/app/program.py` — `area_tolerance`, `area_satisfied`, `short`, `fits`,
  derived `max_rows` in `_stacking_groups`.
- `backend/app/compiler_v3.py` — `_frame_closes`, worst-room steering in
  `_fit_plan_to_brief`.
- `backend/app/analysis_bundle.py` — `_tally_program`.
- `backend/app/briefs.py`, `backend/app/partitions.py`, `backend/app/constitution.py`.
- Measured, all seven massing families: spatial and dependency graphs pass on every one;
  six of seven deliver the whole brief with nothing short and nothing unplaced.
  `MAS-TOWER` pinned with a library brief holds at its identity bound and reports the
  shortfall, which is decision [0013](0013-brief-sizes-the-plate.md) behaving as
  designed.
- Decisions [0012](0012-spatial-constraint-rules.md),
  [0013](0013-brief-sizes-the-plate.md),
  [0014](0014-run-identity-and-one-building-per-number.md).
