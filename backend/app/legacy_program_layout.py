"""Legacy ellipse proposals, bounded rectangular Program Volumes.

The copied legacy solver supplies free XY proposals. Exact rectangle placement
then enforces the buildable polygon and non-overlap; no room is resized to fit.
Structural grid coordinates never participate in this form-making stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import random
from typing import Literal

from pydantic import BaseModel, Field
from shapely.geometry import box, LineString, Point
from shapely.ops import unary_union, nearest_points

from backend.legacy.EllipseAgent import Agent
from .program_massing import MassingGrid
from .roof import score_roof_control
from .joint_layout import JointRoot


class LegacyRoomGroup(BaseModel):
    """An author's shared-width/depth strip decision; no authored coordinates."""
    space_ids: list[str] = Field(min_length=2)
    axis: Literal['x', 'y']
    reason: str = Field(min_length=1)


class LegacyLayoutControls(BaseModel):
    seed: int = 17
    root_proposal: JointRoot | None = None
    iterations: int = Field(default=120, ge=0, le=5000)
    flight_width_m: float = Field(default=1.2, gt=0)
    corridor_width_m: float = Field(default=1.8, gt=0)
    entry_elevation_m: float = Field(default=0.3, gt=0)
    core_inset_fraction: float = Field(default=0.18, ge=0, le=0.35)
    secondary_core_inset_fraction: float = Field(default=0., ge=0, le=0.35)
    hall_depth_position: float | None = Field(default=None, ge=0, le=1)
    backbone_layout: Literal['rear_spine', 'rear_commons', 'distributed_cores'] = 'rear_spine'
    stair_run_axis: Literal['x', 'y'] = 'y'
    layout_max_nodes: int = Field(default=64, ge=1, le=512)
    room_candidate_limit: int = Field(default=8, ge=1, le=32)
    layout_time_budget_s: float = Field(default=20.0, gt=0, le=120)
    proposal_schedule: Literal['accepted_round_robin', 'trial_round_robin'] = 'accepted_round_robin'
    lift_layout: Literal['legacy_rear', 'core_front_inner'] = 'legacy_rear'
    arrival_layout: Literal['legacy_unreserved', 'west_forecourt', 'complete_forecourt'] = 'legacy_unreserved'
    arrival_facade_allowance_m: float = Field(default=1.0, ge=0)
    foyer_layout: Literal['separate_room', 'hall_front_shared'] = 'separate_room'
    room_groups: list[LegacyRoomGroup] = Field(default_factory=list)
    note: str = 'Compact studio test assumptions; no code or accessibility approval.'


class LayoutRejected(ValueError):
    def __init__(self, findings, placed=()):
        self.findings = findings
        self.rectangles = [{'level': p.level, 'id': p.identifier, 'category': p.category,
                            'role': p.role, 'spaces': p.spaces, 'rect': list(p.shape.bounds),
                            'target_area_m2': p.target} for p in placed]
        super().__init__('; '.join(findings))


def hall_depth_for(house, stage, *, available_width, available_depth, position=None):
    """Area-preserving hall/stage proportions inside measured spatial limits.

    None retains the historical deepest-fit proposal. An explicit position selects
    within the feasible interval; the adjacent-room seam and minimum dimensions stay
    binding. Actual gallery/entrance fit is still tested by connected_options.
    """
    upper = min(available_depth, house.area_m2 / house.min_dimension_m,
                stage.area_m2 / stage.min_dimension_m)
    lower = max(house.min_dimension_m, stage.min_dimension_m,
                (house.area_m2 + stage.area_m2) / available_width)
    if upper < lower:
        raise LayoutRejected([
            'Shared auditorium/stage proportions cannot fit the spatial envelope: '
            f'required depth >= {lower:.4f} m; permitted depth <= {upper:.4f} m; '
            f'available field {available_width:.4f} x {available_depth:.4f} m; '
            f'unchanged paired area {house.area_m2 + stage.area_m2:.4f} m2'])
    return upper if position is None else lower + position * (upper - lower)


@dataclass
class Placed:
    level: int
    identifier: str
    category: str
    role: str
    spaces: list[str]
    shape: object
    target: float
    reason: str
    shared_route_volume_ids: list[str] = field(default_factory=list)


def _layout_areas(placed):
    """Whole floor and circulation unions; shared commons count only once.

    These are monotone demands during authoring. Sectional airspace never spends
    floor area, so the same measurement can prune a branch and validate its result.
    """
    floor, traffic = 0., 0.
    for level in {p.level for p in placed}:
        members = [p for p in placed if p.level == level]
        floor += unary_union([p.shape for p in members if p.role != 'sectional_clearance']).area
        traffic += unary_union([p.shape for p in members if p.category == 'circulation']).area
    return floor, traffic


def _registered_union(members):
    """Read connectivity at the same 0.1 mm precision as the emitted registry."""
    return unary_union([box(*(round(v,4) for v in p.shape.bounds)) for p in members])


def _layout_topology_findings(placed, count, core_sources):
    findings = []
    for k in range(count):
        members = [p for p in placed if p.level == k]
        walkable = [p for p in members if p.category == 'circulation'
                    and (not p.spaces or p.shared_route_volume_ids)
                    and p.identifier not in core_sources]
        if _registered_union(walkable).geom_type != 'Polygon':
            findings.append(f'L{k+1:02d} circulation is disconnected without crossing rooms')
        if _registered_union(members).geom_type != 'Polygon':
            findings.append(f'L{k+1:02d} contains disconnected volumes; circulation needs another layout')
    return findings


def _level_proposal_tiers(levels, state):
    """Give occupied storeys a program anchor before filling one storey twice.

    Uninhabited sectional-clearance storeys need an actual room/route assembly to
    join them to the cores. Offer their larger anchors first; leaving this duty
    to the final tiny service room predictably strands the whole level.
    Tiers order proposals, never remove the other permitted storeys.
    """
    owned = {p.level for p in state if p.spaces}
    clearance = {p.level for p in state if p.role == 'sectional_clearance'}
    priority = {k: (0 if k in clearance else 1) if k not in owned else 2 for k in levels}
    return [[k for k in levels if priority[k] == rank] for rank in range(3)]


def _placements(*args, **kwargs):
    """Legal free-XY rectangles in preference order, without grid snapping."""
    return (trial for trial in _placement_trials(*args, **kwargs) if trial is not None)


def _placement_trials(shape, occupied, width, depth, preferred, *, accept=None, checkpoint=None,
                      access_rects=(), access_width=0.):
    """Yield after each geometric attempt, including a rejected attempt.

    The multi-proportion scheduler must see failures: waiting for the first
    successful rectangle can exhaust one impossible shape before another shape
    receives even one attempt. ``None`` is work performed, never a placement.
    """
    minx, miny, maxx, maxy = shape.bounds
    # Candidate faces come from actual polygon vertices and already placed volumes.
    parts = [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)
    vertices = [p for part in parts for p in part.exterior.coords]
    xs = {preferred[0] - width / 2, minx, maxx - width}
    ys = {preferred[1] - depth / 2, miny, maxy - depth}
    for x, y in vertices:
        xs.update((x, x - width))
        ys.update((y, y - depth))
    for other in occupied:
        a, b, c, d = other.bounds
        xs.update((a - width, c, a, c - width))
        ys.update((b - depth, d, b, d - depth))
    def access_priority(point):
        # Attach to an existing public street before growing a new branch.
        # This only orders proposals: the full route/door/domain checks below
        # still decide whether the contact is physically usable.
        x,y = point
        return not any(
            ((abs(x+width-a)<1e-7 or abs(x-c)<1e-7)
             and min(y+depth,d)-max(y,b) >= access_width-1e-7)
            or ((abs(y+depth-b)<1e-7 or abs(y-d)<1e-7)
                and min(x+width,c)-max(x,a) >= access_width-1e-7)
            for a,b,c,d in access_rects)

    candidates = sorted(((x, y) for x in xs for y in ys
                         if minx-1e-7 <= x <= maxx-width+1e-7
                         and miny-1e-7 <= y <= maxy-depth+1e-7), key=lambda p: (
        access_priority(p) if access_rects else False,
        math.hypot(p[0] + width / 2 - preferred[0], p[1] + depth / 2 - preferred[1]), p))
    occupied_union = unary_union(occupied)
    domain = shape.buffer(1e-7)
    for x, y in candidates:
        if checkpoint is not None:
            checkpoint()
        rect = box(x, y, x + width, y + depth)
        if accept is None and (occupied and rect.boundary.intersection(occupied_union.boundary).length < 1e-6):
            yield None
            continue
        if not domain.covers(rect) or rect.intersection(occupied_union).area >= 1e-7:
            yield None
            continue
        yield rect if accept is None or accept(rect) else None


def _split_group(rect, spaces, axis):
    """Exact-area adjacent rooms sharing a cross dimension, or no valid group."""
    a,b,c,d = rect.bounds
    if len(spaces) == 1:
        return [rect] if min(c-a,d-b) >= spaces[0].min_dimension_m - 1e-7 else None
    cursor = a if axis == 'x' else b
    cross = d-b if axis == 'x' else c-a
    parts = []
    for space in spaces:
        span = space.area_m2 / cross
        if min(cross, span) < space.min_dimension_m - 1e-7:
            return None
        parts.append(box(cursor,b,cursor+span,d) if axis == 'x'
                     else box(a,cursor,c,cursor+span))
        cursor += span
    return parts


def _registered_capacity_size(width, depth):
    """Reserve complete capacity before 0.1 mm registry serialization.

    Integral registry dimensions retain their length when both endpoints are
    rounded. Nearest-rounded endpoints of an arbitrary dimension can lose area.
    Placement still checks the slightly larger rectangle against all obstacles.
    """
    scale = 10000
    return tuple(math.ceil(value * scale) / scale for value in (width, depth))


def _shared_foyer(placed, foyer, core_sources, limit, x, top, *, shape=None):
    """Reserve the brief's complete commons before the hall and service search."""
    if foyer is None or foyer.category != 'circulation':
        raise LayoutRejected(['A shared hall-front foyer requires its explicit circulation brief owner'],placed)
    if shape is None:
        depth, width = foyer.min_dimension_m, foyer.area_m2/foyer.min_dimension_m
        shape = box(x,top-depth,x+width,top)
    else:
        x0,y0,x1,y1 = shape.bounds
        width,depth = x1-x0,y1-y0
    shared = [p.identifier for p in placed if p.level == 0
              and p.role in ('circulation_spine','connector')
              and p.identifier not in core_sources and p.shape.intersection(shape).area > 1e-7]
    exclusive = [p.shape for p in placed if p.level == 0 and p.identifier not in shared]
    if (min(width,depth)<foyer.min_dimension_m or not limit.buffer(1e-7).covers(shape)
            or shape.intersection(unary_union(exclusive)).area > 1e-7 or not shared):
        raise LayoutRejected(['The whole hall-front shared foyer does not fit its declared area and core exclusions'],placed)
    if abs(shape.area-foyer.area_m2) > 1e-6:
        raise LayoutRejected(['The shared foyer must retain its whole declared area'],placed)
    return Placed(0,'PV-L01-SP-FOYER','circulation','program',[foyer.id],shape,foyer.area_m2,
        'Exact-area hall-front foyer carries named public routes; cores and other rooms remain exclusive',shared)


def _hall_galleries(pair, corridor, spine_y, left, right):
    """Companion floor is part of the hall proposal, never appended after placement."""
    x0,y0,x1,_ = pair.bounds
    result = []
    for side,gallery in (('W',box(x0-corridor,y0,x0,spine_y+corridor)),
                         ('E',box(x1,y0,x1+corridor,spine_y+corridor))):
        for suffix,shape in (('',gallery),('-RETURN',box(min(gallery.bounds[0],left),spine_y,
                max(gallery.bounds[2],right),spine_y+corridor))):
            result.append(Placed(0,f'PV-L01-GALLERY-{side}{suffix}','circulation','connector',[],shape,0,
                'Whole theater assembly: side-gallery and spine return checked before room placement'))
    return result


def _connect_room(limit, blockers, network, room, width, *, checkpoint=None,
                  terminal_points=None):
    """Reserve full-width orthogonal floor from a room face to authored circulation.

    Unclaimed parcel area may become an explicit connector, never an implicit route
    through another room, a stair shaft or upper sectional airspace.
    """
    from .navigation import orthogonal_route, polygons
    # Reuse an existing full-width landing before growing connector floor. At
    # an exactly corridor-wide gap, subtracting two inflated solids erases its
    # zero-width centre-line even though the complete physical landing fits.
    # Measure that landing directly; a short face or obstructed landing fails.
    floor = unary_union(network)
    occupied = unary_union(blockers)
    radius = width / 2
    landings = ([box(x-radius,y-radius,x+radius,y+radius) for x,y in terminal_points]
                if terminal_points is not None else [])
    shared = room.boundary.intersection(floor.boundary)
    edges = ([] if terminal_points is not None else
             list(shared.geoms) if hasattr(shared,'geoms') else [shared])
    x0,y0,x1,y1 = room.bounds
    for edge in edges:
        if edge.geom_type != 'LineString' or edge.length < width-1e-7:
            continue
        x,y = edge.interpolate(.5,normalized=True).coords[0]
        if abs(y-y0)<1e-7:
            landing = box(x-width/2,y-width,x+width/2,y)
        elif abs(y-y1)<1e-7:
            landing = box(x-width/2,y,x+width/2,y+width)
        elif abs(x-x0)<1e-7:
            landing = box(x-width,y-width/2,x,y+width/2)
        elif abs(x-x1)<1e-7:
            landing = box(x,y-width/2,x+width,y+width/2)
        else:
            continue
        landings.append(landing)
    for landing in landings:
        if (floor.buffer(1e-7).covers(landing) and limit.buffer(1e-7).covers(landing)
                and landing.intersection(occupied.union(room)).area < 1e-7):
            return []
    domain = limit.buffer(-radius, join_style=2).difference(
        unary_union([*blockers, room]).buffer(radius, join_style=2))
    domain = domain.buffer(1e-7)
    corners = [point for part in polygons(domain)
               for ring in [part.exterior,*part.interiors] for point in ring.coords]
    x0, y0, x1, y1 = room.bounds
    starts = list(terminal_points) if terminal_points is not None else []
    for lo, hi, fixed, horizontal in ((x0,x1,y0-radius,True),(x0,x1,y1+radius,True),
                                     (y0,y1,x0-radius,False),(y0,y1,x1+radius,False)):
        if terminal_points is None and hi-lo >= width-1e-7:
            starts.extend((p,fixed) if horizontal else (fixed,p)
                          for p in ((lo+hi)/2, lo+radius, hi-radius))
    axes = []
    for region in network:
        a,b,c,d = region.bounds
        if c-a >= d-b:
            axes.append(LineString([(a+radius,(b+d)/2),(c-radius,(b+d)/2)]))
        else:
            axes.append(LineString([((a+c)/2,b+radius),((a+c)/2,d-radius)]))
    proposals = [(start, tuple(nearest_points(Point(start),axis)[1].coords[0]))
                 for start in starts if domain.covers(Point(start)) for axis in axes]
    points = None
    # First feasible route in near-to-far order: a bounded design proposal, not
    # a globally shortest-path claim or an exhaustive corridor optimisation.
    for start, target in sorted(proposals, key=lambda pair: math.dist(*pair)):
        if checkpoint is not None:
            checkpoint()
        if not domain.covers(Point(target)):
            continue
        points = orthogonal_route(domain, start, target, corners=corners,
                                  orthogonal_only=True)
        if points is not None:
            break
    if points is None:
        return None
    pairs = list(zip(points,points[1:])) or [(points[0],points[0])]
    return [box(min(a[0],b[0])-radius, min(a[1],b[1])-radius,
                max(a[0],b[0])+radius, max(a[1],b[1])+radius) for a,b in pairs]


def organize_legacy_volumes(score, brief, datums, *, controls=None):
    from .compiler_v3 import _core_box, LIFT_SHAFT_M, CORE_CLEARANCE_M
    from .datums import flight_run
    from .program_volumes import (ProgramVolumeModel, ProgramVolume, ProgramVolumeLevel,
        ProgramVolumeUnion, _polygon_rings, _program_volume_regions, _circulation_intent_for)
    controls = controls or LegacyLayoutControls()
    distributed = controls.backbone_layout == 'distributed_cores'
    rear_commons = controls.backbone_layout in ('rear_commons','distributed_cores')
    horizontal_cores = controls.stair_run_axis == 'x'
    if distributed and not horizontal_cores:
        raise LayoutRejected(['Distributed composition uses an X primary stair and Y side stair'])
    if horizontal_cores and not rear_commons:
        raise LayoutRejected(['Horizontal cores require the joint rear-commons layout'])
    if rear_commons and (controls.lift_layout != 'core_front_inner'
                        or controls.arrival_layout != 'complete_forecourt'
                        or controls.foyer_layout != 'hall_front_shared'):
        raise LayoutRejected(['Rear commons requires the complete arrival and shared foyer assembly'])
    limit = brief.massing_limit_shape
    if limit.geom_type != 'Polygon':
        raise LayoutRejected(['Disconnected buildable parcels require an explicit building-cluster choice'])
    spaces = list(brief.resolved_spaces())
    theater = brief.typology == 'theater'
    if brief.typology not in ('theater', 'library'):
        raise LayoutRejected(['Bounded adapter has no sectional program adapter for '+brief.typology])
    by_id = {s.id: s for s in spaces}
    if theater and not {'SP-AUDITORIUM', 'SP-STAGE'} <= by_id.keys():
        raise LayoutRejected(['Theater requires auditorium and stage program owners'])
    if not theater:
        if 'SP-ADULT' not in by_id or brief.occupied_storeys < 2:
            raise LayoutRejected(['Library requires an adult-reading owner and its upper clearance storey'])
        if controls.root_proposal is not None or controls.foyer_layout == 'hall_front_shared':
            raise LayoutRejected(['Theater root/shared-foyer controls cannot author a library'])
    minx, miny, maxx, maxy = limit.bounds
    root = controls.root_proposal
    secondary_axis = root.secondary_run_axis if root is not None else 'y'
    if root is not None and not distributed:
        raise LayoutRejected(['Joint root requires the distributed-core adapter'])
    core = box(*_core_box(0,0,controls.flight_width_m,flight_run(controls.flight_width_m),
                         run_axis=controls.stair_run_axis))
    cw, cd = core.bounds[2] - core.bounds[0], core.bounds[3] - core.bounds[1]
    corridor = controls.corridor_width_m
    inset = (maxx-minx) * controls.core_inset_fraction
    left, right = minx+inset, maxx-inset
    if root is not None:
        left = root.primary_left
        maxy = root.primary_top
    if horizontal_cores:
        right = maxx
    spine_y = maxy - cd - corridor
    lift_width = LIFT_SHAFT_M + 2 * CORE_CLEARANCE_M
    from .approach import ENTRANCE_MIN_WIDTH_M
    from .partitions import PARTITION_TYPES
    wall = max(p.thickness_mm for p in PARTITION_TYPES) / 1000.0
    # The compiler protects a wall thickness beyond entry landings. Reserve that
    # same allowance before placing rooms beside the arrival carrier.
    arrival_width = max(corridor, ENTRANCE_MIN_WIDTH_M) + 2 * wall
    backbone = [box(left, maxy - cd, left + cw, maxy),
                box(right - cw, maxy - cd, right, maxy),
                box(left, spine_y, right, spine_y + corridor),
                # Shaft and landing form one spatial assembly alongside the core.
                # The old remote shaft touched the stair's back wall but supplied
                # no walking floor between its door and the public spine.
                (box(left+cw, spine_y+corridor,
                     left+cw+lift_width, spine_y+corridor+lift_width)
                 if controls.lift_layout == 'core_front_inner' else
                 box(left-lift_width, maxy-lift_width, left, maxy)),
                box(left-arrival_width, spine_y+corridor-arrival_width,
                    left, spine_y+corridor)]
    if controls.lift_layout == 'core_front_inner':
        backbone.append(box(left+cw, spine_y, left+cw+lift_width, spine_y+corridor))
    if horizontal_cores:
        # Horizontal flights need access at their inner end faces. A shared rear
        # gallery links those faces to the cross-spine; the lift takes the remaining
        # arrival-side field instead of blocking the space between the two stairs.
        if left-minx < lift_width or right-left-2*cw < 2*corridor:
            raise LayoutRejected(['Horizontal core pair, lift and end galleries cannot fit this field'])
        # The shared route ends at the inner stair landing gallery. Extending
        # it to the outer core face replicated an unused tail on every storey.
        # Rooms beyond this terminal must author their own measured connection.
        backbone[2] = box(minx,spine_y,right-cw,spine_y+corridor)
        backbone[3] = box(minx,spine_y+corridor,minx+lift_width,spine_y+corridor+lift_width)
        backbone[5] = box(minx,spine_y,minx+lift_width,spine_y+corridor)
        backbone.extend([box(left+cw,spine_y+corridor,left+cw+corridor,maxy),
                         box(right-cw-corridor,spine_y+corridor,right-cw,maxy)])
    if distributed:
        # Rotate the same complete stair reservation, not its flight alone. The
        # second access terminal now faces south along the east parcel field.
        # Its side gallery meets that end and the existing primary-core street.
        side_right = maxx-(maxx-minx)*controls.secondary_core_inset_fraction
        side_x, side_y = side_right-cd, maxy-cw
        if root is not None:
            side_right,side_y = root.secondary_right,root.secondary_bottom
            side_x = side_right-cd
        if secondary_axis == 'x':
            side_x = side_right-cw
        backbone[1] = box(side_x,side_y,side_right,side_y+(cd if secondary_axis=='x' else cw))
        backbone[2] = box(minx,spine_y,side_x,spine_y+corridor)
        if secondary_axis == 'x':
            backbone[7] = box(side_x-corridor,spine_y,side_x,side_y+cd)
        else:
            backbone[7] = box(side_x-corridor,side_y-corridor,side_x,spine_y+corridor)
            backbone.append(box(side_x-corridor,side_y-corridor,side_right,side_y))
    if root is not None:
        from .core_access import lift_approach_bounds
        from .portals import APPROACH_WIDTH_M, APPROACH_DEPTH_M
        from .compiler_v3 import LIFT_DOOR_W_M
        # Keep the shaft adjacent to the translated primary core. Moving only
        # the entry would consume the forecourt depth the ramp actually needs.
        _,b,_,d = backbone[3].bounds
        backbone[3] = box(left-lift_width,b,left,d)
        shaft = backbone[3]
        # Author the same complete door approach the emitted portal will check.
        # This is occupied circulation floor, not an opening cut out of the slab.
        backbone.append(box(*lift_approach_bounds(shaft.centroid.x,shaft.centroid.y,
            LIFT_SHAFT_M,'south',max(LIFT_DOOR_W_M,APPROACH_WIDTH_M),APPROACH_DEPTH_M)))
    arrival = None
    approach_reservation = None
    if controls.arrival_layout in ('west_forecourt','complete_forecourt'):
        from .approach import plan_compact_arrival, PUBLIC_STAIR_TREAD_M, entry_landing_rect
        from .envelope import ENTRANCE_REVEAL_DEPTH_M
        # Full facade frontage and public-route depth are different requirements.
        # Keep the entrance on its foyer connection. The older clear-width
        # study remains replayable; complete frontage is an explicit layout choice.
        if controls.arrival_layout == 'complete_forecourt':
            frontage = max(arrival_width,ENTRANCE_MIN_WIDTH_M+2*(ENTRANCE_REVEAL_DEPTH_M+
                           controls.arrival_facade_allowance_m))
            depth = max(corridor,-entry_landing_rect(controls.flight_width_m)[1]+wall)
            if root is not None:
                depth = max(depth,lift_width/2+APPROACH_WIDTH_M/2)
        else:
            frontage = depth = arrival_width
        entry_x = left-depth if rear_commons else left
        # The horizontal-core cross-spine extends west of the entry. Its lower
        # face bounds the exposed portal frontage; spending that spine depth a
        # second time hid part of the doorway behind the building's own return.
        entry_top = spine_y if horizontal_cores else spine_y+corridor
        if root is not None:
            entry_top = root.arrival_top
            # The joint threshold meets the lift's lower face. The public
            # street/landing share its exterior datum so neither buries its door.
            for i in (2,5):
                _,b,c,d = backbone[i].bounds
                backbone[i] = box(entry_x,b,c,d)
        backbone[4] = box(entry_x,entry_top-frontage,entry_x+depth,entry_top)
        if rear_commons and not horizontal_cores:
            # This complete landing gallery joins the source spine at its west face.
            # Moving it outside the hall's field changes the whole composition;
            # parcel and facade-frontage checks still decide whether it can stand.
            backbone.append(box(entry_x,spine_y,left,spine_y+corridor))
        # A detached west frontage owns its station; the former foyer datum sat
        # too close to its top corner to contain the complete facade portal.
        station_frontage = frontage if rear_commons else arrival_width
        arrival_origin = (entry_x,entry_top-station_frontage/2)
        arrival = plan_compact_arrival(parcel=brief.site.shape,
            origin=arrival_origin,tangent=(0.,-1.),outward=(-1.,0.),
            rise_m=controls.entry_elevation_m,flight_width_m=controls.flight_width_m,
            riser_m=datums.value('riser_m'),tread_m=PUBLIC_STAIR_TREAD_M,
            weather_reach_m=controls.arrival_facade_allowance_m,
            protected=unary_union(backbone).difference(backbone[4]),
            landing_clearance_m=wall)
        if arrival is None:
            raise LayoutRejected(['The whole arrival assembly does not fit this forecourt; '
                                  'revise the backbone before placing rooms'])
        approach_reservation = arrival.reserved_footprint(
            arrival_origin,(0.,-1.),(-1.,0.),landing_clearance_m=wall).difference(backbone[4])
        # Exterior walking floor has its own ownership. It cannot be spent again
        # on room volumes or on a connector inserted by the room search.
    if not all(limit.buffer(1e-7).covers(s) for s in backbone):
        raise LayoutRejected(['The proposed circulation backbone does not fit the actual buildable polygon'])
    if any(backbone[a].intersection(backbone[c]).area > 1e-7
           for a,c in ((0,1),(0,3),(1,3))):
        raise LayoutRejected(['Stair and lift reservations overlap; revise the whole circulation backbone'])
    count = brief.occupied_storeys
    placed = [Placed(k, f'PV-L{k+1:02d}-CIRC-{i}', 'circulation',
                     'circulation_spine', [], s, 0,
                     'Lift landing connected directly to the public spine before rooms are placed'
                     if i == 5 else 'Test core / lift / connecting spine reservation')
              for k in range(count) for i, s in enumerate(backbone) if k == 0 or i != 4]
    core_sources = {f'PV-L{k+1:02d}-CIRC-{i}' for k in range(count) for i in (0,1,3)}
    if controls.foyer_layout == 'hall_front_shared':
        foyer_shape = None
        if distributed or (rear_commons and not horizontal_cores):
            foyer = by_id['SP-FOYER']
            x0,x1 = ((left+cw,side_x-corridor) if distributed else
                     (left+cw+lift_width,right-cw))
            if distributed:
                x1 = min(x1,x0+foyer.area_m2/foyer.min_dimension_m)
            rear_pocket = root is not None and root.foyer_placement == 'between_cores'
            if rear_pocket:
                x1 = min(side_x,x0+foyer.area_m2/foyer.min_dimension_m)
            if x1-x0 < foyer.min_dimension_m:
                raise LayoutRejected(['The rear commons cannot fit between the lift and second core'],placed)
            depth = foyer.area_m2/(x1-x0)
            foyer_shape = (box(x0,spine_y+corridor-depth,x1,spine_y+corridor) if distributed
                           else box(x0,spine_y,x1,spine_y+depth))
            if rear_pocket:
                # A whole-area alternative assembly, sharing the primary end
                # gallery instead of projecting the foyer into the hall field.
                foyer_shape = box(x0,maxy-depth,x1,maxy)
        placed.append(_shared_foyer(placed,by_id.get('SP-FOYER'),core_sources,
                                  limit,left+cw,spine_y+corridor,shape=foyer_shape))
    # A shared foyer owns some existing public floor. Count the actual union,
    # not its whole area a second time. Later batches and the final layout use
    # this same measurement as additional circulation is authored.
    _,traffic = _layout_areas(placed)
    if traffic > brief.circulation_area_m2 + 1e-6:
        raise LayoutRejected([f'Circulation union needs {traffic:.3f} m2; '
                              f'brief reserves {brief.circulation_area_m2:.3f}'],placed)
    deadline = None

    def checkpoint():
        if deadline is not None:
            deadline.check()

    def connected_options(state, k, choices, preferred, *, pair_split=None, minimum=None,
                          group=None, group_axis=None, companions=None, pinned_rect=None):
        members = [p for p in state if p.level == k]
        network = [p.shape for p in members if p.category == 'circulation'
                   and (not p.spaces or p.shared_route_volume_ids)
                   and p.identifier not in core_sources]
        blocked = [p.shape for p in members if p.shape not in network]
        if pair_split is not None and distributed:
            # Hall access must reach the recurring circulation, not terminate on
            # the ground-only arrival carrier. That public carrier may still
            # share connector floor; it does not become a protected solid.
            network = [p.shape for p in members if p.shape in network
                       and p.identifier != 'PV-L01-CIRC-4']
        domain = limit.difference(approach_reservation) if k == 0 and arrival else limit
        existing = unary_union([p.shape for p in members])
        separated_clearance = (any(p.role == 'sectional_clearance' for p in members)
                               and existing.buffer(1e-7).geom_type != 'Polygon')
        links = []
        companion_parts = []

        def connect(rect):
            nonlocal links, companion_parts
            a,b,c,d = rect.bounds
            parts = (_split_group(rect, group, group_axis) if group else
                     [box(a,b,a+pair_split/(d-b),d), box(a+pair_split/(d-b),b,c,d)]
                     if pair_split is not None else [rect])
            if parts is None:
                return False
            links = []
            companion_parts = companions(rect) if companions is not None else []
            if companion_parts is None:
                return False
            companion_shapes = [p.shape for p in companion_parts]
            if any(not domain.buffer(1e-7).covers(s) or
                   s.intersection(unary_union(blocked)).area > 1e-7 for s in companion_shapes):
                return False
            for index, part in enumerate(parts):
                terminals = None
                if pair_split is not None and distributed:
                    from .room_access import owner_terminal_points, front_cross_aisle_bounds
                    from .archetypes import derive_bowl
                    from .room_fixtures import AISLE_WIDTH_M
                    front_x = None
                    if index == 0:
                        hx0,_,hx1,_ = part.bounds
                        rows = derive_bowl(hx1-hx0)
                        first_x = hx1-rows[0].offset_front_m if rows else hx1
                        lo,hi = front_cross_aisle_bounds(first_x,-1,AISLE_WIDTH_M)
                        front_x = (lo+hi)/2
                    # Author the same owner-derived positions the compiler reads.
                    # Corridor floor touches the owner; the compiler applies its
                    # tiny outside-boundary probe clearance separately.
                    terminals = owner_terminal_points(part.bounds,corridor/2,
                        front_x=front_x,boundary_clearance_m=0.)
                path = _connect_room(domain, [*blocked, *parts[:index], *parts[index+1:]],
                    [*network, *companion_shapes, *links], part, corridor,
                    checkpoint=checkpoint,terminal_points=terminals)
                if path is None:
                    return False
                links.extend(path)
            if k == 0 and controls.arrival_layout == 'complete_forecourt':
                # Entrance capacity belongs to the complete level boundary.
                # A legal neighbouring room may still shorten that face after
                # offsetting; preserve the shared aperture plus its jambs now.
                from .envelope import entrance_frontage_interval
                from .geometry import v2
                joined = unary_union([existing,*parts,*links,*companion_shapes]).simplify(0)
                if (joined.geom_type != 'Polygon'
                        or joined.boundary.distance(Point(arrival_origin)) > 1e-7):
                    return False
                for offset in (0.,controls.arrival_facade_allowance_m):
                    # Remove sub-micron seams before reading a physical frontage;
                    # registration later quantizes these same coordinates to 0.1 mm.
                    ring = (joined.buffer(offset,join_style=2) if offset else joined).simplify(1e-7)
                    if ring.geom_type != 'Polygon' or entrance_frontage_interval(
                            [v2(x,y) for x,y in list(ring.exterior.coords)[:-1]],
                            arrival_origin,(0.,-1.),ENTRANCE_MIN_WIDTH_M,
                            ENTRANCE_REVEAL_DEPTH_M) is None:
                        return False
            if separated_clearance:
                # The first upper-floor room must join the tall-room envelope
                # to the shared backbone. Testing this only after all rooms were
                # settled accepted locally connected paths but a detached building.
                joined = unary_union([existing,*parts,*links])
                if joined.buffer(1e-7).geom_type != 'Polygon':
                    return False
            return True

        if minimum is not None:
            # Existing spatial faces supply additional area-preserving proportions.
            # A 3.9 m side strip must not reject a room just because the initial
            # ellipse proposed 3.5 m or 4.2 m. Structural grid lines play no role.
            area = choices[0][0] * choices[0][1]
            for axis in (0,1):
                faces = sorted({round(limit.bounds[axis],4),round(limit.bounds[axis+2],4),
                                *(round(v,4) for p in members for v in
                                  (p.shape.bounds[axis],p.shape.bounds[axis+2]))})
                spans = {round(b-a,4) for i,a in enumerate(faces) for b in faces[i+1:]
                         if minimum <= b-a <= area/minimum}
                choices += sorted(((span,area/span) if axis == 0 else (area/span,span)
                                   for span in spans),
                                  key=lambda size: abs(size[0]-choices[0][0]))
        preferred_ratio = math.log(choices[0][0] / choices[0][1])
        # Judge all geometry-derived proportions against the original musical
        # proposal. Trying a 90-degree flip before any fitted width stranded a
        # small service room below an unnecessarily deep neighbour.
        ranked = sorted(dict.fromkeys(choices), key=lambda size:
                        abs(math.log(size[0]/size[1])-preferred_ratio))
        if pinned_rect is not None:
            a,b,c,d = pinned_rect
            ranked = [(c-a,d-b)]
        # Interleave proportions before exhausting positions of one proportion.
        # Each yielded choice owns its routes so backtracking removes both.
        # Scheduling changes design outcomes, so old briefs retain their order.
        # The fair trial schedule is an explicit candidate choice until broader
        # evidence supports changing the default.
        placement_stream = (_placement_trials if rear_commons or controls.proposal_schedule == 'trial_round_robin'
                            else _placements)
        def placements(width,depth):
            if group is not None and len(group) == 1:
                width,depth = _registered_capacity_size(width,depth)
            if pinned_rect is not None:
                rect = box(*pinned_rect)
                checkpoint()
                valid = (domain.buffer(1e-7).covers(rect)
                         and rect.intersection(existing).area < 1e-7 and connect(rect))
                yield rect if valid else None
                return
            yield from placement_stream(domain,[p.shape for p in members],
                width,depth,preferred,accept=connect,
                checkpoint=checkpoint,
                access_rects=[s.bounds for s in network] if rear_commons else (),access_width=corridor)
        streams = [placements(width,depth) for width,depth in ranked]
        from .layout_search import interleave_trials
        for shape in interleave_trials(streams):
            if shape is not None:
                additions = [Placed(k, f'PV-L{k+1:02d}-LINK-{len(state)+i}',
                    'circulation', 'connector', [], link, 0,
                    'Full-width route from an authored room face to the circulation spine')
                    for i, link in enumerate(links)]
                yield shape, [*companion_parts,*additions]
            elif rear_commons:
                yield None
    # Keep the dominant assembly in the same transaction as the smaller rooms.
    # Compatibility layouts retain their historical first-fit hall.
    if theater:
        house, stage = by_id['SP-AUDITORIUM'], by_id['SP-STAGE']
        depth = hall_depth_for(house, stage, available_width=maxx-minx,
                           available_depth=spine_y-miny, position=controls.hall_depth_position)
        width = (house.area_m2 + stage.area_m2) / depth
    from .archetypes import theatre_clearance_height

    def hall_proposals(state):
        sizes = [(width,depth)]
        preferred = (minx+.58*(maxx-minx),miny+depth/2)
        if root is not None:
            a,b,c,d = root.hall_bounds
            sizes = [(c-a,d-b)]
            preferred = ((a+c)/2,(b+d)/2)
        elif rear_commons:
            # Compatibility galleries spend width; localized room connections
            # are measured per proposal and impose no fixed two-strip envelope.
            for position in (0., .5, 1.):
                d = hall_depth_for(house,stage,available_width=maxx-minx-(0 if distributed else 2*corridor),
                                   available_depth=spine_y-miny,position=position)
                sizes.append(((house.area_m2+stage.area_m2)/d,d))
        def companions(pair):
            return _hall_galleries(pair,corridor,spine_y,
                backbone[2].bounds[0],backbone[2].bounds[2])
        options = connected_options(state,0,sizes,
            preferred,pair_split=house.area_m2,
            companions=None if distributed else companions,
            pinned_rect=root.hall_bounds if root is not None and root.hall_placement=='exact' else None)
        for option in bounded_options(options):
            if option is None:
                yield None
                continue
            pair,links = option
            x0,y0,x1,y1 = pair.bounds
            seam = x0+house.area_m2/(y1-y0)
            batch = list(links)
            for space,shape in ((house,box(x0,y0,seam,y1)),(stage,box(seam,y0,x1,y1))):
                batch.append(Placed(0,f'PV-L01-{space.id}',space.category,'archetype',
                    [space.id],shape,space.area_m2,'Exact-area theater pair with shared seam'))
            clear_height = theatre_clearance_height(seam-x0)
            for k in range(1,count):
                if k*datums.value('floor_to_floor_m') < clear_height:
                    batch.append(Placed(k,f'PV-L{k+1:02d}-HALL-CLEARANCE','public',
                        'sectional_clearance',[],pair,0,
                        f'Shared theater sectional claim: {clear_height:g} m including floor build-up'))
            yield batch

    def bounded_options(options):
        count = 0
        for option in options:
            yield option
            if option is not None:
                count += 1
                if count >= controls.room_candidate_limit:
                    return

    if theater and not rear_commons:
        first = next(hall_proposals(placed),None)
        if first is None:
            raise LayoutRejected(['The auditorium/stage pair does not fit the buildable polygon'])
        placed.extend(first)
    preassigned = {house.id,stage.id} if theater else set()
    if controls.foyer_layout == 'hall_front_shared':
        preassigned.add('SP-FOYER')
    assigned = [[] for _ in range(count)]
    loads = [sum(p.shape.area for p in placed if p.level == k) for k in range(count)]
    for space in sorted((s for s in spaces if s.id not in preassigned),
                        key=lambda s: (s.level_preference != 'ground', -s.area_m2, s.id)):
        allowed = ([0] if space.level_preference == 'ground' else
                   list(range(1, count)) if space.level_preference in ('low','high') and count>1
                   else list(range(count)))
        level = min(allowed, key=lambda k: (loads[k], -k if space.level_preference=='high' else k))
        assigned[level].append(space)
        loads[level] += space.area_m2
    variation = next((d.value for d in score.dimensions if d.id == 'variation'), .5)
    rng = random.Random(controls.seed)
    agents = [[] for _ in range(count)]
    dimensions = {}
    for k, group in enumerate(assigned):
        for space in group:
            ratio = 1 + variation * (1 if k % 2 == 0 else -.45)
            w = min(space.area_m2 / space.min_dimension_m,
                    max(space.min_dimension_m, math.sqrt(space.area_m2 * ratio)))
            h = space.area_m2 / w
            dimensions[space.id] = (w,h)
            agent = Agent(rng.uniform(minx,maxx), rng.uniform(miny,maxy), k,
                          space.area_m2,w,h,space.id,space.category,list(limit.exterior.coords))
            agent.adjacents = list(space.adjacency)
            agents[k].append(agent)
    for _ in range(controls.iterations):
        for floor in agents:
            for agent in floor:
                agent.update(agents)
    from .layout_search import search_layout, SearchDeadline, interleave_trials

    def proposals(item, state):
        k, group, preferred, group_axis, reason = item
        if group_axis == 'hall':
            yield from hall_proposals(state)
            return
        area = sum(space.area_m2 for space in group)
        minimum = max(space.min_dimension_m for space in group)
        w,h = dimensions[group[0].id]
        if group_axis == 'y':
            h = area / w
        elif group_axis == 'x':
            w = area / h
        side = math.sqrt(area)
        choices = [(w,h),(h,w)]
        if side >= minimum:
            choices.append((side,side))
        space = group[0]  # Group members must share a level preference.
        allowed = ([count-2] if not theater and space.id == 'SP-ADULT' else
                   [0] if space.level_preference == 'ground' else
                   list(range(1,count)) if space.level_preference in ('low','high') and count>1
                   else list(range(count)))
        preferred_level = k if k in allowed else allowed[0]
        levels = [preferred_level, *sorted((level for level in allowed if level != preferred_level),
                    key=lambda level: sum(p.shape.area for p in state if p.level == level))]
        def on_level(level):
            options = connected_options(state, level, list(choices), preferred,
                                        minimum=minimum, group=group, group_axis=group_axis or 'x')
            for option in bounded_options(options):
                if option is None:
                    yield None
                    continue
                shape,links = option
                parts = _split_group(shape, group, group_axis or 'x')
                batch = [*links, *(Placed(level,f'PV-L{level+1:02d}-{s.id}',s.category,
                       'archetype' if not theater and s.id == 'SP-ADULT' else 'program',
                       [s.id],part,s.area_m2,reason) for s,part in zip(group,parts))]
                if not theater and space.id == 'SP-ADULT':
                    # Reserve the reading room's upper airspace in the same search
                    # transaction. It cannot consume an existing room or core.
                    if any(p.level == level+1 and p.shape.intersection(shape).area > 1e-7
                           for p in state):
                        continue
                    batch.append(Placed(level+1,f'PV-L{level+2:02d}-READING-CLEARANCE',
                        'public','sectional_clearance',[],shape,0,
                        'Double-height airspace above the adult-reading owner; no allocatable floor'))
                yield batch

        if rear_commons:
            # Storey assignment and its access floor are one spatial choice.
            # A provisional ellipse storey cannot spend all nodes before another
            # permitted storey gets to offer an existing shared route.
            for tier in _level_proposal_tiers(levels,state):
                yield from interleave_trials(on_level(level) for level in tier)
        else:
            for level in levels:
                yield from on_level(level)

    source_items = {space.id:(k,space,agent) for k,group in enumerate(assigned)
                    for space,agent in zip(group,agents[k])}
    grouped = {}
    for rule in controls.room_groups:
        if not theater and 'SP-ADULT' in rule.space_ids:
            raise LayoutRejected(['The double-height reading owner must remain an independent room'], placed)
        if len(set(rule.space_ids)) != len(rule.space_ids) or any(
                identifier not in source_items or identifier in grouped for identifier in rule.space_ids):
            raise LayoutRejected(['Room groups require unique, known non-archetype owners'], placed)
        members = [source_items[identifier][1] for identifier in rule.space_ids]
        if len({s.level_preference for s in members}) != 1:
            raise LayoutRejected(['Grouped rooms require a shared level preference'], placed)
        for identifier in rule.space_ids:
            grouped[identifier] = rule
    items, consumed = [], set()
    for identifier, (k,space,agent) in source_items.items():
        if identifier in consumed:
            continue
        rule = grouped.get(identifier)
        ids = rule.space_ids if rule else [identifier]
        consumed.update(ids)
        members = [source_items[key][1] for key in ids]
        preferred = tuple(sum(source_items[key][2].pos[axis] for key in ids)/len(ids) for axis in (0,1))
        items.append((k, members, preferred, rule.axis if rule else None,
                      'Authored room group: '+rule.reason if rule else
                      'Bounded coordinated search from legacy ellipse XY proposals; unchanged room area'))
    # A grouped strip is one spatial decision and must be ranked by its complete
    # area. Keeping its first member's old position let a 22 m2 foyer consume the
    # only pocket for a 28 m2 service group represented by a 16 m2 member.
    items.sort(key=lambda item: ((item[1][0].level_preference != 'ground') if rear_commons else item[0],
                                 -sum(space.area_m2 for space in item[1]),
                                 tuple(space.id for space in item[1])))
    if theater and rear_commons:
        items.insert(0,(0,[house,stage],None,'hall','Joint dominant spatial assembly'))
    elif not theater:
        items.sort(key=lambda item: item[1][0].id != 'SP-ADULT')
    budget_rejections = 0
    topology_rejections = 0
    required_ids = {s.id for s in spaces}

    def accept_layout_batch(state):
        nonlocal budget_rejections, topology_rejections
        floor, traffic = _layout_areas(state)
        fits = (floor <= brief.target_gross_area_m2 + 1e-6
                and traffic <= brief.circulation_area_m2 + 1e-6)
        budget_rejections += not fits
        if fits and rear_commons:
            owners = {identifier for p in state for identifier in p.spaces}
            empty_levels = set(range(count)) - {p.level for p in state if p.spaces}
            remaining = required_ids - owners
            # Keep enough room owners to inhabit every declared occupied level.
            # A complete branch must also retain the hall's connected envelope;
            # cheap rooms elsewhere cannot leave a detached clearance storey.
            fits = (len(empty_levels) <= len(remaining)
                    and (bool(remaining) or not _layout_topology_findings(state,count,core_sources)))
            topology_rejections += not fits
        return fits

    deadline = SearchDeadline(controls.layout_time_budget_s)
    search = search_layout(items, placed, proposals, max_nodes=controls.layout_max_nodes,
                           checkpoint=checkpoint,fair_roots=rear_commons,accept=accept_layout_batch)
    placed = search.placed
    if not search.complete:
        findings = [f'{space.id} unresolved at unchanged {space.area_m2:g} m2 (preferred L{k+1:02d})'
                    for k,group,*_ in search.unplaced for space in group]
        findings.append(f'Bounded layout search: {search.nodes}/{controls.layout_max_nodes} nodes; '
                        f'budget exhausted={search.exhausted}; no parcel-infeasibility claim')
        if budget_rejections:
            findings.append(f'{budget_rejections} room/route batches rejected by unchanged floor/circulation budgets')
        if topology_rejections:
            findings.append(f'{topology_rejections} batches rejected by occupied-level or connected-volume requirements')
        if search.timed_out:
            findings.append(f'Layout time budget {controls.layout_time_budget_s:g} s reached; '
                            'partial proposal retained; whole-floor coordination needs revision')
        raise LayoutRejected(findings, placed)
    if arrival is not None:
        conflicts = [p.identifier for p in placed if p.level == 0
                     and p.shape.intersection(approach_reservation).area > 1e-7]
        if conflicts:
            raise LayoutRejected(['Arrival reservation was consumed by '+', '.join(conflicts)],placed)
    floor_area, traffic = _layout_areas(placed)
    if traffic > brief.circulation_area_m2 + 1e-6:
        raise LayoutRejected([f'Authored circulation uses {traffic:.3f} m2 including foyer; '
                              f'brief reserves {brief.circulation_area_m2:.3f}'], placed)
    topology_findings = _layout_topology_findings(placed,count,core_sources)
    if topology_findings:
        raise LayoutRejected(topology_findings,placed)
    # The shared ring contract uses 0.1 mm precision; the registry must use the
    # same precision or its own boundary stations cease to have a grid index.
    xs=sorted({round(v,4) for p in placed for v in (p.shape.bounds[0],p.shape.bounds[2])})
    ys=sorted({round(v,4) for p in placed for v in (p.shape.bounds[1],p.shape.bounds[3])})
    grid=MassingGrid(x_lines=xs,y_lines=ys,band_lines=ys)
    ftf=datums.value('floor_to_floor_m')
    levels=[ProgramVolumeLevel(index=k+1,id=f'L{k+1:02d}',
            z_base=controls.entry_elevation_m+k*ftf,z_top=controls.entry_elevation_m+(k+1)*ftf)
            for k in range(count)]
    volumes=[]
    for p in placed:
        a,b,c,d=(round(v,4) for v in p.shape.bounds)
        if p.shared_route_volume_ids:
            # Room branches may join the already declared commons during search.
            # Freeze those final route identities with the owner, after backtracking,
            # so downstream allocation reads every legitimate shared-floor claim.
            p.shared_route_volume_ids = [route.identifier for route in placed
                if route.level == p.level and route.role in ('circulation_spine','connector')
                and route.identifier not in core_sources
                and route.shape.intersection(p.shape).area > 1e-7]
        volumes.append(ProgramVolume(id=p.identifier,level_index=p.level+1,
            level_id=levels[p.level].id,category=p.category,role=p.role,space_ids=p.spaces,
            grid_rect=(xs.index(a),ys.index(b),xs.index(c),ys.index(d)),
            shared_route_volume_ids=p.shared_route_volume_ids,
            target_area_m2=p.target,gross_area_m2=(c-a)*(d-b),reason=p.reason))
    unions=[]
    for k,level in enumerate(levels):
        group=[v for v in volumes if v.level_index==k+1]
        shape=unary_union([box(xs[v.grid_rect[0]],ys[v.grid_rect[1]],
                              xs[v.grid_rect[2]],ys[v.grid_rect[3]]) for v in group])
        # Collinear room/spine seam vertices do not divide a physical facade face.
        # Preserve the exact union while letting a doorway span that common face.
        ring,holes=_polygon_rings(shape.simplify(0,preserve_topology=True))
        unions.append(ProgramVolumeUnion(level_index=k+1,level_id=level.id,boundary=ring,
                      voids=holes,gross_area_m2=shape.area,source_volume_ids=[v.id for v in group]))
    # Gross floor area includes circulation and structure, but not upper airspace
    # over a tall room. The envelope union still retains that airspace for facades.
    if floor_area>brief.target_gross_area_m2+1e-6:
        raise LayoutRejected(['Exact Program Volume floor union exceeds gross budget'])
    signature=hashlib.sha256(json.dumps([v.model_dump() for v in volumes],sort_keys=True).encode()).hexdigest()[:12]
    grammar='PVG-LEGACY-ELLIPSE'
    from .world_xy_grid import WorldXYGrid
    intent = _circulation_intent_for(grammar=grammar,topology_signature=signature,
        volumes=volumes,levels=levels,unions=unions,grid=grid,
        flight_width_m=controls.flight_width_m,entry_carrier_id='PV-L01-CIRC-4')
    if arrival is not None:
        from .program_volume_contracts import GridBoundaryStation
        carrier = next(v for v in volumes if v.id == 'PV-L01-CIRC-4')
        i0,j0,_,j1 = carrier.grid_rect
        intent = intent.model_copy(update={
            'entry_station': GridBoundaryStation(level_id=levels[0].id,
                source_volume_id=carrier.id,grid_edge=(i0,j1,i0,j0),
                fraction=(ys[j1]-arrival_origin[1])/(ys[j1]-ys[j0])),
            'arrival_assembly': arrival,
            'approach_depth_provenance': 'Whole arrival reserved against the actual parcel before room allocation',
            'reason': intent.reason+' '+arrival.basis})
    return ProgramVolumeModel(score_id=score.score_id,typology=brief.typology,
        project_brief=brief,grammar_id=grammar,
        world_xy_grid=WorldXYGrid(spacing_x=datums.value('bay_x_m'),
                                  spacing_y=datums.value('bay_y_m')),
        design_datums={'flight_width_m': controls.flight_width_m,
                       'ground_open_height_m': controls.entry_elevation_m},
        grammar_reason=['Legacy free XY proposals bounded by the project site, setbacks and facade reserve',
                        *([f'Joint root {root.relation}: {root.basis}'] if root is not None else []),
                        f'Whole backbone composition: {controls.backbone_layout}',
                        f'Stair run axis: {controls.stair_run_axis}',
                        *([f'Secondary stair uses the {secondary_axis.upper()} axis at east-field inset {controls.secondary_core_inset_fraction:g}; '
                           'shared foyer proportions follow the available core-access span; hall galleries meet actual network terminals']
                          if distributed else []),
                        *(['Shared-access frontage precedes new room branches; free XY preference orders each class',
                           'Joint level proposals place sectional program anchors before filling a storey twice']
                          if rear_commons else []),
                        *([f'Hall depth position: {controls.hall_depth_position}; '
                           f'depth {next(p.shape.bounds[3]-p.shape.bounds[1] for p in placed if house.id in p.spaces):.4f} m']
                          if theater else ['Library reading-room owner reserves its upper airspace before ordinary rooms']),
                        f'Proposal schedule: {controls.proposal_schedule}',
                        f'Coordinated room/route search: {search.nodes}/{controls.layout_max_nodes} nodes; '
                        f'at most {controls.room_candidate_limit} choices per room and allowed level'],
        authored_cores=[{'id':label, 'kind':kind, 'source_volume_id':f'PV-L01-CIRC-{index}',
                         **({'access_face':'south'} if kind=='lift' and root is not None else {}),
                         'run_axis':(secondary_axis if distributed and index == 1 else controls.stair_run_axis)
                                    if kind=='stair' else 'y'}
                        for label,kind,index in (('CORE-A','stair',0),('CORE-B','stair',1),('LIFT-1','lift',3))],
        levels=levels,grid=grid,volumes=volumes,level_unions=unions,topology_signature=signature,
        program_volume_regions=_program_volume_regions(volumes,levels),
        circulation_intent=intent,
        roof_control=score_roof_control(unions[-1].boundary,unions[-1].voids,
            datum_z=levels[-1].z_top,hierarchy_datum=datums.by_id('truss_depth_m')),
        note='Legacy free-XY restoration. '+controls.note)
