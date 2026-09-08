# Zones: the writer decides, the kernel measures

The purpose restated on 2026-09-06: produce complete, coordinated, presentable
building candidates faster -- not approach professional completion. The same day
the direction for the tooling was set: **程序算，模型判**. The deterministic kernel
(geometry, structure, checks, drawings) is a tool; the judgement -- which rooms
share which part of which floor, where a core goes, what to change when a report
comes back -- is a design decision a person or a model makes on the kernel's
numbers. The kernel never invents a decision; the writer never does arithmetic.

This is the first slice built that way. The whole day before it went into hand-
written placement heuristics that each had to be measured on twenty recordings;
program zoning was the obvious next heuristic to write, and the obvious first one
to hand over instead.

## The contract

- **`MassingZone`** (`backend/app/program_massing.py`): a rectangle on one level
  and the brief spaces that share it (`space_ids`; `space_id` is the single-room
  shorthand), with a label and a note. Coarse on purpose: "back of house, L05,
  the middle row". Zones travel on `ProgramMassing.zones`, so the decision is
  part of the massing file and the run is reproducible without whoever wrote it.
- **The allocator consumes them** (`allocate_program(zoned=...)`,
  `backend/app/program.py`). Floor is laid out per *slot*: one per occupied
  storey for the brief at large, one per zone. A zone's slot is its rectangle
  intersected with the usable floor; its rooms are laid out inside on the module
  rows with the same `try_place` the brief uses, first at their full area, then at
  their own `area_tolerance` -- a room a tenth short is a short room, reported as
  such, not an unplaced one. The zone's floor is taken out of its storey's slot,
  so the rest of the brief keeps out of it. A room that does not fit its zone is
  reported against the zone by name, with the zone's numbers, and is never placed
  elsewhere: the massing is the contract, and the writer enlarges the zone.
- **Refused by name**, like a given core: a zone off the plate, in a void, in a
  stair core or in carved floor (a hairline of 20 mm is tolerated -- the carve
  grows its rectangle by a tenth of a millimetre), a zone naming a space the brief
  does not have, a space named in two zones, a zone on a storey that is not
  occupied.
- **`ZoneReport`** per zone, on `ProgramAllocation.zone_reports`, in the model's
  `Program:` limitation and in the script's `summary.json`: rectangle area, usable
  area inside it, the whole-row floor left once the public corridors and the
  entrance approach took theirs, area asked, area delivered, placed and unplaced
  ids.
- **`brief_for_massing`** (`compile_from_massing.py --brief`) is what the writer
  reads: every briefed space with its area, minimum dimension, level preference,
  daylight need and adjacency, which rooms the archetype already placed; and per
  occupied storey the plate ring and bounding box, plate and usable area after
  cores and carve, the core rectangles, the carved floor, the removed plates
  (double heights), the entrance approach footprints on the entry storey, and
  **the rows**: for each module row, the x-runs of usable floor whose whole depth
  is inside. That last list is the one to draw on. Plates rotate and step; a zone
  drawn to a bounding box stands off a rotated plate at its corners and is
  refused, a zone drawn on a row run is accepted.
- **Module rows round-trip.** `MassingGrid.band_lines` carries the rows the
  rooms lay out on. The structural y-lines carry the core faces (decision 0022);
  an exported massing that handed them back as the rows lost every strip between
  a face and a module line, and a 2 m row is not a row.
- **The loop** is a skill, `.claude/skills/zone-massing/SKILL.md`: read the
  brief, write zones, compile, read the zone reports, adjust. Two to four rounds
  is normal; a compile is one to five minutes. A person can run it without a
  model, and the zoned massing JSON is the record.

## What was learned writing zones by hand

Four passes on the example library and two on a theatre recording, done as the
writer would do them, each one refused or short for a reason the export did not
yet show -- and each reason became a field in the export:

- A zone over the double height above the reading room: refused. The export now
  lists `removed` plates per storey.
- Zones drawn at row mid-depth: the rooms could not use the split rows. The export
  lists `band_lines`; the skill says to put zone edges on them.
- A ground-floor zone across the entrance: the corridor spine and the entry apron
  took the rows, and nothing fitted. The export lists the approach footprints, and
  the zone report now says how much whole-row floor was left after them.
- A zone to the bounding box of a tilted theatre plate: refused at the corner. The
  export lists the plate ring and, decisively, the row runs.
- A row 0.7 m shorter than two rooms plus their gap: the second room was reported
  unplaced. A zone now accepts a room at its own tolerance.

## Limits

Zoning moves rooms; it does not create floor. When the rows on every storey add up
to less than the brief -- a theatre whose house takes the ground floor and whose
upper plates are tilted quads -- the honest result is a named list of what the
massing cannot hold, and the next lever is the massing itself: a storey, a wider
plate. That lever is the writer's too, through the same file, and is not
automated here. The corridor planner still decides a room's connection, so a zone
with the floor for a room can still lose it to the route the planner needs; the
zone report shows the whole-row floor after the planner's reservation, not the
connection. Adjacency in the brief is not enforced inside a zone. The typology
brief is still the brief: a massing does not yet carry its own list of rooms.

## Measured

Runs in `artifacts/massing_runs/example_zones/` and `artifacts/massing_runs/ritual_zones/`;
compiler 3.9.1 unless stated. A compile of the example takes 75-125 s, of the theatre
180-270 s.

- **Example library (48 x 27 m, four storeys, given cores).** Unzoned: 89% of the
  brief delivered, periodicals and staff unplaced. Zoned by hand in four passes:
  76% (zone over the double height refused, exhibition lost to a split row), 71%
  (a zone on the entrance rows held nothing once the corridor spine took them),
  refused (quiet wing over the removed plate), 80% on 3.9.0 and 83% on 3.9.1
  (drawn on the row runs; the cafe fits once the entry landing is excluded from
  the zone's floor instead of refusing the zone, the store does not). On a plate
  the allocator already fills (88% on 3.9.1), every zone edge is a run a room
  cannot cross, and hand zoning cost floor.
- **Ritual (theatre, five storeys, tilted plates with an apse; the house takes the
  ground floor).** Exported from its music run; the unzoned round trip reproduces
  the run exactly: 69%, the same five back-of-house rooms unplaced. Zoned on the
  row runs: 40% on 3.9.0 -- every zone delivered nothing -- which is what exposed
  three kernel faults, fixed in 3.9.1:
  - `_stacking_groups` took one strip per module row, so a row that a stair
    door's corridor stub crossed anywhere was split into 4.4, 1.5 and 3.3 m pieces
    along its whole length and no room of 5 m could stand on it. Chains of
    contiguous strips now stack. Ritual unzoned: 69% to 79%, five unplaced to
    three (the plant room and the dressing rooms found their rows).
  - `rectangular_runs` blocked a whole run for a 0.1 mm sliver where a zone edge at
    4.598 met a row line at 4.5979. A missing piece thinner than half a millimetre
    is a rounding now, and the export writes rows at full precision.
  - Rooms did not know the approach landings: a riser closet stood over the ramp's
    top landing and the cafe took a millimetre of the entry landing. The landings
    on the entry storey, grown by a wall's thickness, are floor no room may take
    (`walked`); a zone may cover one and simply loses that floor.
- **Ritual zoned on 3.9.1:** the three top-floor zones and the fourth-floor plant
  zone deliver their rooms (plant 286 of 286, restrooms 159 of 161, plant and
  services 170 of 170, dressing and loading 199 of 216); the storage zone's row
  holds 56 m² after the corridor and reports the store by name; the foyer, bar and
  rehearsal room -- left to the allocator -- lose their floor to the zones and are
  reported unplaced. 69% against the unzoned 79%: zoning moved the shortfall from
  back of house to front of house on a massing whose rows total 2127 m² against
  a 2787 m² brief. That is the honest shape of this slice: control over which
  rooms a candidate is complete in, not more floor.
- **Tests:** `backend/tests/test_program_massing.py` -- a zone holds its rooms
  inside its rectangle and reports its numbers; a zone too small reports its room
  by name and spills nowhere; a zone in a core, an unknown space and a space named
  twice are refused by name; the brief export gives every number, the double
  height on both storeys.
- **Corpus:** the 20-recording recheck on 3.9.1
  (`artifacts/visual_audit/2026-09-03/recheck_3_9_1.json`, summarised in
  `docs/experiments/visual_music_audit_20.md`): unplaced spaces 32 on 11 tracks
  (3.9.0) to 20 on 7 tracks, all theatre back of house and two library rooms
  (cantina-blues 3, couperin-harpsichord 3, dama-may 2, raw 2, ritual 3, scp-outer-thoughts 4, valse-gymnopedie 3); spatial reports passed 13 of 20 with
  the seven failures the theatres' stage-access overlaps (concurrent seating
  work) -- Android Sock Hop's invalid envelope ring and Raw's overlaps are gone
  with the rooms that moved; dependency graph 20 of 20; no member open, no
  head-clearance violation; 59 minutes for the twenty, 86 to 290 s per candidate.
