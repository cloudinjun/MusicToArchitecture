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
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points, unary_union

from .plan_regions import PLAN_EPS_M, rectangular_runs, usable_region

from .datums import DatumSet, Lattice, LevelDatum
from .geometry import Vector2, point_inside
from .program_volume_contracts import is_exact_registered_room

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


class GivenZone(BaseModel):
    """Floor a program massing assigned to a group of briefed spaces (decision 0023).

    Coarse on purpose: whoever writes it -- a designer, or a model reading the brief
    and the plates -- says which rooms share which part of which floor. The
    allocator lays them out inside the rectangle and measures what did not fit; it
    does no arithmetic on the writer's behalf and never spills a room elsewhere.
    """

    label: str
    level_index: int
    rect: tuple[float, float, float, float]
    space_ids: list[str]


class ZoneReport(BaseModel):
    """What a given zone held: the numbers a writer needs to enlarge or split it."""

    label: str
    level_id: str
    rect: tuple[float, float, float, float]
    area_rect_m2: float
    # Inside the rectangle: the usable floor (plate minus voids, cores and carved
    # floor), and the whole structural rows of it left after the public corridors
    # and the entrance approach took theirs -- the floor a room can actually stand on.
    area_usable_m2: float
    area_rows_m2: float
    area_required_m2: float
    area_delivered_m2: float
    placed: list[str]
    unplaced: list[str]


class PublicPath(BaseModel):
    level_id: str
    target_id: str
    points: list[tuple[float, float]]


class PublicCirculationPlan(BaseModel):
    """Reserved floor, pending independent checks of the emitted building."""
    clear_width_m: float = 1.2
    wall_allowance_m: float
    paths: list[PublicPath] = Field(default_factory=list)
    aprons: dict[str,list[list[tuple[float,float]]]] = Field(default_factory=dict)
    unresolved: dict[str, str] = Field(default_factory=dict)
    basis: str = ('Public circulation planning reservation; physical obstruction, '
                  'door operation, code width and discharge require emitted-model review.')


class ProgramAllocation(BaseModel):
    schema_version: Literal['mta.program_allocation/1.0'] = 'mta.program_allocation/1.0'
    zones: list[AllocatedZone]
    unplaced: list[UnplacedSpace]
    # Legacy payload field. New allocations never waive core reservations. Old
    # runs may still carry this list; it must not excuse a measured collision.
    cores_unreserved: list[str] = Field(default_factory=list)
    usable_area_by_level: dict[str, float]
    required_area_m2: float
    delivered_area_m2: float
    public_circulation: PublicCirculationPlan | None = None
    # Given zones (decision 0023), one report each, in the massing's order.
    zone_reports: list[ZoneReport] = Field(default_factory=list)

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
# Clear plan distance kept between allocated room rectangles.  The same value must
# be used while reserving future Program Volume claims and after a room is committed;
# otherwise an early spill room can leave a claim visible to the search and erase it
# when the level bands are rebuilt.
ROOM_SEPARATION_M = 0.6

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
                reserved: tuple[Reservation, ...] = (), *, region=None,
                split_y=()) -> list[Band]:
    """Inscribed rectangular strips measured against the full usable region."""
    if region is None:
        region = usable_region(level, reserved)
    if region.is_empty:
        return []
    bands: list[Band] = []
    # Rows follow the module the plate was laid out on, not every structural line:
    # the structure is drawn to the cores (decision 0022) and a core face would
    # otherwise split a row into a strip no room can use.
    row_lines = lattice.band_lines or lattice.y_lines
    rows = len(row_lines) - 1
    for index in range(rows):
        lower, upper = row_lines[index], row_lines[index + 1]
        stops = sorted({lower, upper, *(y for y in split_y if lower < y < upper)})
        for y0, y1 in zip(stops, stops[1:]):
            if y1 - y0 < 0.05:
                continue  # two split lines a rounding apart, not a strip
            for x0_run, x1_run in rectangular_runs(region, y0, y1):
                if x1_run - x0_run < 4.0:
                    continue
                bands.append(Band(index=len(bands), row=index, y0=y0, y1=y1,
                                  x0=x0_run, x1=x1_run,
                                  perimeter=index in (0, rows - 1)))
    return bands


class PublicCirculationPlanner:
    """Protect a connected public floor network before consuming it with rooms.

    Core terminals are actual landing points. A room joins only from a supported
    exterior approach, routed around the complete room and every earlier room.
    No service-room interior is an edge of this graph.
    """
    def __init__(self, lattice, *, obstacles, terminals, preplaced=(), aprons=None,
                 protected=None):
        from .partitions import PARTITION_TYPES
        self.plan = PublicCirculationPlan(
            wall_allowance_m=max(p.thickness_mm for p in PARTITION_TYPES)/2000)
        self.radius = self.plan.clear_width_m/2 + self.plan.wall_allowance_m
        # A gap between two room rectangles becomes a usable cross-corridor only
        # after both partition allowances and the full planning body fit inside it.
        # ROOM_SEPARATION_M remains the ordinary non-circulation clearance.
        routed_gap = math.ceil(
            (2 * self.radius + PLAN_EPS_M) * 1000.0) / 1000.0
        self.room_separation_m = max(ROOM_SEPARATION_M, routed_gap)
        self.levels = {level.index: level for level in lattice.occupied}
        self.shared_owners = {space_id for region in getattr(lattice,'program_volume_regions',())
                              if region.shared_route_volume_ids for space_id in region.space_ids}
        self.fixed = {index: unary_union(parts) for index, parts in obstacles.items()}
        self.rooms = {index: [] for index in self.levels}
        for zone in preplaced:
            self.rooms[zone.level_index].append(box(zone.x0,zone.y0,zone.x1,zone.y1))
        self.routes = {index: [] for index in self.levels}
        # A room branch must terminate at an actual protected stair.  The route
        # network can be much nearer at the middle of a long two-core bypass, while
        # both stairs remain a full detour away along that network.
        self.stair_roots = {index: [] for index in self.levels}
        self.aprons = aprons or {}
        # Gross Program Volume owners are temporary path-planning authority.  They
        # keep the core network and preplaced-archetype routes from consuming a future
        # room before allocation gets its first claim; they never become permanent
        # obstructions or appear in the serialized circulation plan.
        self.protected = {index:{sid:region for sid,region in regions.items()
                                  if sid not in self.shared_owners}
                          for index,regions in (protected or {}).items()}
        for index,regions in self.aprons.items():
            self.plan.aprons[self.levels[index].id] = [list(region.exterior.coords)[:-1]
                                                     for region in regions]
        for index, entries in terminals.items():
            for target_id, candidates in entries:
                self._terminal(index, target_id, candidates)

    @staticmethod
    def _shape(points):
        return Point(points[0]) if len(points)==1 else LineString(points)

    def reserved(self, index):
        return unary_union([*[region.buffer(self.plan.wall_allowance_m,join_style='mitre').intersection(
                                  usable_region(self.levels[index]))
                              for region in self.aprons.get(index,[])],
                            *[self._shape(path).buffer(self.radius, join_style='round')
                              for path in self.routes[index]]])

    def split_y(self, index):
        values = [p[1]+sign*self.radius for path in self.routes[index]
                  for p in path for sign in (-1,1)]
        values += [y+sign*self.plan.wall_allowance_m for region in self.aprons.get(index,[])
                   for y,sign in ((region.bounds[1],-1),(region.bounds[3],1))]
        # Allocation removes the room plus the clearance this planner computed.
        # Split at that actual buffered edge: splitting only at the room wall lets
        # `rectangular_runs` project the clearance nib into the whole adjacent
        # structural row and discard otherwise continuous Program Volume floor.
        return values + [y + sign * self.room_separation_m
                         for room in self.rooms[index]
                         for y, sign in ((room.bounds[1], -1),
                                         (room.bounds[3], 1))]

    def _domain(self, index, extra=()):
        region = usable_region(self.levels[index]).buffer(-self.radius, join_style='mitre')
        cuts = [self.fixed.get(index,Polygon()), *self.rooms[index], *extra]
        return region.difference(unary_union(cuts).buffer(self.radius, join_style='mitre'))

    def _connection(self, index, candidates, extra=(), *, roots=()):
        from .navigation import WalkMesh, orthogonal_route, polygons
        mesh = WalkMesh(self._domain(index, extra))
        corners = [point for poly in polygons(mesh.domain)
                   for ring in [poly.exterior,*poly.interiors] for point in ring.coords]

        network = unary_union([self._shape(path) for path in self.routes[index]])
        root_targets = list(dict.fromkeys(roots))
        best = None
        for point in candidates:
            if mesh.locate(point) is None:
                continue
            if network.is_empty:
                return [point]
            # Allocated rooms route to a real stair root.  Other authored terminals
            # may still join the closest point on the already connected network.
            # Every intervening segment is checked through the full eroded floor.
            targets = list(root_targets)
            if not targets:
                targets = [tuple(nearest_points(Point(point),network)[1].coords[0])]
                targets.extend(path[0] for path in self.routes[index])
            for target in dict.fromkeys(targets):
                path = orthogonal_route(mesh.domain, point, target,
                                        mesh=mesh, corners=corners)
                if path is not None:
                    length = sum(math.dist(a,b) for a,b in zip(path,path[1:]))
                    if best is None or length < best[0]:
                        best = length,path
        return best[1] if best else None

    def _record(self, index, target_id, path):
        self.routes[index].append(path)
        self.plan.paths.append(PublicPath(level_id=self.levels[index].id,
                                         target_id=target_id,points=path))

    def _terminal(self, index, target_id, candidates):
        avoid = [region for space_id, region
                 in self.protected.get(index, {}).items()
                 if space_id != target_id]
        path = (self._connection(index, candidates, avoid)
                if self.routes[index] or target_id.startswith('STAIR-') else None)
        if path is None:
            self.plan.unresolved[f'{self.levels[index].id}:{target_id}'] = (
                'No continuous public corridor fits on the plate around cores, holes '
                'and the full archetype rooms at the declared planning width.')
        else:
            self._record(index,target_id,path)
            if target_id.startswith('STAIR-'):
                self.stair_roots[index].append(path[0])

    def network_distance(self, index, region) -> float:
        """Plan distance from a region to the already protected public network."""
        network = unary_union([self._shape(path) for path in self.routes[index]])
        return float(region.distance(network)) if not network.is_empty else math.inf

    def room_connection(self, zone, *, avoid=()):
        index = zone.level_index
        if not self.routes[index]:
            return None
        r = self.radius + PLAN_EPS_M*10
        x0,y0,x1,y1 = zone.x0,zone.y0,zone.x1,zone.y1
        if getattr(zone,'space_id',None) in self.shared_owners:
            # An explicitly shared foyer joins from its interior. Its whole body
            # still fits the floor and cores, and this path must reach a real stair.
            return self._connection(index,[((x0+x1)/2,(y0+y1)/2)],avoid,
                                    roots=self.stair_roots[index])
        # Each candidate leaves space for a full two-sided door approach along
        # a straight room edge. Its outside centre joins the existing network.
        points = []
        for lo,hi,fixed,horizontal in ((x0,x1,y0-r,True),(x0,x1,y1+r,True),
                                      (y0,y1,x0-r,False),(y0,y1,x1+r,False)):
            if hi-lo < 2*r:
                continue
            positions = [(lo+hi)/2,lo+r,hi-r]
            points.extend((p,fixed) if horizontal else (fixed,p) for p in positions)
        return self._connection(
            index, points, [box(x0, y0, x1, y1), *avoid],
            roots=self.stair_roots[index])

    def commit_room(self, zone, path):
        if zone.space_id not in self.shared_owners:
            self.rooms[zone.level_index].append(box(zone.x0,zone.y0,zone.x1,zone.y1))
        self._record(zone.level_index,zone.space_id,path)


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

_PREFERENCE_ORDER = {'ground': 0, 'low': 1, 'high': 2, 'any': 3}
# How far a given zone may overhang the usable floor before it is refused (decision
# 0023): two centimetres, the size of a rounding, not of a room.
ZONE_SNAP_M = 0.02


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

    A group is a chain of strips each starting where the one below ends and
    overlapping it in plan by at least a usable run, up to `max_rows` module rows
    of depth. The chain may cross module rows or run through the pieces a corridor
    split one row into. Grouping one strip per *row* -- the previous rule -- meant
    a row that a stair door's corridor stub crossed anywhere was split into shallow
    pieces along its whole length and could never be used at its full depth: on a
    theatre's upper floors that left 300 m2 rows holding nothing while the plant
    room and the dressing rooms were reported unplaced (decision 0023).
    """
    # A strip thinner than a wall is a rounding between two split lines, not floor,
    # and one that starts where it ends would chain to itself forever.
    usable = [band for band in bands if band.depth >= 0.05]
    by_start: dict[float, list[Band]] = {}
    for band in usable:
        by_start.setdefault(round(band.y0, 4), []).append(band)
    row_depth = max((band.depth for band in usable), default=0.0)
    max_depth = max_rows * row_depth + 1e-6
    groups: list[tuple[Band, ...]] = []
    pending: list[tuple[tuple[Band, ...], float]] = [((band,), band.depth) for band in usable]
    while pending:
        chain, depth = pending.pop()
        groups.append(chain)
        top = chain[-1]
        for above in by_start.get(round(top.y1, 4), []):
            if above.y0 <= top.y0 or depth + above.depth > max_depth:
                continue
            if min(top.x1, above.x1) - max(top.x0, above.x0) < 4.0:
                continue
            pending.append((chain + (above,), depth + above.depth))
    return groups


def allocate_program(
    lattice: Lattice, datums: DatumSet,
    brief: tuple[SpaceRequirement, ...] = LIBRARY_BRIEF,
    reserved: tuple[Reservation, ...] = (),
    *,
    carved: dict[int, tuple[Reservation, ...]] | None = None,
    preplaced: tuple[AllocatedZone, ...] = (),
    precluded: tuple[UnplacedSpace, ...] = (),
    public_circulation: PublicCirculationPlanner | None = None,
    zoned: tuple[GivenZone, ...] = (),
    walked: dict[int, tuple] | None = None,
) -> ProgramAllocation:
    """Lay the brief out on the plates, around whatever already stands on them.

    `reserved` is the cores, on every level alike, and is never waived. Per-level
    reservations already carried by the lattice include given cores and Program
    Volume circulation roles; they are also never waived. The three keyword
    parameters are the
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
    by_id = {space.id: space for space in brief}

    # Program Volumes author a gross room position before the detailed kernel has
    # negotiated cores and public routes (decision 0024).  Keep that position as a
    # preference, not a fixed GivenZone: try the authored storey and rectangle first,
    # then retain the existing measured fallback when coordination makes it unusable.
    # This is the seam between the two program representations -- the volume still
    # makes the form, while ProgramAllocation remains honest about what fitted.
    level_index_by_id = {level.id: level.index for level in lattice.occupied}
    authored_regions: dict[str, tuple[int, Polygon]] = {}
    shared_route_claims = {}
    regions_by_id = {region.id:region for region in getattr(lattice,'program_volume_regions',())}
    program_regions_by_level: dict[int, list[Polygon]] = {}
    for region in getattr(lattice, 'program_volume_regions', ()):
        if region.role not in ('program', 'archetype'):
            continue
        level_index = level_index_by_id.get(region.level_id)
        if level_index is None:
            raise ValueError(
                f'{region.id} assigns program to unknown occupied level {region.level_id}')
        footprint = box(*region.resolve_bounds(lattice))
        program_regions_by_level.setdefault(level_index, []).append(footprint)
        for space_id in region.space_ids:
            if space_id in authored_regions:
                raise ValueError(
                    f'{space_id} is assigned to more than one Program Volume region')
            authored_regions[space_id] = (level_index, footprint)
            if region.shared_route_volume_ids:
                shared_route_claims[space_id] = {
                    tuple(regions_by_id[identifier].resolve_bounds(lattice))
                    for identifier in region.shared_route_volume_ids}
    program_floor_by_level = {
        level_index: unary_union(footprints)
        for level_index, footprints in program_regions_by_level.items()
    }

    def reservations_for(index: int, *, include_carved: bool = True, owner_id=None
                         ) -> tuple[Reservation, ...]:
        """All non-room claims on one level, without counting a rectangle twice."""
        level = lattice.level(index)
        shared = shared_route_claims.get(owner_id, set())
        # Only named public-floor carriers may be shared. The separately supplied
        # real core reservations, voids and archetype claims remain unconditional.
        claims = [*reserved, *(claim for claim in getattr(level,'reserved',())
                               if tuple(claim) not in shared)]
        if include_carved:
            claims.extend((carved or {}).get(index, ()))
        return tuple(dict.fromkeys(tuple(claim) for claim in claims))

    # Floor is laid out per *slot*: one slot per occupied level for the brief at
    # large, and one per given zone (decision 0023), which is its rectangle on its
    # level. A zone's floor is taken out of its level's slot, so the rest of the
    # brief keeps out of it, and the zone's own rooms never leave it.
    zone_slots: dict[tuple, GivenZone] = {('Z', zi): zone for zi, zone in enumerate(zoned)}
    zone_floor: dict[int, list] = {}
    for zone in zoned:
        level = lattice.level(zone.level_index)
        if level.index not in occupied:
            raise ValueError(f"zone '{zone.label}' is on {level.id}, which is not an "
                             f"occupied storey")
        footprint = box(*zone.rect)
        if footprint.is_empty or footprint.area <= 0.0:
            raise ValueError(f"zone '{zone.label}' on {level.id} has no area")
        reservations = reservations_for(level.index)
        # A zone is a coarse instruction: a hairline over a void's edge -- the carve
        # grows its rectangle by a tenth of a millimetre -- is not a zone in a void.
        # The rooms are laid out on the intersection with the usable floor anyway.
        if not usable_region(level, reservations).buffer(ZONE_SNAP_M).covers(footprint):
            raise ValueError(f"zone '{zone.label}' on {level.id} stands outside the "
                             f"usable floor: off the plate, in a void, in a stair core "
                             f"or in floor the archetype carved")
        for other in zone_floor.get(level.index, []):
            if other.intersection(footprint).area > PLAN_EPS_M:
                raise ValueError(f"zone '{zone.label}' on {level.id} overlaps another zone")
        unknown = [sid for sid in zone.space_ids if sid not in by_id]
        if unknown:
            raise ValueError(f"zone '{zone.label}' names spaces not in the brief: "
                             f"{', '.join(unknown)}; the brief has "
                             f"{', '.join(space.id for space in brief)}")
        zone_floor.setdefault(level.index, []).append(footprint)
    named = [sid for zone in zoned for sid in zone.space_ids]
    if len(named) != len(set(named)):
        twice = sorted({sid for sid in named if named.count(sid) > 1})
        raise ValueError(f"spaces named in two zones: {', '.join(twice)}")

    slot_level: dict = {level.index: level.index for level in lattice.occupied}
    for slot, zone in zone_slots.items():
        slot_level[slot] = zone.level_index

    def base_region(slot):
        index = slot_level[slot]
        level = lattice.level(index)
        reservations = reservations_for(index)
        region = usable_region(level, reservations)
        # `walked` is floor a person steps onto -- the approach's landings on the
        # entry storey -- which no room may take but which a zone may cover: it
        # is excluded from the zone's floor rather than refusing the zone.
        for rect in (walked or {}).get(index, ()):
            region = region.difference(box(*rect))
        if slot in zone_slots:
            return region.intersection(box(*zone_slots[slot].rect))
        if zone_floor.get(index):
            region = region.difference(unary_union(zone_floor[index]))
        return region

    # A core is an obstruction even on a small floor. The fit stage may grow the
    # plate or report unplaced rooms; it must never make a core disappear to fit.
    bands_by_level: dict = {}
    regions_by_level = {}
    zone_usable: dict[tuple, float] = {}
    for slot in slot_level:
        index = slot_level[slot]
        level = lattice.level(index)
        regions_by_level[slot] = base_region(slot)
        if slot in zone_slots:
            zone_usable[slot] = regions_by_level[slot].area
        if public_circulation is not None:
            regions_by_level[slot] = regions_by_level[slot].difference(
                public_circulation.reserved(index))
        bands_by_level[slot] = level_bands(level, lattice,
            region=regions_by_level[slot],
            split_y=public_circulation.split_y(index) if public_circulation else ())
    # remaining run per band, consumed left to right
    cursor: dict[tuple, float] = {
        (slot, band.index): band.x0
        for slot, bands in bands_by_level.items() for band in bands}

    usable: dict[str, float] = {}
    capacity: dict = {}
    for level in lattice.occupied:
        area = sum(band.area for band in bands_by_level[level.index])
        zone_area = sum(band.area for slot, zone in zone_slots.items()
                        if zone.level_index == level.index
                        for band in bands_by_level[slot])
        usable[level.id] = round(area + zone_area, 2)
        capacity[level.index] = area * (1.0 - allowance)
    for slot in zone_slots:
        capacity[slot] = sum(band.area for band in bands_by_level[slot]) * (1.0 - allowance)

    # The archetype's rooms are settled either way -- placed or refused -- so the
    # allocator neither lays them out again nor lets their depth inflate `max_rows`.
    # A zone's rooms are laid out in their zone, below, and are not pending either.
    settled = ({zone.space_id for zone in preplaced}
               | {space.space_id for space in precluded} | set(named))
    pending = [space for space in brief if space.id not in settled]
    zone_spaces = [by_id[sid] for sid in named]

    ordered = sorted(
        pending,
        key=lambda space: (_PREFERENCE_ORDER[space.level_preference], -space.area_m2))

    # How many rows the deepest room in this brief could want: its area laid out at
    # its own minimum width, in bays. Bounded because the group count doubles with each
    # row a split can appear in, and a room deeper than six bays is a corridor.
    typical_bay = max(1.0, (lattice.y_lines[-1] - lattice.y_lines[0])
                      / max(1, len(lattice.y_lines) - 1))
    wanted = max((space.area_m2 / space.min_dimension_m
                  for space in pending + zone_spaces), default=0.0)
    max_rows = max(3, min(6, math.ceil(wanted / typical_bay)))
    groups_by_level = {index: _stacking_groups(bands, max_rows)
                       for index, bands in bands_by_level.items()}
    connections = {}

    zones: list[AllocatedZone] = []
    unplaced: list[UnplacedSpace] = list(precluded)
    # An archetype is not exempt from floor coverage. Its own carved reservation
    # is excluded here, but holes and real cores still constrain the room.
    for zone in preplaced:
        level = lattice.level(zone.level_index)
        footprint = box(zone.x0, zone.y0, zone.x1, zone.y1)
        region = usable_region(
            level, reservations_for(level.index, include_carved=False))
        if footprint.is_empty or not region.buffer(PLAN_EPS_M).covers(footprint):
            unplaced.append(UnplacedSpace(
                space_id=zone.space_id, label=zone.label,
                area_required_m2=zone.area_required_m2,
                reason='Preplaced archetype room is outside the usable floor or overlaps a core.'))
            continue
        zones.append(zone.model_copy(update={'area_delivered_m2': round(footprint.area, 2)}))

    def placement_candidates(
        space: SpaceRequirement, slot, tolerance: float, *, required_region=None,
    ) -> list[tuple[tuple, AllocatedZone]]:
        """Fit one space on one level, letting a large room span adjacent strips.

        A 380 m2 reading room does not fit in one 7 m strip without becoming a 50 m
        corridor, so the allocator tries one, two, then three adjacent structural rows,
        taking one strip from each -- a row yields two where a core stands in the middle
        of it -- and keeps the shallowest arrangement that delivers the area at a sensible
        proportion. That is what a designer does with a bay grid, and it is why the room
        dimensions move when the score moves the grid.
        """
        level_index = slot_level[slot]
        level = lattice.level(level_index)
        candidate_region = regions_by_level[slot]
        if required_region is not None:
            authored = authored_regions.get(space.id)
            if (space.id in shared_route_claims and authored is not None
                    and authored[0] == level_index and required_region.equals(authored[1])):
                candidate_region = usable_region(level,
                    reservations_for(level_index,owner_id=space.id))
                obstacles = [box(z.x0,z.y0,z.x1,z.y1) for z in zones
                             if z.level_index == level_index]
                obstacles += [box(*rect) for rect in (walked or {}).get(level_index,())]
                candidate_region = candidate_region.difference(unary_union(obstacles))
            candidate_region = candidate_region.intersection(required_region)
            # A room already authored at its required size is measured directly.
            # Repacking it into global strips discards free XY proportions and can
            # make a 2 m service room disappear behind the 4 m legacy strip filter.
            rect = required_region.bounds
            if is_exact_registered_room(rect, space.area_m2, space.min_dimension_m):
                footprint = box(*rect)
                if not candidate_region.buffer(PLAN_EPS_M).covers(footprint):
                    return []  # cores, holes and protected routes keep their authority
                x0, y0, x1, y1 = rect
                lines = lattice.band_lines or lattice.y_lines
                row = max(0, next((i for i, y in enumerate(lines[1:]) if y > y0), 0))
                perimeter = footprint.boundary.intersection(Polygon(
                    [(p.x, p.y) for p in level.plate]).boundary).length > PLAN_EPS_M
                candidate = AllocatedZone(
                    space_id=space.id, space_type=space.space_type, label=space.label,
                    category=space.category, occupancy_id=space.occupancy_id,
                    level_index=level_index, level_id=level.id, band_index=row,
                    x0=x0, y0=y0, x1=x1, y1=y1,
                    area_required_m2=space.area_m2, area_delivered_m2=round(footprint.area, 2),
                    area_tolerance=space.area_tolerance,
                    daylight_satisfied=space.daylight != 'required' or perimeter,
                    level_preference_satisfied=False)
                return [((0 if candidate.daylight_satisfied else 1, 0, 0, y0, x0, y1, x1), candidate)]
            bands = level_bands(
                level, lattice, region=candidate_region,
                split_y=public_circulation.split_y(level_index)
                if public_circulation else ())
            groups = _stacking_groups(bands, max_rows)
            local_cursor = {band.index: band.x0 for band in bands}
        else:
            groups = groups_by_level[slot]
            local_cursor = None
        candidates = []
        for group in groups:
            span = len(group)
            depth = sum(band.depth for band in group)
            if depth < space.min_dimension_m and span < max_rows:
                continue
            start = max(
                local_cursor[band.index] if local_cursor is not None
                else cursor[(slot, band.index)]
                for band in group)
            limit = min(band.x1 for band in group)
            remaining = limit - start
            width = max(space.area_m2 / depth, space.min_dimension_m)
            if remaining < width * tolerance:
                continue
            width = min(width, remaining)
            # Round inward, then validate the exact serialized rectangle. Checking
            # before rounding can turn boundary contact into a small overhang.
            x0 = math.ceil(start * 1000.0 - 1e-8) / 1000.0
            x1 = math.floor((start + width) * 1000.0 + 1e-8) / 1000.0
            y0 = math.ceil(group[0].y0 * 1000.0 - 1e-8) / 1000.0
            y1 = math.floor(group[-1].y1 * 1000.0 + 1e-8) / 1000.0
            if min(x1 - x0, y1 - y0) < space.min_dimension_m - PLAN_EPS_M:
                continue
            footprint = box(x0, y0, x1, y1)
            if not candidate_region.buffer(PLAN_EPS_M).covers(footprint):
                continue
            delivered = footprint.area
            perimeter = any(band.perimeter for band in group)
            candidate = AllocatedZone(
                space_id=space.id, space_type=space.space_type, label=space.label,
                category=space.category, occupancy_id=space.occupancy_id,
                level_index=level_index, level_id=level.id,
                band_index=group[0].row,
                x0=x0, y0=y0, x1=x1, y1=y1,
                area_required_m2=space.area_m2,
                area_delivered_m2=round(delivered, 2),
                area_tolerance=space.area_tolerance,
                daylight_satisfied=(space.daylight != 'required') or perimeter,
                level_preference_satisfied=False)
            score = (
                0 if candidate.daylight_satisfied else 1,
                abs(candidate.area_delivered_m2 - space.area_m2),
                span, round(y0, 6), round(x0, 6), round(y1, 6), round(x1, 6),
            )
            candidates.append((score, candidate))
        return sorted(candidates, key=lambda row: row[0])

    def try_place(
        space: SpaceRequirement, slot, tolerance: float, *, required_region=None,
        avoid=(),
    ) -> AllocatedZone | None:
        for _,candidate in placement_candidates(
                space, slot, tolerance, required_region=required_region,
                ):
            if public_circulation is None:
                return candidate
            connection = public_circulation.room_connection(candidate, avoid=avoid)
            if connection is not None:
                connections[space.id] = connection
                return candidate
        return None

    def consume(chosen: AllocatedZone, slot) -> None:
        """Give the floor a placed room stands on away, in its slot."""
        index = slot_level[slot]
        if public_circulation is not None:
            public_circulation.commit_room(chosen, connections[chosen.space_id])
            level = lattice.level(index)
            # Authored owners may share a wall: an additional full corridor around
            # every room destroys its neighbour's declared area. Actual public
            # routes retain their full-width reservation below, and room_connection
            # still routes around every occupied room with its planning body.
            occupied_rooms = unary_union([
                box(z.x0, z.y0, z.x1, z.y1).buffer(
                    0.0 if z.space_id in authored_regions else public_circulation.room_separation_m,
                    join_style='mitre')
                for z in zones if z.level_index == index])
            region = base_region(slot).difference(occupied_rooms).difference(
                public_circulation.reserved(index))
            regions_by_level[slot] = region
            bands_by_level[slot] = level_bands(level, lattice, region=region,
                                               split_y=public_circulation.split_y(index))
            groups_by_level[slot] = _stacking_groups(bands_by_level[slot], max_rows)
            for band in bands_by_level[slot]:
                cursor[(slot, band.index)] = band.x0
            capacity[slot] = sum(b.area for b in bands_by_level[slot]) * (1 - allowance)
            return
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
        for band in bands_by_level[slot]:
            if not (chosen.y0 - 0.01 <= band.y0 and band.y1 <= chosen.y1 + 0.01):
                continue
            if band.x1 <= chosen.x0 or band.x0 >= chosen.x1:
                continue
            key = (slot, band.index)
            cursor[key] = max(cursor[key], consumed)
        capacity[slot] -= chosen.area_delivered_m2

    # The given zones first: each lays its own rooms out inside its rectangle. A
    # room that does not fit is reported against the zone, with the zone's numbers,
    # and is not tried anywhere else -- the massing is the contract.
    zone_reports: list[ZoneReport] = []
    for slot, zone in zone_slots.items():
        level = lattice.level(zone.level_index)
        spaces = sorted((by_id[sid] for sid in zone.space_ids),
                        key=lambda space: (_PREFERENCE_ORDER[space.level_preference],
                                           -space.area_m2))
        asked = sum(space.area_m2 for space in spaces)
        rows_area = sum(band.area for band in bands_by_level.get(slot, []))
        placed_ids: list[str] = []
        missing_ids: list[str] = []
        delivered = 0.0
        for space in spaces:
            # The full area first; then the room's own tolerance -- a room a tenth
            # short in a zone is a short room, reported as such, not an unplaced one.
            chosen = None
            if bands_by_level.get(slot):
                chosen = (try_place(space, slot, 1.0)
                          or try_place(space, slot, space.area_tolerance))
            if chosen is None:
                missing_ids.append(space.id)
                unplaced.append(UnplacedSpace(
                    space_id=space.id, label=space.label, area_required_m2=space.area_m2,
                    reason=(f"zone '{zone.label}' on {level.id} holds "
                            f"{zone_usable[slot]:.0f} m2 of usable floor, "
                            f"{rows_area:.0f} m2 of it in whole rows once the corridors "
                            f"and the approach took theirs, against "
                            f"{asked:.0f} m2 asked by its {len(spaces)} spaces; "
                            f"{space.label} ({space.area_m2:.0f} m2 at "
                            f"{space.min_dimension_m:.1f} m) does not fit what is left")))
                continue
            chosen.level_preference_satisfied = (
                zone.level_index in _allowed_levels(space.level_preference, occupied))
            zones.append(chosen)
            placed_ids.append(space.id)
            delivered += chosen.area_delivered_m2
            consume(chosen, slot)
        zone_reports.append(ZoneReport(
            label=zone.label, level_id=level.id, rect=zone.rect,
            area_rect_m2=round(box(*zone.rect).area, 2),
            area_usable_m2=round(zone_usable[slot], 2), area_rows_m2=round(rows_area, 2),
            area_required_m2=round(asked, 2), area_delivered_m2=round(delivered, 2),
            placed=placed_ids, unplaced=missing_ids))

    # Every geometrically viable Program Volume owner gets first claim on its own
    # gross rectangle.  While its room is being connected, the other viable owners
    # on that storey are temporary route obstacles: an early shortest path may use
    # their future circulation allowance, but it may not erase the only rectangle in
    # which their full room fits.  These obstacles disappear after this pass and are
    # never serialized as reservations or GivenZones.
    owner_ready = {}
    owner_order = []
    for space in ordered:
        authored = authored_regions.get(space.id)
        if authored is None:
            continue
        level_index, owner = authored
        if not placement_candidates(
                space, level_index, 1.0, required_region=owner):
            continue
        owner_ready[space.id] = (level_index, owner)
        level = lattice.level(level_index)
        owner_floor = regions_by_level[level_index].intersection(owner)
        owner_bands = level_bands(
            level, lattice, region=owner_floor,
            split_y=public_circulation.split_y(level_index)
            if public_circulation else ())
        network_distance = (
            public_circulation.network_distance(level_index, owner)
            if public_circulation else 0.0)
        owner_order.append((
            round(network_distance, 6),
            round(sum(band.area for band in owner_bands) - space.area_m2, 6),
            level_index, round(owner.bounds[1], 6), round(owner.bounds[0], 6),
            space.id, space))

    owner_placed = set()
    pending_owners = dict(owner_ready)
    for *_key, space in sorted(owner_order):
        level_index, owner = pending_owners[space.id]
        avoid = [other_owner for other_id, (other_level, other_owner)
                 in pending_owners.items()
                 if other_id != space.id and other_level == level_index
                 and other_id not in shared_route_claims]
        chosen = try_place(
            space, level_index, 1.0, required_region=owner, avoid=avoid)
        del pending_owners[space.id]
        if chosen is None:
            continue
        chosen.level_preference_satisfied = (
            level_index in _allowed_levels(space.level_preference, occupied))
        zones.append(chosen)
        owner_placed.add(space.id)
        consume(chosen, level_index)

    # Rooms whose owner was obstructed by an archetype/core/route, plus legacy rooms
    # with no Program Volume owner, enter the measured spill pass.  Full-area PV rooms
    # remain full-area here; an honest unplaced record is preferable to silent shrinkage.
    for space in (space for space in ordered if space.id not in owner_placed):
        brief_preferred = _allowed_levels(space.level_preference, occupied)
        authored = authored_regions.get(space.id)
        authored_level = authored[0] if authored is not None else None
        preferred = (([authored_level] if authored_level in occupied else [])
                     + [index for index in brief_preferred if index != authored_level])
        fallback = [index for index in occupied if index not in preferred]
        chosen: AllocatedZone | None = None

        # first pass insists on the full area, second accepts a truncated room rather
        # than reporting a space as unplaceable when a partial fit exists
        for tolerance in ((1.0,) if public_circulation is not None else (1.0, 0.55)):
            for level_index in preferred + fallback:
                if capacity.get(level_index, 0.0) < space.area_m2 * 0.45:
                    continue
                if not bands_by_level.get(level_index):
                    continue
                candidate = try_place(
                    space, level_index, tolerance,
                    required_region=(program_floor_by_level.get(level_index)
                                     if authored_regions else None))
                if candidate is None:
                    continue
                candidate.level_preference_satisfied = level_index in brief_preferred
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
                        f'{sum(usable.values()):.0f} m2 of usable plate' +
                        (' after protecting connected public corridors and room approaches'
                         if public_circulation is not None else ''))))
            continue

        zones.append(chosen)
        consume(chosen, chosen.level_index)

    return ProgramAllocation(
        zones=zones, unplaced=unplaced, cores_unreserved=[],
        zone_reports=zone_reports,
        usable_area_by_level=usable,
        required_area_m2=round(sum(space.area_m2 for space in brief), 2),
        delivered_area_m2=round(sum(zone.area_delivered_m2 for zone in zones), 2),
        public_circulation=public_circulation.plan if public_circulation is not None else None)
