"""Area program -> allocated zones on the lattice.

This is stage S6 of decision 0008, and it is the change that makes the plan itself
music-driven rather than merely rescaled.

Before: `LIBRARY_SPACE_SPECS` was 21 rows of literal `x0, x1, y0, y1`, and the later
fraction-of-bounding-box version was the same mistake at one remove -- the plan shape was
authored, and the score could only stretch it.

Now the brief states **areas and requirements**, and an allocator packs them onto whatever
plate the score produced:

    SpaceRequirement    340 m2 of open stacks, needs 7.18 kPa, prefers a low level,
                        daylight preferred, minimum dimension 6 m
            |
            v
    band decomposition  each level is cut into strips between the y grid lines, and each
            |           strip is measured against the actual plate polygon, minus voids
            |           and the core
            v
    greedy placement    spaces claim runs along the strips; daylight-required spaces get
            |           the perimeter strips first
            v
    ProgramAllocation   every space with its delivered area, its deviation from the
                        brief, and an explicit list of what did not fit

The last part is the point. A score that produces fewer or smaller plates genuinely
cannot hold the brief, and the allocator says so instead of quietly shrinking rooms.
"""

from __future__ import annotations

import math

import itertools

from typing import Literal

from pydantic import BaseModel, Field

from .datums import DatumSet, Lattice, LevelDatum
from .geometry import Vector2, point_inside

ProgramCategory = Literal['public', 'private', 'circulation', 'service']
LevelPreference = Literal['ground', 'low', 'any', 'high']
DaylightNeed = Literal['required', 'preferred', 'none']


class SpaceRequirement(BaseModel):
    """One line of the brief. No geometry, only requirements."""

    id: str
    space_type: str
    label: str
    category: ProgramCategory
    area_m2: float = Field(gt=0)
    min_dimension_m: float = Field(gt=0)
    level_preference: LevelPreference
    daylight: DaylightNeed
    occupancy_id: str
    adjacency: list[str] = Field(default_factory=list)
    reason: str
    # The fraction of the asked-for area below which this space has not been delivered.
    # Bands quantise, so a room a few per cent short of its ask is the grid rounding
    # and not a failure; a room a fifth short is a different room. The default is
    # generous and the rooms that *are* the building tighten it -- an auditorium at
    # eighty per cent is not a small auditorium, it is a theatre that does not work,
    # and it must not be able to hide inside an average.
    area_tolerance: float = Field(default=0.9, gt=0.0, le=1.0)


class AllocatedZone(BaseModel):
    space_id: str
    space_type: str
    label: str
    category: ProgramCategory
    occupancy_id: str
    level_index: int
    level_id: str
    # The structural row the zone starts in -- a real lattice coordinate, which is what
    # the elements built from this zone publish as their `lattice_index`. `Band.index`
    # is a per-level serial number now that one row can yield two strips, and exporting
    # it named a grid line that does not exist.
    band_index: int
    x0: float
    y0: float
    x1: float
    y1: float
    area_required_m2: float
    area_delivered_m2: float
    area_tolerance: float = 0.9
    daylight_satisfied: bool
    level_preference_satisfied: bool

    @property
    def deviation(self) -> float:
        return round(self.area_delivered_m2 / self.area_required_m2 - 1.0, 4)

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    @property
    def area_satisfied(self) -> bool:
        """Whether the delivered area met this space's own tolerance.

        Computed from the two numbers beside it rather than stored as a flag. `fits`
        used to mean only that a rectangle had been placed somewhere, so a 680 m2
        auditorium delivered at 546 m2 read as a space that fitted -- and a stored
        boolean would have carried its own way of being wrong: a default of True says
        "delivered" about a zone nobody measured, which is the exact shape of unearned
        status this project keeps removing. There is nothing here to leave stale.
        """
        return self.area_delivered_m2 >= self.area_required_m2 * self.area_tolerance


class UnplacedSpace(BaseModel):
    space_id: str
    label: str
    area_required_m2: float
    reason: str


class ProgramAllocation(BaseModel):
    schema_version: Literal['mta.program_allocation/1.0'] = 'mta.program_allocation/1.0'
    zones: list[AllocatedZone]
    unplaced: list[UnplacedSpace]
    # Levels whose plate could not carry its own cores: cutting them out left too
    # little to lay out on, so the bands were taken whole and the program shares the
    # floor with the stair. Recorded rather than hidden -- the spatial rules read this
    # to tell a consequence of a small plate from an oversight.
    cores_unreserved: list[str] = Field(default_factory=list)
    usable_area_by_level: dict[str, float]
    required_area_m2: float
    delivered_area_m2: float

    @property
    def short(self) -> list[AllocatedZone]:
        """Zones placed but not delivered to their own tolerance."""
        return [zone for zone in self.zones if not zone.area_satisfied]

    @property
    def fits(self) -> bool:
        """Every briefed space placed *and* delivered.

        This was `not self.unplaced` -- placement alone. A theatre whose auditorium
        came out a fifth short reported `fits` and a compliance roll-up of zero
        failures, because the room had been put somewhere. Being somewhere is not the
        requirement; the requirement is the area, and it is now read per space rather
        than averaged across the brief.
        """
        return not self.unplaced and not self.short

    @property
    def fulfilment(self) -> float:
        return round(self.delivered_area_m2 / self.required_area_m2, 4) \
            if self.required_area_m2 else 0.0

    def zones_on(self, level_index: int) -> list[AllocatedZone]:
        return [zone for zone in self.zones if zone.level_index == level_index]

    def governing_occupancy(self, level_index: int, live_loads: dict[str, float]) -> str:
        zones = self.zones_on(level_index)
        if not zones:
            return 'office'
        return max(zones, key=lambda z: live_loads.get(z.occupancy_id, 0.0)).occupancy_id


# ---------------------------------------------------------------------------
# The brief
# ---------------------------------------------------------------------------

LIBRARY_BRIEF: tuple[SpaceRequirement, ...] = (
    SpaceRequirement(
        id='SP-LOBBY', space_type='lobby_welcome_checkout', label='Lobby and welcome',
        category='circulation', area_m2=210.0, min_dimension_m=8.0,
        level_preference='ground', daylight='required',
        occupancy_id='lobby_first_corridor', adjacency=['SP-EXHIBITION', 'SP-CAFE'],
        reason='Arrival must meet a staffed point before the collection.'),
    SpaceRequirement(
        id='SP-EXHIBITION', space_type='exhibition_foyer', label='Exhibition foyer',
        category='public', area_m2=180.0, min_dimension_m=7.0,
        level_preference='ground', daylight='preferred',
        occupancy_id='assembly_movable_seats', adjacency=['SP-LOBBY'],
        reason='Public display works at the entry level without opening the collection.'),
    SpaceRequirement(
        id='SP-CAFE', space_type='cafe', label='Cafe',
        category='public', area_m2=140.0, min_dimension_m=6.0,
        level_preference='ground', daylight='required',
        occupancy_id='assembly_movable_seats', adjacency=['SP-LOBBY'],
        reason='After-hours operation from the entry zone.'),
    SpaceRequirement(
        id='SP-CHILDREN', space_type='children_reading', label='Children reading',
        category='public', area_m2=230.0, min_dimension_m=7.0,
        level_preference='low', daylight='required',
        occupancy_id='library_reading', adjacency=['SP-LOBBY'],
        reason='Short route from arrival; daylight is a constitution requirement.'),
    SpaceRequirement(
        id='SP-STACKS', space_type='open_stacks', label='Open stacks',
        category='public', area_m2=430.0, min_dimension_m=9.0,
        level_preference='low', daylight='preferred',
        occupancy_id='library_stacks', adjacency=['SP-ADULT'],
        reason='The governing floor load of the whole building at 7.18 kPa.'),
    SpaceRequirement(
        id='SP-ADULT', space_type='adult_reading', label='Adult reading room',
        category='public', area_m2=380.0, min_dimension_m=9.0,
        level_preference='any', daylight='required',
        occupancy_id='library_reading', adjacency=['SP-STACKS'],
        reason='The principal room; its clear span is the governing structural episode.'),
    SpaceRequirement(
        id='SP-PERIODICALS', space_type='periodicals_media', label='Periodicals and media',
        category='public', area_m2=210.0, min_dimension_m=6.0,
        level_preference='any', daylight='preferred',
        occupancy_id='library_reading', adjacency=['SP-ADULT'],
        reason='Browsing collection adjacent to reading.'),
    SpaceRequirement(
        id='SP-QUIET', space_type='quiet_reading', label='Quiet reading room',
        category='public', area_m2=260.0, min_dimension_m=8.0,
        level_preference='high', daylight='required',
        occupancy_id='library_reading', adjacency=[],
        reason='Separated from arrival noise; upper levels are the quiet end.'),
    SpaceRequirement(
        id='SP-SEMINAR', space_type='seminar', label='Seminar rooms',
        category='public', area_m2=170.0, min_dimension_m=6.0,
        level_preference='any', daylight='preferred',
        occupancy_id='assembly_fixed_seats', adjacency=['SP-QUIET'],
        reason='Group use, acoustically separable from the reading floor.'),
    SpaceRequirement(
        id='SP-SPECIAL', space_type='special_collections', label='Special collections',
        category='private', area_m2=150.0, min_dimension_m=6.0,
        level_preference='high', daylight='none',
        occupancy_id='library_stacks', adjacency=['SP-STAFF'],
        reason='Controlled access and no daylight; heavy sustained load.'),
    SpaceRequirement(
        id='SP-STAFF', space_type='staff_workroom', label='Staff workroom',
        category='private', area_m2=160.0, min_dimension_m=6.0,
        level_preference='any', daylight='preferred',
        occupancy_id='office', adjacency=['SP-SPECIAL', 'SP-PROCESSING'],
        reason='Back-of-house adjacent to processing and the service core.'),
    SpaceRequirement(
        id='SP-PROCESSING', space_type='collection_processing', label='Collection processing',
        category='service', area_m2=120.0, min_dimension_m=5.0,
        level_preference='low', daylight='none',
        occupancy_id='library_stacks', adjacency=['SP-STAFF'],
        reason='Receiving route to the collection without crossing the public floor.'),
    SpaceRequirement(
        id='SP-MECHANICAL', space_type='mechanical_room', label='Mechanical plant',
        category='service', area_m2=130.0, min_dimension_m=5.0,
        level_preference='high', daylight='none',
        occupancy_id='library_stacks', adjacency=[],
        reason='Plant at the top of the riser, away from reading rooms.'),
)


# ---------------------------------------------------------------------------
# Plate measurement
# ---------------------------------------------------------------------------

# The vertical cores used to be a fixed rectangle here -- 18.4, 5.2 to 21.4, 9.4,
# coordinates from the original thirty-six metre slab. The program was banded around a
# core that was not there, while the real one, positioned later by `_stair_anchor`,
# landed in whichever room happened to occupy its ground. A lift shaft took 41% of the
# refuse store on one model and nothing in the pipeline was in a position to notice:
# the program is allocated a hundred lines before the stairs are placed, so at the
# moment of the decision the information did not exist.
#
# It does now. The caller works the cores out first and hands them in.
Reservation = tuple[float, float, float, float]
DEFAULT_CIRCULATION_ALLOWANCE = 0.22   # used when the datum set predates the rule

# How much of a floor must survive the core reservation for it to be worth applying.
# Below this the plate is too small to lay out around its own cores, and cutting them
# out leaves nothing to allocate at all.
MIN_USABLE_AFTER_CORES = 0.45
_SAMPLES = 220


def polygon_area(polygon: list[Vector2]) -> float:
    total = 0.0
    for index in range(len(polygon)):
        a, b = polygon[index], polygon[(index + 1) % len(polygon)]
        total += a.x * b.y - b.x * a.y
    return abs(total) / 2.0


def plate_x_runs(
    plate: list[Vector2], y: float, blocked: list[tuple[float, float]] | None = None,
) -> list[tuple[float, float]]:
    """Every continuous run of plate at this y, with blocked x ranges removed.

    Sampling rather than exact clipping: the plate has a sampled apsidal end anyway, so
    an exact half-plane clip would give false precision. The sample count is fixed, which
    keeps the result deterministic.
    """
    x_lo = min(point.x for point in plate)
    x_hi = max(point.x for point in plate)
    step = (x_hi - x_lo) / _SAMPLES
    runs: list[tuple[float, float]] = []
    start: float | None = None
    for index in range(_SAMPLES + 1):
        x = x_lo + step * index
        inside = point_inside(plate, x, y)
        if inside and blocked:
            inside = not any(bx0 <= x <= bx1 for bx0, bx1 in blocked)
        if inside and start is None:
            start = x
        elif not inside and start is not None:
            runs.append((start, x - step))
            start = None
    if start is not None:
        runs.append((start, x_hi))
    return runs


def plate_x_span(
    plate: list[Vector2], y: float, blocked: list[tuple[float, float]] | None = None,
) -> tuple[float, float] | None:
    """The longest run at this y. Right for a row interrupted by nothing but its own
    edge; `plate_x_runs` is what a row with a core standing in it needs."""
    runs = plate_x_runs(plate, y, blocked)
    if not runs:
        return None
    return max(runs, key=lambda run: run[1] - run[0])


class Band(BaseModel):
    """One strip of a level between two structural grid lines."""

    index: int
    # The structural row this band lies in. One row can yield two bands where a core
    # splits it, so `index` is unique and `row` is what says which strips are stacked
    # above one another -- the thing a large room spans. Merging on `index` alone put
    # the two halves of one row together as though they were two rows, and counted the
    # same depth twice.
    row: int
    y0: float
    y1: float
    x0: float
    x1: float
    perimeter: bool

    @property
    def depth(self) -> float:
        return self.y1 - self.y0

    @property
    def length(self) -> float:
        return self.x1 - self.x0

    @property
    def area(self) -> float:
        return self.depth * self.length


def level_bands(level: LevelDatum, lattice: Lattice,
                reserved: tuple[Reservation, ...] = ()) -> list[Band]:
    bands: list[Band] = []
    rows = len(lattice.y_lines) - 1
    for index in range(rows):
        y0, y1 = lattice.y_lines[index], lattice.y_lines[index + 1]
        mid = (y0 + y1) / 2.0
        blocked: list[tuple[float, float]] = []
        for hole in level.voids:
            hy0 = min(p.y for p in hole)
            hy1 = max(p.y for p in hole)
            if hy0 < y1 and hy1 > y0:
                blocked.append((min(p.x for p in hole), max(p.x for p in hole)))
        for rx0, ry0, rx1, ry1 in reserved:
            if ry0 < y1 and ry1 > y0:
                blocked.append((rx0, rx1))
        # Every clear run, not the longest. A core standing in the middle of a row
        # leaves usable floor on both sides of it, and taking only the longer side threw
        # the other away -- which is how reserving 133 m2 of core cost 267 m2 of floor,
        # and why an atrium sterilised whichever side of itself was narrower.
        for x0_run, x1_run in plate_x_runs(level.plate, mid, blocked):
            if x1_run - x0_run < 4.0:
                continue
            bands.append(Band(index=len(bands), row=index, y0=y0, y1=y1,
                              x0=x0_run, x1=x1_run,
                              perimeter=index in (0, rows - 1)))
    return bands


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

_PREFERENCE_ORDER = {'ground': 0, 'low': 1, 'high': 2, 'any': 3}


def _allowed_levels(preference: LevelPreference, occupied: list[int]) -> list[int]:
    if not occupied:
        return []
    if preference == 'ground':
        return occupied[:1]
    if preference == 'low':
        return occupied[:max(1, len(occupied) // 2)]
    if preference == 'high':
        return occupied[max(1, len(occupied) // 2):] or occupied[-1:]
    return occupied


def _stacking_groups(bands: list[Band], max_rows: int) -> list[tuple[Band, ...]]:
    """Every set of strips a single room may be laid out across.

    Depends only on the strips, so it is found once per level rather than once
    per space per level.

    `max_rows` used to be the constant three -- enough for a reading room, and the
    reason a theatre's auditorium came out a fifth short: at three bays the largest
    rectangle its plate offers is 539 m2 against a 680 m2 ask, and at four it is 719.
    A room may stack as many rows as its own area needs. Small rooms are not dragged
    into deep groups by this, because the scoring below prefers the arrangement with
    the least waste and a small room in a deep group is nearly all waste.
    """
    # One strip per row, over adjacent rows. A contiguous slice of the band list was
    # enough while a row yielded one band; now that a core splits a row in two, the left
    # half of row 3 and the left half of row 4 are not adjacent in the list, and the
    # slice missed exactly the stacking a large room wants. Whether a chosen pair really
    # shares ground is left to `try_place`, which intersects their runs.
    by_row: dict[int, list[Band]] = {}
    for band in bands:
        by_row.setdefault(band.row, []).append(band)
    rows_present = sorted(by_row)
    groups: list[tuple[Band, ...]] = []
    for span_rows in range(1, max_rows + 1):
        for start_index in range(len(rows_present) - span_rows + 1):
            chosen_rows = rows_present[start_index:start_index + span_rows]
            if any(chosen_rows[k + 1] != chosen_rows[k] + 1
                   for k in range(len(chosen_rows) - 1)):
                continue
            groups.extend(itertools.product(
                *(by_row[row] for row in chosen_rows)))

    return groups


def allocate_program(
    lattice: Lattice, datums: DatumSet,
    brief: tuple[SpaceRequirement, ...] = LIBRARY_BRIEF,
    reserved: tuple[Reservation, ...] = (),
    *,
    carved: dict[int, tuple[Reservation, ...]] | None = None,
    preplaced: tuple[AllocatedZone, ...] = (),
    precluded: tuple[UnplacedSpace, ...] = (),
) -> ProgramAllocation:
    """Lay the brief out on the plates, around whatever already stands on them.

    `reserved` is the cores, on every level alike, and may be waived on a plate too
    small to carry its own (see below). The three keyword parameters are the
    archetype's, and they are different in kind: `carved` is floor an archetype has
    taken, per level, and is never waived -- an auditorium is not a stair that a small
    plate can choose to overlap; `preplaced` are the archetype's own rooms, which
    enter the result as delivered zones without passing through the bands; and
    `precluded` are rooms an archetype claims but could not build here, reported
    unplaced with the archetype's reason so the plate fit grows toward a plate that
    can, instead of housing them as the flat rectangles the archetype exists to
    replace.
    """
    try:
        allowance = datums.value('circulation_allowance')
    except KeyError:
        allowance = DEFAULT_CIRCULATION_ALLOWANCE

    occupied = [level.index for level in lattice.occupied]
    # Reserve the cores where the floor can carry them, and say so where it cannot.
    #
    # A core is a real obstruction and the program has to be laid out around it -- that
    # is the whole point of reserving it. But `level_bands` measures a row as one
    # continuous run, so an obstruction in the middle of a row costs the shorter side
    # as well as itself. On a wide plate that is a few per cent; on a nineteen-metre
    # tower it took every band on every floor and left twenty-two spaces unplaced and a
    # building with no rooms in it.
    #
    # So the reservation is applied where it leaves a floor to lay out on, and where it
    # does not the bands are taken unreserved and the overlap is left for the spatial
    # rules to report. A stated compromise beats an empty building, and beats a silent
    # one either way.
    bands_by_level: dict[int, list[Band]] = {}
    unreserved_levels: list[str] = []
    for level in lattice.occupied:
        # Carved floor is in both the gross and the cut bands, so the core fallback
        # below can waive the cores but can never waive the archetype.
        carve_here = tuple((carved or {}).get(level.index, ()))
        gross = level_bands(level, lattice, carve_here)
        cut = level_bands(level, lattice, tuple(reserved) + carve_here) \
            if reserved else gross
        gross_area = sum(band.area for band in gross)
        cut_area = sum(band.area for band in cut)
        if reserved and (not cut or cut_area < gross_area * MIN_USABLE_AFTER_CORES):
            bands_by_level[level.index] = gross
            unreserved_levels.append(level.id)
        else:
            bands_by_level[level.index] = cut
    # remaining run per band, consumed left to right
    cursor: dict[tuple[int, int], float] = {
        (level_index, band.index): band.x0
        for level_index, bands in bands_by_level.items() for band in bands}

    usable: dict[str, float] = {}
    capacity: dict[int, float] = {}
    for level in lattice.occupied:
        area = sum(band.area for band in bands_by_level[level.index])
        usable[level.id] = round(area, 2)
        capacity[level.index] = area * (1.0 - allowance)

    # The archetype's rooms are settled either way -- placed or refused -- so the
    # allocator neither lays them out again nor lets their depth inflate `max_rows`.
    settled = ({zone.space_id for zone in preplaced}
               | {space.space_id for space in precluded})
    pending = [space for space in brief if space.id not in settled]

    ordered = sorted(
        pending,
        key=lambda space: (_PREFERENCE_ORDER[space.level_preference], -space.area_m2))

    # How many rows the deepest room in this brief could want: its area laid out at
    # its own minimum width, in bays. Bounded because the group count doubles with each
    # row a split can appear in, and a room deeper than six bays is a corridor.
    typical_bay = max(1.0, (lattice.y_lines[-1] - lattice.y_lines[0])
                      / max(1, len(lattice.y_lines) - 1))
    wanted = max((space.area_m2 / space.min_dimension_m for space in pending),
                 default=0.0)
    max_rows = max(3, min(6, math.ceil(wanted / typical_bay)))
    groups_by_level = {index: _stacking_groups(bands, max_rows)
                       for index, bands in bands_by_level.items()}

    zones: list[AllocatedZone] = list(preplaced)
    unplaced: list[UnplacedSpace] = list(precluded)

    def try_place(
        space: SpaceRequirement, level_index: int, tolerance: float,
    ) -> AllocatedZone | None:
        """Fit one space on one level, letting a large room span adjacent strips.

        A 380 m2 reading room does not fit in one 7 m strip without becoming a 50 m
        corridor, so the allocator tries one, two, then three adjacent structural rows,
        taking one strip from each -- a row yields two where a core stands in the middle
        of it -- and keeps the shallowest arrangement that delivers the area at a sensible
        proportion. That is what a designer does with a bay grid, and it is why the room
        dimensions move when the score moves the grid.
        """
        level = lattice.level(level_index)
        best: AllocatedZone | None = None
        best_score: tuple[int, float, int] | None = None
        groups = groups_by_level[level_index]
        for group in groups:
            span = len(group)
            depth = sum(band.depth for band in group)
            if depth < space.min_dimension_m and span < max_rows:
                continue
            start = max(cursor[(level_index, band.index)] for band in group)
            limit = min(band.x1 for band in group)
            remaining = limit - start
            width = space.area_m2 / depth
            if width < space.min_dimension_m:
                width = space.min_dimension_m
            if remaining < width * tolerance:
                continue
            width = min(width, remaining)
            delivered = width * depth
            perimeter = any(band.perimeter for band in group)
            candidate = AllocatedZone(
                space_id=space.id, space_type=space.space_type, label=space.label,
                category=space.category, occupancy_id=space.occupancy_id,
                level_index=level_index, level_id=level.id,
                band_index=group[0].row,
                x0=round(start, 3), y0=round(group[0].y0, 3),
                x1=round(start + width, 3), y1=round(group[-1].y1, 3),
                area_required_m2=space.area_m2,
                area_delivered_m2=round(delivered, 2),
                area_tolerance=space.area_tolerance,
                daylight_satisfied=(space.daylight != 'required') or perimeter,
                level_preference_satisfied=False)
            # prefer the arrangement that delivers the area with the fewest strips
            # and the least waste, and that satisfies daylight when it is required
            score = (
                0 if candidate.daylight_satisfied else 1,
                abs(candidate.area_delivered_m2 - space.area_m2),
                span,
            )
            if best_score is None or score < best_score:
                best, best_score = candidate, score
        return best

    for space in ordered:
        preferred = _allowed_levels(space.level_preference, occupied)
        fallback = [index for index in occupied if index not in preferred]
        chosen: AllocatedZone | None = None

        # first pass insists on the full area, second accepts a truncated room rather
        # than reporting a space as unplaceable when a partial fit exists
        for tolerance in (1.0, 0.55):
            for level_index in preferred + fallback:
                if capacity.get(level_index, 0.0) < space.area_m2 * 0.45:
                    continue
                if not bands_by_level.get(level_index):
                    continue
                candidate = try_place(space, level_index, tolerance)
                if candidate is None:
                    continue
                candidate.level_preference_satisfied = level_index in preferred
                chosen = candidate
                break
            if chosen:
                break

        if chosen is None:
            unplaced.append(UnplacedSpace(
                space_id=space.id, label=space.label, area_required_m2=space.area_m2,
                reason=('no run of contiguous bands on any occupied level can hold '
                        f'{space.area_m2:.0f} m2 at a minimum dimension of '
                        f'{space.min_dimension_m:.1f} m; the score produced '
                        f'{len(occupied)} occupied levels totalling '
                        f'{sum(usable.values()):.0f} m2 of usable plate')))
            continue

        zones.append(chosen)
        # A room consumes the strips it actually stands on: the ones inside its depth
        # *and* overlapping its length. Advancing every strip in the depth band was
        # right while a row yielded one strip, and became wrong the moment a core could
        # split a row in two -- a room laid out west of a stair wrote its finishing edge
        # into the cursor of the strip east of it, which starts further east still. The
        # cursor then read behind that strip's own beginning, and the next room started
        # from it and ran clean through the core. That is how a foyer came to span the
        # whole plate with the lift shaft standing inside it. A cursor is a record of
        # floor already given away, so it only ever moves forward.
        consumed = chosen.x1 + 0.6
        for band in bands_by_level[chosen.level_index]:
            if not (chosen.y0 - 0.01 <= band.y0 and band.y1 <= chosen.y1 + 0.01):
                continue
            if band.x1 <= chosen.x0 or band.x0 >= chosen.x1:
                continue
            key = (chosen.level_index, band.index)
            cursor[key] = max(cursor[key], consumed)
        capacity[chosen.level_index] -= chosen.area_delivered_m2

    return ProgramAllocation(
        zones=zones, unplaced=unplaced, cores_unreserved=unreserved_levels,
        usable_area_by_level=usable,
        required_area_m2=round(sum(space.area_m2 for space in brief), 2),
        delivered_area_m2=round(sum(zone.area_delivered_m2 for zone in zones), 2))
