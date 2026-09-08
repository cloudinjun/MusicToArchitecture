"""Door apertures and the walking surfaces on both sides, read from solids.

The approach dimensions are a project review convention, not an ADA manoeuvring
clearance or a code approval. A drawn leaf is not evidence that its wall is open.
Lift openings remain non-traversable while the car-side floor is absent.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel, Field
from shapely.geometry import MultiPoint, Point, Polygon, box
from shapely.ops import unary_union

from .geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, QuadGeometry, v3
from .geometry_review import _polygon, _z_interval
from .mesh_primitives import member_mesh

APPROACH_DEPTH_M = 1.2
APPROACH_WIDTH_M = 1.2
FLOOR_TOLERANCE_M = .005
AREA_TOLERANCE_M2 = 1e-6
REVIEW_HEAD_M = 2.1
WALKING_KINDS = {'floor_slab', 'podium_slab', 'stair_landing', 'ramp_landing',
                 'lift_landing', 'auditorium_riser', 'stage_platform', 'site_step',
                 'lift_car'}
WALL_KINDS = {'partition', 'partition_head', 'elevator_shaft', 'core_wall',
              'shear_wall', 'proscenium_wall', 'wall_panel', 'solid_wall_panel',
              'glazing_panel', 'entrance_head', 'backing_panel', 'field_panel',
              'facet_panel', 'facet_glazing', 'order_field'}
NON_OBSTACLE_KINDS = {'program_zone', 'figure', 'site_ground', 'footing'}


class PortalFinding(BaseModel):
    rule_id: str
    portal_id: str
    elements: list[str] = Field(default_factory=list)
    detail: str
    measure: float = 0.0
    unit: str = ''


class PortalSide(BaseModel):
    region: list[tuple[float, float]]
    support_ids: list[str] = Field(default_factory=list)
    unsupported_m2: float = 0.0
    elevation_mismatch_m: float | None = None
    clash_ids: list[str] = Field(default_factory=list)


class DoorPortal(BaseModel):
    id: str
    door_ids: list[str]
    level_id: str
    kind: Literal['room', 'entrance', 'lift']
    center: tuple[float, float]
    tangent: tuple[float, float]
    normal: tuple[float, float]
    aperture: list[tuple[float, float]]
    floor_z: float
    width_m: float
    height_m: float
    wall_depth_m: float
    host_wall_ids: list[str] = Field(default_factory=list)
    side_a: PortalSide
    side_b: PortalSide
    aperture_clear: bool = False
    passable: bool = False
    reasons: list[str] = Field(default_factory=list)


class PortalReport(BaseModel):
    schema_version: Literal['mta.portals/1.0'] = 'mta.portals/1.0'
    status: Literal['passed', 'failed', 'unevaluated']
    portals: list[DoorPortal]
    findings: list[PortalFinding]
    basis: str = ('Aperture and level support measured from emitted geometry; '
                  '1.2 m approach depth/width is a project review convention. '
                  'Door operation, fire protection and code compliance are unverified.')


class WallOpening(BaseModel):
    at_m: float
    width_m: float
    threshold_z: float
    height_m: float = 2.1
    existing_door_ids: list[str] = Field(default_factory=list)


@dataclass
class _Solid:
    id: str
    kind: str
    level_id: str
    polygon: object
    low: float
    high: float
    group: object
    geometry: object


def _solids(model):
    result = []
    cache = getattr(model, '_portal_geometry_cache', None)
    for group in model.element_groups:
        for item in group.instances:
            geometry = item.geometry
            if cache is not None and item.id in cache:
                previous = cache[item.id]
                if previous.geometry is geometry and previous.group is group:
                    result.append(previous)
                    continue
            polygon, vertical = _polygon(geometry), _z_interval(geometry)
            if isinstance(geometry, MemberGeometry):
                profiles = {key: value.model_dump() if hasattr(value, 'model_dump') else value
                            for key, value in getattr(model, 'profiles', {}).items()}
                if geometry.profile not in profiles:
                    continue
                vertices, _ = member_mesh(geometry.model_dump(), profiles)
                polygon = MultiPoint([(x, y) for x, y, _ in vertices]).convex_hull
                vertical = min(v[2] for v in vertices), max(v[2] for v in vertices)
            elif isinstance(geometry, QuadGeometry):
                points = [(p.x, p.y) for p in geometry.corners]
                polygon = MultiPoint(points).convex_hull
                # A vertical panel's plan projection is a line; its physical depth
                # comes from the group, never from an assumed wall thickness.
                thickness = getattr(group, 'thickness_m', None)
                if thickness:
                    polygon = polygon.buffer(thickness / 2, cap_style=2)
                vertical = (min(p.z for p in geometry.corners),
                            max(p.z for p in geometry.corners))
            if polygon is not None and vertical and not polygon.is_empty:
                solid = _Solid(item.id, group.kind, item.level_id, polygon,
                               *vertical, group, geometry)
                result.append(solid)
                if cache is not None:
                    cache[item.id] = solid
    return result


def _ring(region):
    return [(round(x, 6), round(y, 6)) for x, y in list(region.exterior.coords)[:-1]]


def _rectangle(center, tangent, across0, across1, width):
    tx, ty = tangent
    nx, ny = -ty, tx
    cx, cy = center
    return Polygon([(cx + tx * along + nx * across,
                     cy + ty * along + ny * across)
                    for along, across in ((-width/2, across0), (width/2, across0),
                                          (width/2, across1), (-width/2, across1))])


def _door_basis(doors):
    first = doors[0]
    geometry = first.geometry
    if isinstance(geometry, BoxGeometry):
        angle = geometry.rotation_z + (math.pi/2 if geometry.size.y > geometry.size.x else 0)
        tangent = math.cos(angle), math.sin(angle)
        depth = min(geometry.size.x, geometry.size.y)
    elif isinstance(geometry, QuadGeometry):
        pairs = [(a, b) for a in geometry.corners for b in geometry.corners
                 if abs(a.z-b.z) <= FLOOR_TOLERANCE_M]
        a, b = max(pairs, key=lambda pair: math.hypot(pair[0].x-pair[1].x, pair[0].y-pair[1].y))
        length = math.hypot(b.x-a.x, b.y-a.y)
        tangent = (b.x-a.x)/length, (b.y-a.y)/length
        depth = getattr(first.group, 'thickness_m', None)
        if not depth:
            return None
    else:
        return None
    tx, ty = tangent
    if tx < -1e-8 or (abs(tx) < 1e-8 and ty < 0):
        tangent = -tx, -ty
    tx, ty = tangent
    coords = [p for door in doors for p in door.polygon.exterior.coords]
    along = [x*tx+y*ty for x, y in coords]
    across = [-x*ty+y*tx for x, y in coords]
    u, v = (min(along)+max(along))/2, (min(across)+max(across))/2
    return ((u*tx-v*ty, u*ty+v*tx), tangent, max(along)-min(along),
            depth, min(d.low for d in doors), max(d.high for d in doors))


def _portal_shapes(solids):
    grouped = {}
    for solid in solids:
        if solid.kind not in {'door', 'entrance_door'}:
            continue
        key = re.sub(r'-L\d+$', '', solid.id) if solid.kind == 'entrance_door' else solid.id
        grouped.setdefault(key, []).append(solid)
    for identifier, doors in grouped.items():
        basis = _door_basis(doors)
        if basis is None:
            continue
        center, tangent, width, depth, floor, top = basis
        kind = ('entrance' if doors[0].kind == 'entrance_door' else
                'lift' if doors[0].group.subsystem == 'vertical_core' else 'room')
        # Find the actual wall at the aperture edges. Its depth, not half-depth of
        # a closed leaf, determines where either walking approach starts.
        neighbourhood = _rectangle(center, tangent, -.6, .6, width+.15)
        hosts = [s for s in solids if s.kind in WALL_KINDS
                 and s.high > floor + .1 and s.low < top-.01
                 and s.polygon.intersects(neighbourhood)]
        nx, ny = -tangent[1], tangent[0]
        for host in hosts:
            if isinstance(host.geometry, BoxGeometry):
                g = host.geometry
                axis = math.cos(g.rotation_z), math.sin(g.rotation_z)
                # Ignore perpendicular walls: their full length is not wall depth.
                host_tangent = axis if g.size.x >= g.size.y else (-axis[1], axis[0])
                if abs(sum(a*b for a, b in zip(tangent, host_tangent))) > .99:
                    depth = max(depth, min(g.size.x, g.size.y))
            elif kind == 'lift':
                # The emitted shaft wall beside this opening is inspected locally.
                clipped = host.polygon.intersection(neighbourhood)
                if not clipped.is_empty:
                    coords = list(clipped.envelope.exterior.coords)
                    offsets = [(x-center[0])*nx+(y-center[1])*ny for x,y in coords]
                    depth = max(depth, min(1.2, max(offsets)-min(offsets)))
        approach_width = max(width, APPROACH_WIDTH_M)
        aperture = _rectangle(center, tangent, -depth/2, depth/2, width)
        a = _rectangle(center, tangent, depth/2, depth/2+APPROACH_DEPTH_M, approach_width)
        b = _rectangle(center, tangent, -depth/2-APPROACH_DEPTH_M, -depth/2, approach_width)
        yield identifier, doors, kind, basis, depth, hosts, aperture, a, b


def approach_regions(model, level_id):
    """Reserved walking approaches for furniture layout, including blocked doors."""
    return [region for row in _portal_shapes(_solids(model))
            if row[1][0].level_id == level_id for region in row[-2:]]


def _side(region, floor, solids, door_ids, head=REVIEW_HEAD_M):
    floors = [s for s in solids if s.kind in WALKING_KINDS
              and abs(s.high-floor) <= FLOOR_TOLERANCE_M
              and s.polygon.intersection(region).area > AREA_TOLERANCE_M2]
    support = unary_union([s.polygon for s in floors])
    unsupported = region.difference(support.buffer(1e-5)).area
    nearby = [abs(s.high-floor) for s in solids if s.kind in WALKING_KINDS
              and s.polygon.intersection(region).area > AREA_TOLERANCE_M2]
    clashes = [s.id for s in solids if s.id not in door_ids
               and s.kind not in NON_OBSTACLE_KINDS
               and min(s.high, floor+head)-max(s.low, floor+.01) > .005
               and s.polygon.intersection(region).area > AREA_TOLERANCE_M2]
    return PortalSide(region=_ring(region), support_ids=[s.id for s in floors],
                      unsupported_m2=round(unsupported, 6),
                      elevation_mismatch_m=min(nearby) if nearby else None,
                      clash_ids=clashes)


def inspect_portals(model) -> PortalReport:
    solids = _solids(model)
    portals, findings = [], []
    for identifier, doors, kind, basis, depth, hosts, aperture, a, b in _portal_shapes(solids):
        center, tangent, width, _, floor, top = basis
        door_ids = [d.id for d in doors]
        side_a, side_b = (_side(region, floor, solids, door_ids) for region in (a, b))
        aperture_check = _side(aperture.buffer(-1e-5), floor, solids, door_ids, top-floor)
        portal = DoorPortal(id=identifier, door_ids=door_ids, level_id=doors[0].level_id,
                            kind=kind, center=center, tangent=tangent,
                            normal=(-tangent[1], tangent[0]), aperture=_ring(aperture),
                            floor_z=floor, width_m=width, height_m=top-floor,
                            wall_depth_m=depth, host_wall_ids=[s.id for s in hosts],
                            side_a=side_a, side_b=side_b,
                            aperture_clear=not aperture_check.clash_ids)
        def fail(rule, detail, ids=(), measure=0., unit=''):
            portal.reasons.append(detail)
            findings.append(PortalFinding(rule_id=rule, portal_id=identifier,
                                          elements=list(ids), detail=detail,
                                          measure=measure, unit=unit))
        if not hosts:
            fail('PORTAL-WALL-UNRESOLVED', 'No emitted host wall identifies this opening.')
        if aperture_check.clash_ids:
            fail('PORTAL-APERTURE-BLOCKED', 'Solid geometry closes the door aperture.',
                 aperture_check.clash_ids)
        # A lift door has one landing-side approach and one car/shaft-side
        # condition.  The latter is not a second walking approach: a shaft with
        # no car floor is intentionally unresolved, and treating its void as a
        # failed approach made every upper landing look geometrically broken.
        sides_to_check = ((('a', side_a), ('b', side_b)) if kind != 'lift'
                          else tuple(
                              (name, side) for name, side in (('a', side_a),
                                                              ('b', side_b))
                              if (side.unsupported_m2 <= AREA_TOLERANCE_M2
                                  and not side.clash_ids)))
        if kind == 'lift' and not sides_to_check:
            # No supported landing-side surface exists. Keep the actual measured
            # failure; this is different from an unevaluated car-side condition.
            sides_to_check = (('a', side_a), ('b', side_b))
        for name, side in sides_to_check:
            if side.unsupported_m2 > AREA_TOLERANCE_M2:
                fail('PORTAL-APPROACH-UNSUPPORTED',
                     f'Approach {name} lacks a floor at the door threshold elevation.',
                     side.support_ids, side.unsupported_m2, 'm2')
            if side.clash_ids:
                fail('PORTAL-APPROACH-BLOCKED', f'Approach {name} contains solid obstacles.',
                     side.clash_ids)
        if aperture_check.unsupported_m2 > AREA_TOLERANCE_M2:
            fail('PORTAL-THRESHOLD-UNSUPPORTED', 'The threshold does not have continuous floor support.',
                 measure=aperture_check.unsupported_m2, unit='m2')
        if kind == 'lift':
            # The car is parked at one landing; that door opens onto its floor and
            # the others open onto the shaft. Measured off the car floor, not read
            # off the shaft's claim to serve the level.
            car = [s for s in solids if s.kind == 'lift_car'
                   and abs(s.high - floor) <= FLOOR_TOLERANCE_M
                   and s.polygon.intersects(aperture.buffer(0.1))]
            if not car:
                fail('PORTAL-LIFT-CAR-UNVERIFIED',
                     'Shaft aperture exists; no car floor stands at this landing, so this is not a walking edge.')
        portal.passable = not portal.reasons
        portals.append(portal)
    for solid in solids:
        if 'MTA-DOOR-UNRESOLVED' in getattr(solid.group, 'rule_refs', []):
            findings.append(PortalFinding(rule_id='PORTAL-REQUIRED-UNPLACED',
                portal_id=solid.id, elements=[solid.id],
                detail='Required door has no feasible two-sided supported approach; wall remains closed.'))
    required_rooms = {}
    for solid in solids:
        for rule in getattr(solid.group, 'rule_refs', []):
            if rule.startswith('MTA-ROOM-ACCESS-REQUIRED:'):
                room = rule.split(':',1)[1]
                required_rooms.setdefault((solid.level_id,room),[]).append(solid.id)
    zones = {(z.level_id,z.space_id):z for z in
             getattr(getattr(model,'program_allocation',None),'zones',[])}
    for key,wall_ids in required_rooms.items():
        zone = zones.get(key)
        room = box(zone.x0,zone.y0,zone.x1,zone.y1) if zone is not None else None
        accessible = room is not None and any(
            portal.passable and portal.level_id == key[0]
            and room.boundary.distance(Point(portal.center)) <= portal.wall_depth_m/2+.01
            and any(room.intersection(Polygon(side.region)).area > .1
                    for side in (portal.side_a,portal.side_b)) for portal in portals)
        if not accessible:
            findings.append(PortalFinding(rule_id='PORTAL-ROOM-INACCESSIBLE',
                portal_id=f'{key[0]}:{key[1]}',elements=wall_ids,
                detail='Enclosed room has no measured usable door connection to its surroundings.'))
    represented = {identifier for portal in portals for identifier in portal.door_ids}
    unresolved = []
    for group in model.element_groups:
        for item in group.instances:
            if ((group.kind in {'door','entrance_door'} and item.id not in represented)
                    or (isinstance(item.geometry, MemberGeometry)
                        and item.geometry.profile not in getattr(model, 'profiles', {}))):
                unresolved.append(item.id)
    if unresolved:
        detail = 'Door or member geometry is unresolved; obstruction review cannot be complete.'
        findings.append(PortalFinding(rule_id='PORTAL-GEOMETRY-UNRESOLVED',portal_id='',
                                      elements=unresolved, detail=detail))
        for portal in portals:
            portal.passable = False
            portal.reasons.append(detail)
    blocking_findings = [finding for finding in findings
                         if finding.rule_id != 'PORTAL-LIFT-CAR-UNVERIFIED']
    status = ('failed' if blocking_findings else
              'unevaluated' if findings else
              'passed' if portals else 'unevaluated')
    return PortalReport(status=status,
                        portals=portals, findings=findings)


def choose_partition_opening(builder, level, start, end, width, wall_depth):
    """Choose a position with real two-sided floor and no core/solid obstruction."""
    length = math.dist(start, end)
    margin = max(width, APPROACH_WIDTH_M)/2 + .01
    if length < 2*margin:
        return None
    tangent = ((end[0]-start[0])/length, (end[1]-start[1])/length)
    if not hasattr(builder, '_portal_geometry_cache'):
        builder._portal_geometry_cache = {}
    solids = _solids(SimpleNamespace(element_groups=list(builder.groups.values()),
                                    profiles=builder.profiles,
                                    _portal_geometry_cache=builder._portal_geometry_cache))
    neighbourhood = box(min(start[0],end[0]),min(start[1],end[1]),
                        max(start[0],end[0]),max(start[1],end[1])).buffer(
                            APPROACH_DEPTH_M+wall_depth+APPROACH_WIDTH_M)
    solids = [s for s in solids if s.high >= level.z-FLOOR_TOLERANCE_M
              and s.low <= level.z+REVIEW_HEAD_M and s.polygon.intersects(neighbourhood)]
    count = max(1, math.ceil((length-2*margin)/.2))
    positions = {length/2, *(margin+(length-2*margin)*i/count for i in range(count+1))}
    for along in sorted(positions, key=lambda value: (abs(value-length/2), value)):
        center = (start[0]+tangent[0]*along, start[1]+tangent[1]*along)
        regions = [_rectangle(center, tangent, -wall_depth/2, wall_depth/2, width),
                   _rectangle(center, tangent, wall_depth/2, wall_depth/2+APPROACH_DEPTH_M,
                              max(width, APPROACH_WIDTH_M)),
                   _rectangle(center, tangent, -wall_depth/2-APPROACH_DEPTH_M,
                              -wall_depth/2, max(width, APPROACH_WIDTH_M))]
        if all((side := _side(region, level.z, solids, [])).unsupported_m2 <= AREA_TOLERANCE_M2
               and not side.clash_ids for region in regions):
            return along
    return None


def split_room_edges(zones):
    """Split a room edge at every real neighbour end; emit shared walls once.

    A neighbour along two metres of a long edge does not own its other eight.
    Only coincident boundaries are shared; a gap remains a circulation region.
    """
    for zone in zones:
        for edge, start, end in (
                ('S',(zone.x0,zone.y0),(zone.x1,zone.y0)),
                ('N',(zone.x0,zone.y1),(zone.x1,zone.y1)),
                ('W',(zone.x0,zone.y0),(zone.x0,zone.y1)),
                ('E',(zone.x1,zone.y0),(zone.x1,zone.y1))):
            horizontal = edge in ('S','N')
            lo,hi = (start[0],end[0]) if horizontal else (start[1],end[1])
            fixed = start[1] if horizontal else start[0]
            neighbours, stops = [], {lo,hi}
            for other in zones:
                if other.space_id == zone.space_id:
                    continue
                other_fixed = {'S':other.y1,'N':other.y0,'W':other.x1,'E':other.x0}[edge]
                a,c = (other.x0,other.x1) if horizontal else (other.y0,other.y1)
                a,c = max(lo,a),min(hi,c)
                if abs(other_fixed-fixed) <= FLOOR_TOLERANCE_M and c-a > 1e-5:
                    neighbours.append((a,c,other))
                    stops.update((a,c))
            stops = sorted(stops)
            for index,(a,c) in enumerate(zip(stops,stops[1:])):
                neighbour = next((other for n0,n1,other in neighbours
                                  if n0-1e-5 <= (a+c)/2 <= n1+1e-5),None)
                if neighbour is not None and neighbour.space_id < zone.space_id:
                    continue
                points = (a,fixed,c,fixed) if horizontal else (fixed,a,fixed,c)
                yield zone,neighbour,f'{edge}{index:02}',points


def matching_entrances(builder, level, start, end, wall_depth):
    """Continue existing façade apertures through a coincident program wall."""
    length = math.dist(start,end)
    tangent = ((end[0]-start[0])/length,(end[1]-start[1])/length)
    normal = -tangent[1],tangent[0]
    if not hasattr(builder,'_portal_geometry_cache'):
        builder._portal_geometry_cache={}
    model = SimpleNamespace(element_groups=list(builder.groups.values()),profiles=builder.profiles,
                            _portal_geometry_cache=builder._portal_geometry_cache)
    count = sum(len(group.instances) for group in builder.groups.values())
    cache = getattr(builder,'_portal_entry_shapes',None)
    if cache is None or cache[0] != count:
        cache = count,list(_portal_shapes(_solids(model)))
        builder._portal_entry_shapes=cache
    openings = []
    for row in cache[1]:
        _,doors,kind,basis,*_ = row
        if kind != 'entrance' or doors[0].level_id != level.id:
            continue
        center,axis,width,depth,floor,top = basis
        offset = ((center[0]-start[0])*normal[0]+(center[1]-start[1])*normal[1])
        if abs(sum(a*b for a,b in zip(tangent,axis))) < .99 or abs(offset) > (wall_depth+depth)/2+.01:
            continue
        along = (center[0]-start[0])*tangent[0]+(center[1]-start[1])*tangent[1]
        low,high = max(0,along-width/2),min(length,along+width/2)
        if high-low > .01:
            openings.append(WallOpening(at_m=(low+high)/2,width_m=high-low,
                threshold_z=floor,height_m=top-floor,existing_door_ids=[d.id for d in doors]))
    return openings


def wall_run_parts(start,end,base,height,thickness,openings):
    """Build solids around apertures; existing entrance leaves are never duplicated."""
    length = math.dist(start,end)
    horizontal = abs(end[0]-start[0]) >= abs(end[1]-start[1])
    cuts = sorted(openings,key=lambda opening:opening.at_m)
    parts = []
    def add(tag,kind,a,c,z0,z1):
        if c-a <= 1e-5 or z1-z0 <= 1e-5:
            return
        t = (a+c)/(2*length)
        center = v3(start[0]+(end[0]-start[0])*t,start[1]+(end[1]-start[1])*t,(z0+z1)/2)
        size = v3(c-a,thickness,z1-z0) if horizontal else v3(thickness,c-a,z1-z0)
        parts.append((tag,kind,BoxGeometry(center=center,size=size)))
    cursor = 0.
    for i,opening in enumerate(cuts):
        low,high = max(cursor,opening.at_m-opening.width_m/2),min(length,opening.at_m+opening.width_m/2)
        add(f'W{i:02}','partition',cursor,low,base,base+height)
        add(f'SILL{i:02}','partition',low,high,base,max(base,opening.threshold_z))
        add(f'HD{i:02}','partition_head',low,high,
            min(base+height,opening.threshold_z+opening.height_m),base+height)
        cursor = max(cursor,high)
    add(f'W{len(cuts):02}','partition',cursor,length,base,base+height)
    return parts


def select_lift_face(builder, floors, cx, cy, shaft_width, thickness, door_width, preferred,
                     declared_face=None):
    """One shaft face supported and clear on the most landing levels, then nearest stair.

    No opening is emitted on an unsupported level. Car-side service remains a
    separate unverified condition even where the external landing fits.
    """
    solids = _solids(SimpleNamespace(element_groups=list(builder.groups.values()),profiles=builder.profiles))
    options = []
    faces = {'east':(True,1.),'west':(True,-1.),'north':(False,1.),'south':(False,-1.)}
    choices = [faces[declared_face]] if declared_face is not None else [preferred,*faces.values()]
    from .core_access import lift_approach_bounds
    for face_x,side in choices:
        face = next(name for name,value in faces.items() if value==(face_x,side))
        region = box(*lift_approach_bounds(cx,cy,shaft_width,face,
                     max(door_width,APPROACH_WIDTH_M),APPROACH_DEPTH_M))
        served = [level.id for level in floors
                  if (check := _side(region,level.z,solids,[])).unsupported_m2 <= AREA_TOLERANCE_M2
                  and not check.clash_ids]
        options.append((face_x,side,served))
    return max(enumerate(options),key=lambda pair:(len(pair[1][2]),-pair[0]))[1]


def stage_access_plan(builder, level, carve):
    """A ground-level door pocket and solid steps within the stage footprint.

    180 mm rise / 300 mm tread is the requested planning recipe, not a code
    approval. The stage body gives up the entire access pocket, so neither the
    doorway nor the steps are hidden inside the raised stage solid.
    """
    x0,y0,x1,y1=carve.stage
    rise=carve.focal_h_m
    count=max(1,math.ceil(rise/.18-1e-8))
    tread=.30
    bottom_depth=APPROACH_DEPTH_M+.20  # includes wall thickness at the threshold
    top_depth=APPROACH_DEPTH_M
    width=APPROACH_WIDTH_M+.20
    depth=bottom_depth+count*tread+top_depth
    stage=box(x0,y0,x1,y1)
    solids=_solids(SimpleNamespace(element_groups=list(builder.groups.values()),profiles=builder.profiles))
    edges=[((x0,y0),(x1,y0),(0.,1.)),((x0,y1),(x1,y1),(0.,-1.))]
    # The proscenium opening belongs to the audience/stage interface; service
    # access uses a side or the back of the stage, never that opening's wall.
    if abs(carve.proscenium_x-x0) < abs(carve.proscenium_x-x1):
        edges.append(((x1,y0),(x1,y1),(-1.,0.)))
    else:
        edges.append(((x0,y0),(x0,y1),(1.,0.)))
    def region(center,tangent,normal,d0,d1,w):
        return Polygon([(center[0]+tangent[0]*u+normal[0]*v,
                         center[1]+tangent[1]*u+normal[1]*v)
                        for u,v in ((-w/2,d0),(w/2,d0),(w/2,d1),(-w/2,d1))])
    for start,end,normal in edges:
        length=math.dist(start,end)
        if length<width+.02:
            continue
        tangent=((end[0]-start[0])/length,(end[1]-start[1])/length)
        margin=width/2+.01
        samples=max(1,math.ceil((length-2*margin)/.2))
        positions={length/2,*(margin+(length-2*margin)*i/samples for i in range(samples+1))}
        for along in sorted(positions,key=lambda value:(abs(value-length/2),value)):
            center=(start[0]+tangent[0]*along,start[1]+tangent[1]*along)
            pocket=region(center,tangent,normal,0,depth,width)
            outside=region(center,tangent,normal,-APPROACH_DEPTH_M-.15,-.15,APPROACH_WIDTH_M)
            if not stage.buffer(1e-6).covers(pocket):
                continue
            if not all((check:=_side(candidate,level.z,solids,[])).unsupported_m2<=AREA_TOLERANCE_M2
                       and not check.clash_ids for candidate in (pocket,outside)):
                continue
            parts=[]
            def solid(tag,kind,d0,d1,height):
                shape=region(center,tangent,normal,d0,d1,width)
                ax,ay,bx,by=shape.bounds
                parts.append((tag,kind,BoxGeometry(center=v3((ax+bx)/2,(ay+by)/2,level.z+height/2),
                                                   size=v3(bx-ax,by-ay,height))))
            for i in range(count):
                solid(f'STEP{i:02}','stair_tread',bottom_depth+i*tread,
                      bottom_depth+(i+1)*tread,rise*(i+1)/count)
            # This surface arrives at the raised stage, not at a storey plate.
            # Calling it a stair landing makes the floor-landing invariant report
            # the deliberate stage rise as a 900 mm error.
            solid('TOP','stage_platform',bottom_depth+count*tread,depth,rise)
            return {'pocket':pocket,'parts':parts,'door_center':center,
                    'bottom_region':region(center,tangent,normal,0,bottom_depth,width),
                    'rise_m':rise/count,'tread_m':tread}
    return None


def shaft_wall_parts(cx, cy, shaft_width, thickness, base, top, *, face_x, side,
                     opening_bottom, opening_width, opening_height):
    """Four shaft walls, with jambs/head replacing the landing wall at its opening.

    Every position is an offset from the compiler's registered shaft anchor. The
    pit has no landing opening; the other pieces remain ordinary native solids.
    """
    half = shaft_width/2
    tangent, normal = ((0., 1.), (side, 0.)) if face_x else ((1., 0.), (0., side))
    parts = []
    def add(tag, u0, u1, v0, v1, z0, z1):
        if min(u1-u0, v1-v0, z1-z0) <= 1e-6:
            return
        u, v = (u0+u1)/2, (v0+v1)/2
        x, y = cx+tangent[0]*u+normal[0]*v, cy+tangent[1]*u+normal[1]*v
        sx, sy = ((v1-v0, u1-u0) if face_x else (u1-u0, v1-v0))
        parts.append((tag, BoxGeometry(center=v3(x,y,(z0+z1)/2), size=v3(sx,sy,z1-z0))))
    add('BACK', -half,half,-half,-half+thickness,base,top)
    add('SIDEA',-half,-half+thickness,-half+thickness,half-thickness,base,top)
    add('SIDEB',half-thickness,half,-half+thickness,half-thickness,base,top)
    if opening_bottom is None:
        add('FRONT',-half,half,half-thickness,half,base,top)
    else:
        add('JAMBA',-half,-opening_width/2,half-thickness,half,base,top)
        add('JAMBB',opening_width/2,half,half-thickness,half,base,top)
        add('SILL',-opening_width/2,opening_width/2,half-thickness,half,
            base,min(top,opening_bottom))
        add('HEAD',-opening_width/2,opening_width/2,half-thickness,half,
            max(base,opening_bottom+opening_height),top)
    return parts
