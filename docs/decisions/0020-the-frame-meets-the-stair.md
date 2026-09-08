# The frame meets the stair

The 20-recording visual audit (decision 0018, compiler 3.3.2) left four items open:
beams and braces through stair wells and lift shafts (G7), a lift that was a shaft and
nothing else (G8), landings drawn twice where they met the slab (G9), and eight
spaces with nowhere to go (G10). The stair and the frame were each correct on their
own and had never been asked to agree.

## Implemented

- A grid node standing exactly on the plate boundary is on the plate. The ray-cast
  point test answered by which way the edge ran, so every building carried columns
  and girders on three sides and framed nothing along the fourth. `_on_plate` is
  boundary-inclusive and is the one test the column loop, the girder loops, the
  transfer planner and the frame-closure check read. This changes every model's
  perimeter frame, and is recorded here as a correction rather than a design choice.
- A stair well that straddles one girder line inside one bay is framed around.
  `_plan_transfers` finds the crossing; `_emit_transfer_frame` stops the girder at a
  transfer header each side of the well, runs trimmer girders along it, and carries
  both onto the bay's girders. Every member is sized by `select_beam` for the
  reaction it collects, expressed as an equivalent tributary so the sizing tables
  are not bypassed. Joist and panel headers reuse the frame members through
  `transfer_edge` rather than emitting a second header on the same edge. Ids are
  `STR-TRF-…` and the girder halves carry a side suffix; the rule is
  `STR-OPENING-TRANSFER-001`.
- A well that straddles both directions, or one whose bearing girders do not exist,
  is not framed. It stays a reported conflict (`STR-OPENING-TRANSFER-UNRESOLVED`)
  with the member kept for review. Stepped upper plates whose bays are partial at
  the ragged edge fall in this class.
- Stair placement prefers wells the frame can carry. `_stair_anchor` orders
  candidates by no crossing, then transferable on every served level, then by
  crossing count, measured through `_transfer_feasible_everywhere` and cached per
  lattice.
- Braced-frame lines skip any bay a stair well crosses. Diagonals are no longer
  drawn through flights.
- Head clearance is measured against the section, at the place the member passes.
  `geometry_review` builds each declared profile's solid, takes the underside at the
  tread's plan location, and ignores vertical members, which are not overhead. A
  member without a declared section stays a warning rather than a pass. This turned
  351 warnings into measurements and removed the diagonal false negatives.
- The approach landings own their footprint. `_plan_approach` decides the entry
  landing, ramp and access stair once; the slab is cut back to those rectangles, so
  the coplanar overlap drawn as striped fighting is zero by construction.
- The lift has a car and a machine. `CIR-LFT-CAR-FLOOR`, `-BACK` and `-CANOPY`
  (kind `lift_car`) sit in the shaft at the parked level and `CIR-LFT-MACHINE`
  (`mechanical_equipment`) sits in the overrun, fastened to the shaft wall. The
  dependency graph knows both; the Revit mapping carries them; a portal at a landing
  the car does not stand at is reported `PORTAL-LIFT-CAR-UNVERIFIED`, not passable.

## Limits

A transfer frame is a member design, not a connection design. Girder halves bear on
headers that bear on trimmers; the joints are identities in the dependency graph and
nothing more. Wells on ragged-edge partial bays are still unresolved on the demo's
upper levels (L02 to L05 on the library massing), and each leaves head-clearance
violations that are now exact rather than approximate. The lift car proves the
elevator can stand where its portal is; it does not prove travel, door operation or
service coverage on any other level.

## Measured

The demo library (MAS-SLAB), before and after, on the same score:

| Measure | 3.3.2 | 3.7.0 |
|---|---:|---:|
| Columns on the north plate line | 0 | 8 |
| Landing to slab coplanar overlap | 8.2 m² | 0 m² |
| L01 well | girder through it | framed, W24X68 transfer sized by calculation |
| Wells still crossed (L02 to L05) | 4 | 4, reported as unresolved |
| Head-clearance findings | 351 warnings, 0 violations | 8 violations, 0 warnings |
| Lift car parts, L00 portal | none, unverified | 3 parts, passable |

The 20-track corpus, recompiled on 2026-09-05 through the audio to score to v3 chain
without Blender (numbers only, no renders; the per-track record is
`artifacts/visual_audit/2026-09-03/recheck_3_7_0.json`, summarised in
`docs/experiments/visual_music_audit_20.md`):

| Measure | 3.4.0 | 3.7.0 |
|---|---:|---:|
| Landing to slab coplanar overlap, all tracks | 155.4 m² on 20 | 0 m² on 0 |
| Wells framed with a transfer frame | 0 | 133 |
| Members kept for review at an opening | 290 on 16 tracks | 291 on 11 tracks |
| Head clearance | 0 violations, every check unevaluated | 483 violations, 0 unevaluated |
| Spatial report passed / unevaluated / failed | 0 / 18 / 2 | 4 / 0 / 16 |
| Dependency graph passed | 17 | 18 |
| Occupied levels without a lift door | 0 | 0 |
| Lift car and machine present | none | 20 of 20 |
| Unplaced spaces | 0 | 29 on 7 theatres |

The 291 members that remain fall in four classes, none of them framed here: a column
node standing inside the well (the well straddles a line in both directions), narrow
podium-bar bays where one well crosses several lines, a well against the plate edge
whose header has one bearing, and a single girder in a ragged partial bay. Decision
0022 then removed the first class at its source -- cores placed as grid cells, the
grid sized to hold the well -- and the same corpus measured 21 members on 3 tracks,
all of the second and third classes, with head-clearance violations down from 483
to 41. The
unplaced spaces are back-of-house theatre rooms and appeared while `program.py` was
being changed by the concurrent interface work (aisle clear width and wall allowance
deducted from band capacity); they are recorded, not attributed. The whole run was
measured on a moving tree: the same recording compiled at 22:38 and 22:55 reported
15 and then 0 members for review. The numbers are a state, not a release.

## Evidence

`backend/tests/test_core_frames.py` holds the boundary test, the exact head-clearance
measurements (low beam, clear beam, diagonal measured where it crosses, post ignored,
undeclared section warned) and the approach-landing cut. The transfer planner's tests
went with the planner when decision 0022 removed it. The corpus recheck and the demo compile are the integration
evidence; neither is a code approval.
