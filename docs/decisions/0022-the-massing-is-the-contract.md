# The massing is the contract

A building here is a function of its volumes: the plates level by level, the
structural grid, the vertical cores, and the datums that size what stands in them.
Until now those volumes were chosen by the score and then re-derived by whoever
needed them. The stair search sampled the plate and found a spot; the frame drew
its grid and met the stair afterwards; the lift stood at a fixed offset from the
stair; five functions each computed "the well" from the anchor with their own
formula. Every collision the 20-recording audit found (decision 0018) was two of
those computations disagreeing. And a designer with a massing in hand had no way
in: the only entry point wanted a recording.

Two requirements, stated on 2026-09-05: downstream component construction depends
on the volumes the program massing gives it and invents none of its own; and in
real use the pipeline takes a massing alone and produces the model and drawings at
once.

## Implemented

- **The grid follows the volumes.** Stair cores are placed from the plates alone
  (a site is ranked only by whether a face of its core would leave a sliver bay
  against the plate edge or a neighbouring volume), and the grid is then drawn to
  them: `_frame_the_volumes` makes every core face a grid line, keeps the plate
  extents, the archetype's carved room edges and any given grid lines fixed, fills
  the spans between with the score's bay module, and adds no line through a core
  or through a given lift shaft. The legacy generator anchored its 6 m grid on two
  fixed core centres; this is that idea with the cores decided by the massing and
  the module filling around them. It replaced two earlier attempts on this branch
  -- placing cores on cells of the score's grid, then coarsening the grid to hold
  the well -- and the transfer frames, straddle tiers and feasibility cache that
  framed girders around wells the grid could not fit. Those are deleted, not kept
  behind a switch: a girder through a stair is not a case to frame around.
  The sliver penalty ranks below the separation the code asks for: the second
  core and the extras are chosen among the sites that meet a third of the served
  area's diagonal, fewest slivers first, and only when no site meets it is the
  farthest taken regardless. Ranking slivers first left the bar-podium's pair 15 m
  apart against 25 m required, with the remote corner of the podium refused for a
  sliver against the ramp's keep-out -- a second exit that is not remote is not an
  exit. The primary itself is chosen among its
  preferred sites for the one that leaves every storey two ways out, since the
  extras can only cover what the primary leaves room for. The sampler also offers
  the sites flush with the frame's extent, since a core face on the extent line is
  the grid's own line. A core's exit door opens away from its partner where the
  strip beyond the landing face has room for the door and a person on every storey
  served (`CORE_DOOR_ROOM_M`), because the separation is measured door to door;
  where it does not, the door faces the interior, where the corridor is.
- **The core is structure.** A stair core is four reinforced-concrete walls on the
  faces of its volume (`CORE_WALL_M` 200 mm, inside the face), from a raft footing
  to the roof. No column, girder, joist or panel is drawn inside the core or on its
  faces; the framing that meets a face bears on the wall (`edge_support`), and a
  girder that ends at a core corner bears on the wall there -- the dependency
  check now measures distance to a box's solid rather than its centre, since a
  wall is metres long and the girder meets its end. The landing-side wall carries
  the exit door as two jambs and a head (1.6 m clear by 2.4 m: wider than the 1.2 m
  planning body plus its wall allowance, taller than the 2.1 m use height), and a
  `door` element in the `stairs` subsystem so the portal report reads it as a room
  door onto the landing rather than a lift door wanting a car. Each storey of wall
  is screened as a bearing wall (ACI 318 empirical wall, phi 0.65, f'c 30 MPa) for
  the walls above it, the floor inside the core outside the well, and half of each
  bay the framing spans onto its faces; the utilisation is recorded on the element.
  The public-circulation planner treats the cores as obstacles and reaches each
  stair at the point outside its door. The door faces the plate's interior (the
  landing side is the side toward the plan centre): a pair's doors used to face
  away from each other, which with walled cores put a door on the strip between
  the core and the facade and sent every corridor around the core, and the
  theatres' back-of-house rooms lost their runs to those corridors. A girder that
  arrives at the landing face bears on the jamb or the head standing where it
  arrives, not on the head regardless. The door hangs in its jambs in the
  dependency graph -- the door rule there read every non-partition door as a lift
  landing door and hung it on the nearest shaft segment, which left a stair door
  on a storey the lift does not reach with no host at all; the jamb rule reads
  core-wall hosts only, because `instance.supports` is regenerated from the graph
  and a second compile would otherwise read a lift door's shaft segment as a jamb
  and disagree with the first. Each wall piece registers its centre-lines with the
  axis skeleton -- up its middle to the storey line and along the storey line in
  its centre plane, so the storey above meets it at one node by identity as a
  column stack does -- and a ground-storey wall is a root of the frame the way a
  ground column is, since the raft under it is a solid with no line; without that
  a girder spanning wall to wall on the ziggurat shared no node with anything and
  read as floating. The skeleton's closest-pair routine measured two parallel
  lines from the first one's start, which put a girder running along a wall's
  line a whole bay from the wall it bears on; it now takes the nearest endpoint.
  `core_wall` is a gravity element in the dependency graph. The
  approach -- entry landing, ramp runs and landings, access stair -- is decided
  from the plate before the cores and is floor no core may take: a core flush
  with the entrance frontage of an apsidal library stood its half landing over a
  ramp run.
- **Rooms lay out on the module, structure on the volumes.** `Lattice.band_lines`
  keeps the module rows the plate was laid out on; `level_bands` reads them, so a
  core face never splits a row into a strip no room can use. Cores are placed
  inside the orthogonal frame's extent, never in an apsidal end that stands on
  radial columns. Roof trusses stop at the cores and bear on their walls. Measured
  on the demo library: the four-storey score at its size bound houses 90% of the
  brief and reports the rest unplaced (it housed all of it before the cores had
  walls, because corridors then ended at landing edges the walls now stand on);
  the seven-storey score houses 104%. A preference for cores that share grid lines
  was tried, measured worse (the second core stacked over the first and cut every
  row in two) and removed. The archetype daylight gate measures its perimeter zone from
  the bay module rather than the structural lines: those now carry the core
  faces, and a sliver between a face and a module line shrank the zone to 450 mm,
  short of the demo library's cantilever, so the glazed reading room read as
  interior.
- **`ProgramMassing`** (`backend/app/program_massing.py`): plates from the ground
  up with optional kinds and elevations, an optional grid, cores with the levels
  they serve, datum overrides by id, and pins for typology, structural system and
  grammar. `compile_from_massing` builds the full model from it with no recording:
  a neutral score stands in for the datum table and the selection screens, and the
  massing's datum values override it. `program_massing_of` writes the massing a
  compiled model stands on, so a music run's volumes can be saved, edited and fed
  back. `backend/scripts/compile_from_massing.py` runs either and issues the
  drawing set; `docs/contracts/program_massing.v1.example.json` is a worked input.
- **One compiler tail.** `compile_building_model_v3` now ends where the plate is
  settled and hands over to `_compile_from_lattice`; the massing path enters there.
  Selection, sizing, emission, the constitution, portals, life safety, spatial
  rules and the archetype report run identically on both.
- **Given cores are read, not searched for.** `Lattice.given_cores` carries the
  massing's cores; `core_anchors` returns them after checking each footprint --
  landings included -- against every plate it serves, the carved floor and the
  other cores, and refuses by name when one does not stand. Each given core also
  reserves its floor on `LevelDatum.reserved`, which the one clearance test every
  archetype carver uses reads, so the reading room or the galleries are carved
  around a designer's core instead of through it.
- **One formula for the flight run.** `flight_run` replaces three copies of
  `max(2.2, width * 2.4)`.
- **The ramp's top landing is the podium's floor.** It was emitted on the ground
  level with the rest of the ramp, so a lobby reaching onto it read as standing
  outside its floor support by exactly the landing's area on three library
  recordings. It now belongs to the level it is flush with, and the room-support
  review counts a flush `ramp_landing` as floor the way it counts a stair landing,
  healing the seam between a landing and the slab it was cut from by a closing
  (grow then shrink, square joins) rather than a buffer, which had moved every
  measured area by a tenth of a millimetre times its perimeter.

## Limits

Rooms are still allocated by the typology brief: a massing smaller than the brief
reports unplaced rooms, honestly, rather than shrinking them. The theatre hall's gravity
transfer (`transfer_structure.py`, the concurrent session's) is a different thing from
the deleted well transfers and is untouched here. `ProgramMassing.zones`
is consumed by the allocator since decision 0023 (the writer decides, the kernel
measures); the brief itself is still the typology's. The
theatre carver positions its house from the plate and refuses a given core that
lands in it rather than moving the house. The core walls are screened for gravity
only: reinforcement, in-plane shear, the lateral role and the wall-to-frame joints
are not designed, and the column stacks are still sized without deducting the
floor the core walls now carry, which is conservative. Rooms the egress network
reports unreachable on the example are unreachable with the core walls removed as
well: their partition doors open onto the facade strip, which is the partition and
corridor planner's decision, not the core's. The theatre bar-podium fixture's
podium floor asks for three exits and has two: no second core fits the bar beside
a 2.6 m flight and the house, and the extras exist for coverage, not for the exit
count -- HEAD's compiler (3.5.0) places the same two cores and reports the same
finding. Cores driven by the occupant load is a slice not taken here.

## Measured

- The example massing (five storeys, 48 by 27 m, 6 by 9 m bays, two stairs and a
  lift at cell centres) compiles in about 80 s: cores where given, no girder
  crosses an opening, dependency graph passed, reading room carved clear of the
  cores, eleven sheets issued.
- Courtyard library, remote-pair placement before and after the cell rule: the two
  cores stand 50.8 m apart against a 24.9 m requirement either way; the remoteness
  finding reads `unevaluated` in both, which comes from the life-safety rewrite
  and not from placement.
- The 20-recording corpus, recompiled on the settled 3.8.0 tree and again on the
  3.9.0 tree (numbers only, no renders; `artifacts/visual_audit/2026-09-03/
  recheck_3_8_0.json` and `recheck_3_9_0.json`, summarised in
  `docs/experiments/visual_music_audit_20.md`):

| Measure | 3.7.0 | 3.8.0 | 3.9.0 |
|---|---:|---:|---:|
| Members kept for review at an opening | 291 on 11 tracks | 21 on 3 tracks | 0 |
| Head-clearance violations | 483 on 11 tracks | 41 on 2 tracks | 0 |
| Spatial report passed | 4 of 20 | 12 of 20 | 13 of 20 |
| Dependency graph passed | 18 | 18 | 20 |
| Landing to slab overlap | 0 m² | 0 m² | 0.0 m² |
| Unplaced spaces (theatre back of house, from the concurrent program change) | 29 | 28 | 32 on 11 tracks |

  On 3.8.0 the 21 members left are all on the three bar-over-podium theatres (Cantina
  Blues 3, L'Art de toucher le clavecin 5, Raw 13): wells on the bar's narrow bays
  that cross several lines or stand against the plate edge with one bearing. They
  are reported under decision 0020's limits, not cut.

  On 3.9.0 no member is kept for review and no head-clearance violation remains: the
  cores are walls and nothing is framed inside them. 6 spatial failures are the
  theatres' stage-access overlaps (concurrent seating work); the others are
  INVALID-PLAN-RING on Android Sock Hop. The unplaced count moved from 28 on 8
  tracks to 32 on 11 (Blue Ska 0 to 1, Cloud Dancer 3 to 1, L'Art de toucher le
  clavecin (recorded excerpt) 3 to 2, Dama-May 1 to 3, Exotic Battle 0 to 1, Funky
  Boxstep 0 to 1, Raw 2 to 6, Ritual 6 to 5, SCP-x5x (Outer Thoughts) 5 to 4): the
  core walls take floor the corridor planner used, the second core now stands at
  the plate's edge for separation and a door opening away from its partner sends
  the corridor round the core, so the theatres' back of house loses more runs than
  it gains; that exchange is this change's, the shortfall itself is still the
  brief's capacity deduction in `program.py`. The archetype report refuses nothing
  on any track. The door rule was A/B'd on the same tree with every core door
  facing the interior (`recheck_3_9_0_ab_door_inward.json`): 33 unplaced against
  32, and two spatial reports that pass with the rule fail without it (Blue Ska,
  Exotic Battle), so the rule stays; the unplaced shift is the placement, not the
  doors. Decision 0023's allocator fixes then move the count: 20 unplaced on 7
  tracks on 3.9.1, spatial 13 of 20, dependency 20 of 20 (recorded there).

## Evidence

`backend/tests/test_program_massing.py`: a hand-drawn massing builds a building
and its drawings; a core outside its plate, two overlapping cores and a stair that
does not reach grade are refused by name; cores left to the compiler land on cells;
an unknown datum is refused; a music run round-trips through its own massing to the
same grid, cores and frame counts; cores left to the compiler and cores given both get
a grid drawn to them, walls that chain to a footing and an exit door.
`backend/tests/test_core_frames.py` holds the grid rules: every core face a line, no
line through a core, idempotent, a given grid kept, carved edges fixed, slivers
penalised.
