"""Located room fixtures and measurable use/service/aisle reservations.

Recipes are project planning conventions, without plumbing counts, equipment sizing
or accessibility approval. Every placement is derived from an allocated room and
is refused when its complete body or working area cannot fit. Reservations are
metadata, never translucent solids sent to fabrication or mistaken for construction.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel, Field
from shapely.affinity import rotate, translate
from shapely.geometry import MultiPoint, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .furniture import FurniturePart, footprint, furniture_parts, usable_floor
from .geometry import BoxGeometry, v3
from .geometry_review import _polygon, _z_interval
from .mesh_primitives import primitive_mesh
from .plan_regions import rectangular_runs
from .archetypes import (
    AISLE_TREAD_M, ROW_PASSAGE_M, SEAT_LINE_OFFSET_M,
    THEATRE_SEAT_DEPTH_M as SEAT_DEPTH_M,
)


AREA_EPS = 1e-7
CONTACT_EPS_M = 1e-5
USE_HEIGHT_M = 2.1
AISLE_WIDTH_M = 1.2
SEAT_WIDTH_M = .52
SEAT_PITCH_M = .57
AISLE_STEP_REVIEW_M = .18
PLAN_BASIS = 'Project planning recipe; dimensions require project-specific review, not a code-compliance result.'
RAIL_DIAMETER_M = .045
RAIL_HEIGHT_M = .9
WHEELCHAIR_WIDTH_M = .9
WHEELCHAIR_DEPTH_M = 1.2
SUPPORT_KINDS = {'floor_slab', 'podium_slab', 'auditorium_riser', 'auditorium_aisle'}
NON_OBSTACLES = {'program_zone', 'figure', 'site_ground'}
FIXTURE_KINDS = {'sanitary_fixture', 'mechanical_equipment', 'electrical_equipment'}


class LayoutReservation(BaseModel):
    id: str
    space_id: str
    level_id: str
    purpose: Literal['fixture_use', 'equipment_service', 'longitudinal_aisle',
                     'cross_aisle', 'seat_row_access', 'wheelchair_position']
    polygon: list[tuple[float, float]]
    floor_z_m: float
    clear_height_m: float = USE_HEIGHT_M
    basis: str = PLAN_BASIS


class AssemblyIntent(BaseModel):
    assembly_id: str
    space_id: str
    level_id: str
    recipe: str
    required_roles: list[str]
    floor_roles: list[str]
    floor_z_m: float


class SpaceLayoutPlan(BaseModel):
    space_id: str
    space_type: str
    level_id: str
    proposed_counts: dict[str, int]
    # A fit count does not answer the adopted plumbing code or a seating brief.
    required_counts: dict[str, int] | None = None
    count_basis: str
    omitted: dict[str, str] = Field(default_factory=dict)
    unresolved: list[str] = Field(default_factory=list)


class RoomLayoutPlan(BaseModel):
    schema_version: Literal['mta.room_layout_plan/1.0'] = 'mta.room_layout_plan/1.0'
    spaces: list[SpaceLayoutPlan] = Field(default_factory=list)
    assemblies: list[AssemblyIntent] = Field(default_factory=list)
    reservations: list[LayoutReservation] = Field(default_factory=list)


class LayoutFinding(BaseModel):
    check_id: str
    status: Literal['failed', 'unevaluated']
    space_id: str
    element_ids: list[str] = Field(default_factory=list)
    detail: str


class RoomLayoutReport(BaseModel):
    schema_version: Literal['mta.room_layout_report/1.0'] = 'mta.room_layout_report/1.0'
    status: Literal['passed', 'failed', 'unevaluated']
    assembly_count: int
    counts_by_recipe: dict[str, int]
    reservation_count: int
    findings: list[LayoutFinding]
    checks_run: list[str]
    quantity_adequacy: Literal['unevaluated'] = 'unevaluated'
    basis: str = PLAN_BASIS


@dataclass(frozen=True)
class FixtureRecipe:
    kind: str
    width: float
    depth: float
    parts: tuple[FurniturePart, ...]
    clearance: Polygon
    purpose: str


def fixture_recipe(name: str) -> FixtureRecipe:
    """Local fixture coordinates; an allocated zone supplies the world location."""
    parts = []

    def part(role, x, y, bottom, width, depth, height, hosts=('$floor',)):
        parts.append(FurniturePart(role, BoxGeometry(center=v3(x, y, bottom + height/2),
            size=v3(width, depth, height)), hosts))

    if name == 'toilet':
        width, depth, kind = .42, .72, 'sanitary_fixture'
        part('pedestal', 0, -.03, 0, .25, .38, .31)
        part('bowl_base', 0, .08, .31, .38, .43, .06, ('pedestal',))
        for tag, x, y, w, d in [('left', -.175, .08, .05, .43),
                               ('right', .175, .08, .05, .43),
                               ('front', 0, .275, .4, .04),
                               ('rear', 0, -.115, .4, .04)]:
            part('bowl_'+tag, x, y, .37, w, d, .055, ('bowl_base',))
        part('cistern', 0, -.26, .31, width, .2, .42, ('pedestal',))
        clearance = box(-.6, depth/2, .6, depth/2 + 1.2)
        purpose = 'fixture_use'
    elif name == 'basin':
        width, depth, kind = .6, .5, 'sanitary_fixture'
        part('pedestal', 0, -.08, 0, .22, .22, .72)
        part('basin_base', 0, 0, .72, width, depth, .04, ('pedestal',))
        for tag, x, y, w, d in [('left', -.275, 0, .05, depth),
                               ('right', .275, 0, .05, depth),
                               ('front', 0, .225, width, .05),
                               ('rear', 0, -.225, width, .05)]:
            part('rim_'+tag, x, y, .76, w, d, .09, ('basin_base',))
        part('tap', 0, -.225, .85, .035, .035, .12, ('rim_rear',))
        part('spout', 0, -.17, .945, .035, .14, .025, ('tap',))
        clearance = box(-.45, depth/2, .45, depth/2 + .9)
        purpose = 'fixture_use'
    elif name in {'air_handler', 'electrical_cabinet'}:
        mechanical = name == 'air_handler'
        width, depth = (1.6, .9) if mechanical else (.9, .45)
        height = 1.5 if mechanical else 1.8
        kind = 'mechanical_equipment' if mechanical else 'electrical_equipment'
        part('plinth', 0, 0, 0, width, depth, .1)
        part('cabinet', 0, -.015, .1, width, depth-.03, height, ('plinth',))
        for i, x in enumerate((-width/4, width/4)):
            part(f'service_panel_{i}', x, depth/2-.015, .13,
                 width/2-.03, .03, height-.06, ('cabinet',))
        clearance = box(-max(width, 1.2)/2, depth/2,
                        max(width, 1.2)/2, depth/2+1.2)
        purpose = 'equipment_service'
    else:
        raise ValueError(f'Unknown room fixture recipe {name}')
    return FixtureRecipe(kind, width, depth, tuple(parts), clearance, purpose)


def _located(parts, x, y, z, degrees):
    angle = math.radians(degrees)
    ca, sa = math.cos(angle), math.sin(angle)
    return [FurniturePart(p.role, BoxGeometry(
        center=v3(x+ca*p.geometry.center.x-sa*p.geometry.center.y,
                  y+sa*p.geometry.center.x+ca*p.geometry.center.y,
                  z+p.geometry.center.z), size=p.geometry.size,
        rotation_z=p.geometry.rotation_z+angle), p.support_roles) for p in parts]


def _records(model):
    return [(group, item) for group in model.element_groups for item in group.instances]


def _builder_model(builder):
    return SimpleNamespace(element_groups=list(builder.groups.values()),
                           profiles=builder.profiles, lattice=builder.lattice)


def _shape(group, item, profiles):
    """Exact extruded/box footprints, conservative swept-member footprint."""
    polygon, vertical = _polygon(item.geometry), _z_interval(item.geometry)
    if polygon is not None and vertical is not None:
        return polygon, vertical
    # Use the actual section sweep, not an invented beam buffer or centre point.
    try:
        profile_id = getattr(item.geometry, 'profile', None)
        needed = {profile_id: profiles[profile_id]} if profile_id in profiles else {}
        vertices, _ = primitive_mesh(item.geometry.model_dump(),
            {key: p.model_dump() if hasattr(p, 'model_dump') else p
             for key, p in needed.items()},
            getattr(group, 'thickness_m', None))
    except ValueError as exc:
        raise ValueError(
            f'{item.id} ({group.kind}) has invalid physical geometry: {exc}') from exc
    return MultiPoint([(x,y) for x,y,_ in vertices]).convex_hull, (
        min(z for _,_,z in vertices), max(z for _,_,z in vertices))


def placement_obstacles(builder, level, floor_z=None):
    """Bodies above a floor plus every actual door's two approach regions."""
    from .portals import approach_regions
    z = level.z if floor_z is None else floor_z
    model = _builder_model(builder)
    regions = approach_regions(model, level.id)
    for group, item in _records(model):
        if group.kind in NON_OBSTACLES or group.kind in {'door', 'entrance_door'}:
            continue
        polygon, (z0,z1) = _shape(group, item, builder.profiles)
        if z1 > z+CONTACT_EPS_M and z0 < z+USE_HEIGHT_M:
            regions.append(polygon)
    return regions


def _support_candidates(model, floor_z):
    return [(item.id, _polygon(item.geometry)) for group,item in _records(model)
                  if group.kind in SUPPORT_KINDS and _z_interval(item.geometry)
                  and abs(_z_interval(item.geometry)[1]-floor_z) <= CONTACT_EPS_M]


def _support_hosts(model, parts, floor_z, candidates=None):
    if candidates is None:
        candidates = _support_candidates(model,floor_z)
    hosts_by_role = {}
    for part in parts:
        if '$floor' not in part.support_roles:
            continue
        base = footprint([part])
        hosts = [(name, polygon) for name,polygon in candidates if polygon is not None
                 and polygon.intersection(base).area > AREA_EPS]
        if not hosts or not unary_union([p for _,p in hosts]).buffer(CONTACT_EPS_M).covers(base):
            return None
        hosts_by_role[part.role] = [name for name,_ in hosts]
    return hosts_by_role


def _emit_assembly(builder, root_id, recipe, kind, parts, level, zone, region, floor_z,
                   support_candidates=None, row_index=None):
    if not region.buffer(CONTACT_EPS_M).covers(footprint(parts)):
        return False
    hosts = _support_hosts(_builder_model(builder), parts, floor_z,support_candidates)
    if hosts is None:
        return False
    ids = {part.role: f'{root_id}-PART-{part.role}' for part in parts}
    for part in parts:
        supports = [name for role in part.support_roles
                    for name in (hosts[part.role] if role == '$floor' else [ids[role]])]
        builder.add(ids[part.role], kind, 'program', 'room_fixtures', part.geometry,
            'white_soft' if kind == 'sanitary_fixture' else 'furn',
            category=zone.category, program=zone.space_type, level_id=level.id,
            lattice_index={'level': level.index, 'band': zone.band_index,
                           **({'row':row_index} if row_index is not None else {})},
            datum_refs=['bay_x_m','bay_y_m','level_count','circulation_allowance',
                        'cantilever_m','plate_step_m','plate_rotation_deg','apse_radius_m'],
            supports=supports, assembly_id=root_id, part_role=part.role,
            rule_refs=['MTA-ROOM-LAYOUT-001'],
            reason=f'{recipe}: {part.role}. {PLAN_BASIS}')
    builder.room_layout_plan.assemblies.append(AssemblyIntent(assembly_id=root_id,
        space_id=zone.space_id, level_id=level.id, recipe=recipe,
        required_roles=[part.role for part in parts],
        floor_roles=[part.role for part in parts if '$floor' in part.support_roles],
        floor_z_m=floor_z))
    return True


def _reserve(builder, zone, identifier, purpose, polygon, floor_z):
    builder.room_layout_plan.reservations.append(LayoutReservation(id=identifier,
        space_id=zone.space_id, level_id=zone.level_id, purpose=purpose,
        polygon=list(polygon.exterior.coords)[:-1], floor_z_m=floor_z))


def _perimeter_candidates(region, envelope):
    """Search on the inside of each room edge; no world-coordinate locations."""
    x0,y0,x1,y1 = region.bounds
    for degrees in (0,90,180,270):
        turned = rotate(envelope,degrees,origin=(0,0))
        a,b,c,d = turned.bounds
        lo,hi = (x0-a,x1-c) if degrees in (0,180) else (y0-b,y1-d)
        if hi < lo-CONTACT_EPS_M:
            continue
        count = max(1,math.ceil((hi-lo)/.4))
        # Deterministic room-edge stations, including both corners and the middle.
        stations = [(lo+hi)/2, *[lo+(hi-lo)*i/count for i in range(count+1)]]
        for station in stations:
            x = station if degrees in (0,180) else (x1-c if degrees == 90 else x0-a)
            y = station if degrees in (90,270) else (y0-b if degrees == 0 else y1-d)
            yield x,y,degrees


def emit_service_room(builder, level, zone, forbidden) -> bool:
    """Return whether this is a supported service-room recipe, even if it cannot fit."""
    name = zone.space_type
    if 'restroom' in name:
        recipes = ('toilet','basin')
        note = ('One toilet and one basin are a located planning example per allocated room. '
                'Fixture quantities, accessible transfer/turning, privacy compartments, '
                'sex/all-user distribution and plumbing connections remain unresolved.')
    elif name in {'mechanical','mechanical_room','plant'}:
        recipes = ('air_handler',)
        note = ('One plant cabinet is a service-envelope example. Equipment selection, '
                'plant capacity, duct/pipe routes and replacement access remain unresolved.')
    elif name in {'electrical_it','electrical'}:
        recipes = ('electrical_cabinet',)
        note = ('One cabinet is a service-envelope example. Voltage-specific working '
                'space, equipment schedule, cable routes and heat rejection remain unresolved.')
    else:
        return False
    plan = SpaceLayoutPlan(space_id=zone.space_id, space_type=name, level_id=level.id,
        proposed_counts={key:1 for key in recipes}, count_basis=note, unresolved=[note])
    builder.room_layout_plan.spaces.append(plan)
    region = usable_floor(level,zone,forbidden)
    for recipe_name in recipes:
        recipe = fixture_recipe(recipe_name)
        identifier = f'PRG-FIX-{level.id}-{zone.space_id}-{recipe_name}'
        occupied = footprint(list(recipe.parts)).union(recipe.clearance)
        placed = False
        if not region.is_empty:
            for x,y,degrees in _perimeter_candidates(region,occupied):
                clearance = translate(rotate(recipe.clearance,degrees,origin=(0,0)),x,y)
                parts = _located(recipe.parts,x,y,level.z,degrees)
                if not region.buffer(CONTACT_EPS_M).covers(clearance):
                    continue
                if _emit_assembly(builder,identifier,recipe_name,recipe.kind,parts,
                                  level,zone,region,level.z):
                    _reserve(builder,zone,identifier+'-USE',recipe.purpose,clearance,level.z)
                    region = region.difference(footprint(parts).union(clearance))
                    placed = True
                    break
        if not placed:
            plan.omitted[identifier] = ('Complete fixture, supported base and use/service '
                'area cannot fit clear of floor holes, structure and door approaches.')
    return True


def _seat_parts(x,y,z,direction):
    # The stock furniture recipe faces -local Y. Rotate so its eyes face the stage;
    # direction points away from the stage along the theatre's derived X axis.
    return _located(furniture_parts('seat',0,0,0,SEAT_WIDTH_M,SEAT_DEPTH_M),
                    x,y,z,-90*direction)


def theatre_floor_layout(carve, level, approach=None):
    """One dimensional contract for solids, doors, seating and navigation.

    The wall allowance is the largest published half-thickness in the selected
    partition catalogue; a narrow mounting strip keeps handrails outside clear lanes.
    """
    from .partitions import PARTITION_TYPES
    from .room_access import front_cross_aisle_bounds
    wall = max(part.thickness_mm for part in PARTITION_TYPES)/2000
    rail_strip = RAIL_DIAMETER_M+.05
    x0,y0,x1,y1 = carve.house
    y0,y1 = y0+wall+rail_strip,y1-wall-rail_strip
    middle = (y0+y1)/2
    south_aisle_end = y0 + AISLE_WIDTH_M
    north_aisle_start = y1 - AISLE_WIDTH_M
    if approach and approach.get('podium_id') == level.id:
        # The entrance landing is the floor replacing the slab at the public door.
        # When it reaches slightly past the nominal side aisle, widen that aisle to
        # its exact inner edge so a seating band never claims the landing. This same
        # plan is read by the slab cut, stair emitter and facade threshold.
        for rect in (approach.get('entry'), approach.get('access'),
                     approach.get('ramp_top')):
            if rect is None:
                continue
            rx0, ry0, rx1, ry1 = rect
            if min(x1, rx1) <= max(x0, rx0) + CONTACT_EPS_M:
                continue
            if ry0 <= y0 + CONTACT_EPS_M and ry1 > y0:
                south_aisle_end = max(south_aisle_end, ry1)
            if ry1 >= y1 - CONTACT_EPS_M and ry0 < y1:
                north_aisle_start = min(north_aisle_start, ry0)
    aisles = [(y0,south_aisle_end),
              (middle-AISLE_WIDTH_M/2,middle+AISLE_WIDTH_M/2),
              (north_aisle_start,y1)]
    bands = [(aisles[0][1]+rail_strip,aisles[1][0]-rail_strip),
             (aisles[1][1]+rail_strip,aisles[2][0]-rail_strip)]
    rows = [(row,carve.proscenium_x+carve.audience_dx*row.offset_front_m,
             carve.proscenium_x+carve.audience_dx*row.offset_back_m,
             level.z+row.floor_m) for row in carve.rows]
    first_x = rows[0][1] if rows else carve.proscenium_x
    last_x = rows[-1][2] if rows else first_x
    rear_x = x1-wall if carve.audience_dx>0 else x0+wall
    front_low,front_high = front_cross_aisle_bounds(first_x,carve.audience_dx,AISLE_WIDTH_M)
    return SimpleNamespace(rows=rows,aisles=aisles,seat_bands=bands,rail_strip=rail_strip,
        y0=y0,y1=y1,direction=carve.audience_dx,
        front=box(front_low,y0,front_high,y1),
        rear=box(min(last_x,rear_x),y0,max(last_x,rear_x),y1),
        front_z=level.z,rear_z=rows[-1][3] if rows else level.z)


def emit_theatre_floor(builder, carve):
    """Split the bowl at its aisles; retain seat-floor heights and real tread runs."""
    level = builder.lattice.occupied[0]
    zone = next(zone for zone in carve.zones if zone.space_type=='auditorium')
    layout = theatre_floor_layout(
        carve, level, getattr(builder, 'approach', None))
    # Make this shared dimensional plan available to program after partitions.
    builder.theatre_layout = layout
    source = _builder_model(builder)
    floor_hosts = _support_candidates(source,level.z)
    base = level.z-.05

    def floor_piece(identifier, kind, polygon, top, row=None, band=None):
        hosts = [(name, shape) for name, shape in floor_hosts
                 if shape is not None
                 and shape.intersection(polygon).area > AREA_EPS]
        if not hosts:
            # The reservation remains in the model and the independent check fails.
            return
        support = unary_union([shape for _, shape in hosts])
        if support.buffer(CONTACT_EPS_M).covers(polygon):
            pieces = [polygon]
            fragmented = False
        else:
            # A landing or core opening may take only part of a seating block. Keep
            # every full-depth supported run on either side of the opening instead of
            # dropping the whole row block; the unbuilt interval remains the opening.
            supported = support.intersection(polygon)
            _xa, ya, _xb, yb = polygon.bounds
            pieces = [box(xa, ya, xb, yb)
                      for xa, xb in rectangular_runs(supported, ya, yb)
                      if (xb - xa) * (yb - ya) > AREA_EPS]
            fragmented = True
        for piece_index, piece in enumerate(pieces):
            piece_hosts = [(name, shape) for name, shape in hosts
                           if shape.intersection(piece).area > AREA_EPS]
            if (not piece_hosts
                    or not unary_union([shape for _, shape in piece_hosts])
                    .buffer(CONTACT_EPS_M).covers(piece)):
                continue
            xa, ya, xb, yb = piece.bounds
            piece_id = (f'{identifier}-P{piece_index:02d}'
                        if fragmented else identifier)
            builder.add(piece_id, kind, 'program', 'archetype',
                BoxGeometry(center=v3((xa+xb)/2, (ya+yb)/2, (base+top)/2),
                            size=v3(xb-xa, yb-ya, top-base)),
                'concrete_light', category=zone.category, program=zone.space_type,
                level_id=level.id, lattice_index={
                    'level': level.index,
                    **({'row': row} if row is not None else {}),
                    **({'band': band} if band is not None else {}),
                },
                supports=[name for name, _ in piece_hosts],
                rule_refs=['ARCH-SIGHTLINE', 'MTA-ROOM-LAYOUT-001'],
                reason='Sightline row floor with separate stepped aisle surfaces. '
                       + PLAN_BASIS)

    for index,(row,front,back,top) in enumerate(layout.rows):
        xa,xb = sorted((front,back))
        for bi,(a,b) in enumerate(layout.seat_bands):
            floor_piece(f'PRG-BWL-{level.id}-R{row.index:02d}-B{bi}',
                        'auditorium_riser', box(xa, a, xb, b), top,
                        row.index, bi)
        next_top = layout.rows[index+1][3] if index+1<len(layout.rows) else top
        rise = next_top-top
        count = max(1,math.ceil(round(rise/AISLE_STEP_REVIEW_M,9)))
        landing_end = front+layout.direction*ROW_PASSAGE_M
        # A flat lateral passage at each seating floor precedes the rise to the next.
        for ai,(a,b) in enumerate(layout.aisles):
            sa = a-layout.rail_strip
            sb = b+layout.rail_strip
            flat = box(min(front,landing_end),sa,max(front,landing_end),sb)
            tag = f'PRG-AIS-{level.id}-R{row.index:02d}-A{ai}'
            floor_piece(tag+'-FLAT','auditorium_aisle',flat,top,row.index)
            _reserve(builder,zone,tag+'-FLAT','longitudinal_aisle',
                     box(min(front,landing_end),a,max(front,landing_end),b),top)
            for step in range(count):
                start = landing_end+(back-landing_end)*step/count
                end = landing_end+(back-landing_end)*(step+1)/count
                step_top = top+rise*(step+1)/count
                shape = box(min(start,end),sa,max(start,end),sb)
                floor_piece(f'{tag}-S{step:02d}','auditorium_aisle',shape,step_top,row.index)
                _reserve(builder,zone,f'{tag}-S{step:02d}','longitudinal_aisle',
                         box(min(start,end),a,max(start,end),b),step_top)
        for bi,(a,b) in enumerate(((layout.aisles[0][1],layout.aisles[1][0]),
                                   (layout.aisles[1][1],layout.aisles[2][0]))):
            # Aisle flat cells include the narrow rail strips and meet the seat
            # blocks; reserve their union without adding overlapping floor solids.
            _reserve(builder,zone,f'PRG-BWL-{level.id}-R{row.index:02d}-ACCESS{bi}',
                     'seat_row_access',box(min(front,landing_end),a,max(front,landing_end),b),top)
    if layout.rows:
        floor_piece('PRG-BWL-'+level.id+'-REAR-AISLE','auditorium_aisle',layout.rear,layout.rear_z)
    for name,shape,z in [('FRONT',layout.front,layout.front_z),('REAR',layout.rear,layout.rear_z)]:
        if shape.area>AREA_EPS:
            _reserve(builder,zone,zone.space_id+'-CROSS-'+name,'cross_aisle',shape,z)


def _seat_intervals(region, front, back, lower, upper):
    """Whole-depth rectangular runs after obstacles, never centre-point probes."""
    from .plan_regions import rectangular_runs
    # Rotate the room so the existing complete-strip helper can sweep seat depth.
    turned = rotate(region,90,origin=(0,0))
    runs = rectangular_runs(turned,min(front,back),max(front,back))
    return [(max(lower,-b),min(upper,-a)) for a,b in runs
            if min(upper,-a)-max(lower,-b)>=SEAT_WIDTH_M]


def _emit_wheelchair_positions(builder,level,zone,layout,plan):
    """Two front-slab bays and actual companion chairs connected to the cross aisle."""
    stageward = layout.front.centroid.x-layout.direction*AISLE_WIDTH_M/2
    far = stageward-layout.direction*WHEELCHAIR_DEPTH_M
    obstacles = placement_obstacles(builder,level)
    region = usable_floor(level,zone,obstacles)
    proposed = 0
    for bi,(a,b) in enumerate(layout.seat_bands):
        # The bay's rear meets the cross aisle; its companion is immediately beside it.
        y = (a+b)/2
        wheelchair = box(min(stageward,far),y-WHEELCHAIR_WIDTH_M/2,
                         max(stageward,far),y+WHEELCHAIR_WIDTH_M/2)
        seat_y = y+WHEELCHAIR_WIDTH_M/2+SEAT_PITCH_M/2
        seat_x = stageward-layout.direction*(SEAT_DEPTH_M/2)
        parts = _seat_parts(seat_x,seat_y,level.z,layout.direction)
        identifier = f'PRG-COMP-{level.id}-B{bi}'
        if (region.buffer(CONTACT_EPS_M).covers(wheelchair)
                and _emit_assembly(builder,identifier,'companion_seat','seat',parts,
                    level,zone,region,level.z)):
            _reserve(builder,zone,f'{zone.space_id}-WHEELCHAIR-{bi}',
                     'wheelchair_position',wheelchair,level.z)
            proposed += 1
        else:
            plan.omitted[f'{zone.space_id}-WHEELCHAIR-{bi}'] = (
                'Front wheelchair position with adjacent companion cannot fit fully '
                'supported and clear of actual structure or doorway approaches.')
    plan.proposed_counts['wheelchair_position'] = proposed
    plan.proposed_counts['companion_seat'] = proposed


def _emit_aisle_handrails(builder,level,zone,layout):
    """Short rails beside seating blocks, with every row passage left unobstructed."""
    model = _builder_model(builder)
    records = _records(model)
    surfaces = [(item.id,_polygon(item.geometry),_z_interval(item.geometry)[1])
                for group,item in records if group.kind=='auditorium_aisle'
                and item.level_id==level.id]
    for row,front,back,top in layout.rows:
        start = front+layout.direction*(ROW_PASSAGE_M+RAIL_DIAMETER_M)
        end = back-layout.direction*RAIL_DIAMETER_M
        # Both edges of each seat block receive rails outside the clear aisle.
        for bi,(a,b) in enumerate(layout.seat_bands):
            for side,y in enumerate((a-layout.rail_strip/2,b+layout.rail_strip/2)):
                points=[]
                posts=[]
                for pi,x in enumerate((start,end)):
                    base = box(x-RAIL_DIAMETER_M/2,y-RAIL_DIAMETER_M/2,
                               x+RAIL_DIAMETER_M/2,y+RAIL_DIAMETER_M/2)
                    hosts=[(identifier,z) for identifier,p,z in surfaces
                           if p is not None and p.buffer(CONTACT_EPS_M).covers(base)]
                    if not hosts:
                        break
                    host,z=max(hosts,key=lambda item:item[1])
                    identifier=f'PRG-AHR-{level.id}-R{row.index:02d}-B{bi}-E{side}-P{pi}'
                    post_geometry = BoxGeometry(
                        center=v3(x,y,z+RAIL_HEIGHT_M/2),
                        size=v3(RAIL_DIAMETER_M,RAIL_DIAMETER_M,RAIL_HEIGHT_M))
                    builder.add(identifier,'railing','program','auditorium_handrail',
                        post_geometry,
                        'frame_dark',category='circulation',program='auditorium',
                        level_id=level.id,lattice_index={'level':level.index,'row':row.index},
                        supports=[host],reason='Aisle handrail post outside the clear lane. '+PLAN_BASIS)
                    # Use the top face of the emitted post as the rail endpoint.  The
                    # post center and dimensions are the serialized geometry
                    # authority; recomputing from the pre-emission aisle elevation
                    # can differ by one last decimal after a JSON round-trip.
                    points.append(v3(
                        post_geometry.center.x,
                        post_geometry.center.y,
                        post_geometry.center.z + post_geometry.size.z / 2.0))
                    posts.append(identifier)
                if len(points)==2:
                    from .geometry import MemberGeometry, convention_profile
                    profile=convention_profile('AUDITORIUM-RAIL-45','chs',RAIL_DIAMETER_M,
                                               RAIL_DIAMETER_M,web_m=.003)
                    builder.profiles[profile.id]=profile
                    builder.add(f'PRG-AHR-{level.id}-R{row.index:02d}-B{bi}-E{side}-RAIL',
                        'railing','program','auditorium_handrail',
                        MemberGeometry(path=points,profile=profile.id),'frame_dark',
                        category='circulation',program='auditorium',level_id=level.id,
                        lattice_index={'level':level.index,'row':row.index},supports=posts,
                        reason='Segmented handrail leaves each flat row entrance open. '+PLAN_BASIS)


def emit_auditorium_seating(builder, level, zone):
    """Fit full chairs into actual supported row strips after walls and doors exist."""
    layout = getattr(builder,'theatre_layout',None)
    plan = SpaceLayoutPlan(space_id=zone.space_id,space_type=zone.space_type,
        level_id=level.id,proposed_counts={'theatre_seat':0},
        count_basis='Complete chair count fitted into actual supported row strips after structure, door approaches and aisles; no seating-capacity brief supplied.',
        unresolved=['Wheelchair quantity/distribution and handrail graspability, extensions and project-specific egress sizing require review.'])
    builder.room_layout_plan.spaces.append(plan)
    if layout is None or not layout.rows:
        plan.omitted[zone.space_id+'-SEATING']='No emitted sightline floor plan to support seating.'
        return
    for index,(row,front,back,top) in enumerate(layout.rows):
        next_top=layout.rows[index+1][3] if index+1<len(layout.rows) else top
        count=max(1,math.ceil(round((next_top-top)/AISLE_STEP_REVIEW_M,9)))
        tread=(abs(back-front)-ROW_PASSAGE_M)/count
        if tread<AISLE_TREAD_M-CONTACT_EPS_M:
            plan.omitted[f'{zone.space_id}-R{row.index}-TREAD']=(
                f'Aisle tread {tread:.3f} m is below the {AISLE_TREAD_M:.2f} m planning target.')
        support_candidates=_support_candidates(_builder_model(builder),top)
        support=unary_union([p for _,p in support_candidates if p is not None])
        obstacles=placement_obstacles(builder,level,top)
        region=support.intersection(box(zone.x0,zone.y0,zone.x1,zone.y1))
        if obstacles:
            region=region.difference(unary_union(obstacles))
        x=front+layout.direction*SEAT_LINE_OFFSET_M
        depth_front=x-SEAT_DEPTH_M/2
        depth_back=x+SEAT_DEPTH_M/2
        for bi,(a,b) in enumerate(layout.seat_bands):
            runs=_seat_intervals(region,depth_front,depth_back,a,b)
            if not runs:
                plan.omitted[f'{zone.space_id}-R{row.index}-B{bi}']=(
                    'Actual seating row block has no supported chair-depth strip clear of obstacles.')
            for segment,(lo,hi) in enumerate(runs):
                count=math.floor((hi-lo-SEAT_WIDTH_M)/SEAT_PITCH_M+1+1e-8)
                for ci in range(count):
                    y=(lo+hi)/2+(ci-(count-1)/2)*SEAT_PITCH_M
                    identifier=f'PRG-TSEA-{level.id}-R{row.index:02d}-B{bi}-G{segment}-S{ci:02d}'
                    parts=_seat_parts(x,y,top,layout.direction)
                    if _emit_assembly(builder,identifier,'theatre_seat','seat',parts,
                            level,zone,region,top,support_candidates,row.index):
                        plan.proposed_counts['theatre_seat'] += 1
                    else:
                        plan.omitted[identifier]='A whole-depth fitted chair failed exact assembly or support validation.'
    _emit_wheelchair_positions(builder,level,zone,layout,plan)
    _emit_aisle_handrails(builder,level,zone,layout)


def inspect_room_layouts(model) -> RoomLayoutReport:
    """Re-measure emitted bodies and complete clearances; never trust placed flags."""
    plan = getattr(model,'room_layout_plan',None)
    if plan is None:
        return RoomLayoutReport(status='unevaluated',assembly_count=0,counts_by_recipe={},
            reservation_count=0,checks_run=[],findings=[LayoutFinding(check_id='LAYOUT-PLAN',
            status='unevaluated',space_id='',detail='No room fixture/layout plan was serialized.')])
    records = _records(model)
    shapes = {item.id: _shape(group,item,model.profiles) for group,item in records
              if group.kind not in NON_OBSTACLES}
    physical = [(group,item) for group,item in records if item.id in shapes]
    index = STRtree([shapes[item.id][0] for _,item in physical])
    assemblies = defaultdict(list)
    for group,item in records:
        if getattr(item,'assembly_id',None):
            assemblies[item.assembly_id].append((group,item))
    zones = {zone.space_id:zone for zone in model.program_allocation.zones}
    findings = []
    counts = defaultdict(int)

    def finding(check,space,detail,ids=(),status='failed'):
        findings.append(LayoutFinding(check_id=check,status=status,space_id=space,
                                       element_ids=list(ids),detail=detail))

    for space in plan.spaces:
        for identifier,reason in space.omitted.items():
            finding('LAYOUT-UNPLACED',space.space_id,reason,[identifier])
        for reason in space.unresolved:
            finding('LAYOUT-SCOPE',space.space_id,reason,status='unevaluated')
    planned = {space.space_id for space in plan.spaces}
    for zone in zones.values():
        if (zone.space_id not in planned and ('restroom' in zone.space_type
                or zone.space_type in {'mechanical','mechanical_room','plant',
                                      'electrical_it','electrical','auditorium'})):
            finding('LAYOUT-MISSING-ROOM',zone.space_id,'Allocated room has no fixture or seating layout plan.')
    from .portals import approach_regions
    approaches = {level.id:approach_regions(model,level.id) for level in model.lattice.occupied}
    support_cache = {}
    def floor_candidates(z):
        if z not in support_cache:
            support_cache[z] = _support_candidates(model,z)
        return support_cache[z]

    for intent in plan.assemblies:
        actual = assemblies.get(intent.assembly_id,[])
        roles = {item.part_role:item for _,item in actual}
        missing = sorted(set(intent.required_roles)-set(roles))
        if missing:
            finding('LAYOUT-ASSEMBLY',intent.space_id,'Missing assembly parts: '+', '.join(missing),[intent.assembly_id])
            continue
        counts[intent.recipe] += 1
        zone = zones.get(intent.space_id)
        footprint_all = unary_union([shapes[item.id][0] for _,item in actual])
        if zone is None or not box(zone.x0,zone.y0,zone.x1,zone.y1).buffer(CONTACT_EPS_M).covers(footprint_all):
            finding('LAYOUT-ROOM-BOUNDARY',intent.space_id,'Complete assembly leaves its allocated room.',[intent.assembly_id])
        feet = [FurniturePart(role,roles[role].geometry,('$floor',)) for role in intent.floor_roles if role in roles]
        # Parts' actual bottom must agree with the stored floor, as well as their plan contact.
        candidates = floor_candidates(intent.floor_z_m)
        support_area = unary_union([polygon for _,polygon in candidates if polygon is not None])
        if (any(abs(_z_interval(p.geometry)[0]-intent.floor_z_m)>CONTACT_EPS_M for p in feet)
                or _support_hosts(model,feet,intent.floor_z_m,candidates) is None
                or not support_area.buffer(CONTACT_EPS_M).covers(footprint_all)):
            finding('LAYOUT-FLOOR-SUPPORT',intent.space_id,'A base/foot does not fully bear on an emitted surface at its actual elevation.',[intent.assembly_id])
        if any(footprint_all.intersection(region).area>AREA_EPS for region in approaches.get(intent.level_id,[])):
            finding('LAYOUT-DOOR-APPROACH',intent.space_id,'Assembly occupies a real doorway approach.',[intent.assembly_id])
        own = {item.id for _,item in actual}
        for hit in index.query(footprint_all,predicate='intersects'):
            group,other = physical[hit]
            if other.id in own or group.kind in NON_OBSTACLES or group.kind in {'door','entrance_door'}:
                continue
            polygon,(z0,z1) = shapes[other.id]
            # Check actual parts, not an assembly bounding box (a service void stays empty).
            if any(min(shapes[item.id][1][1],z1)-max(shapes[item.id][1][0],z0)>CONTACT_EPS_M
                   and shapes[item.id][0].intersection(polygon).area>AREA_EPS for _,item in actual):
                finding('LAYOUT-BODY-CLASH',intent.space_id,'Fixture/seat body intersects another constructed object.',[intent.assembly_id,other.id])
                break
    for reservation in plan.reservations:
        area = Polygon(reservation.polygon)
        zone = zones.get(reservation.space_id)
        if not area.is_valid or area.is_empty:
            finding('LAYOUT-CLEARANCE',reservation.space_id,'Invalid or empty reservation polygon.',[reservation.id])
            continue
        if zone is None or not box(zone.x0,zone.y0,zone.x1,zone.y1).buffer(CONTACT_EPS_M).covers(area):
            finding('LAYOUT-CLEARANCE-BOUNDARY',reservation.space_id,'Full use/service/aisle area leaves its room.',[reservation.id])
        if (reservation.purpose in {'fixture_use','equipment_service'}
                and any(area.intersection(region).area>AREA_EPS
                        for region in approaches.get(reservation.level_id,[]))):
            finding('LAYOUT-CLEARANCE-DOOR',reservation.space_id,
                    'Fixture use or equipment maintenance area occupies a doorway approach.',[reservation.id])
        supports = [polygon for _,polygon in floor_candidates(reservation.floor_z_m)
                    if polygon is not None]
        if not supports or not unary_union(supports).buffer(CONTACT_EPS_M).covers(area):
            finding('LAYOUT-CLEARANCE-SUPPORT',reservation.space_id,'Full use/service/aisle area lacks a flush continuous supporting surface.',[reservation.id])
        blockers = [item.id for hit in index.query(area,predicate='intersects')
                    for group,item in [physical[hit]] if group.kind not in NON_OBSTACLES
                    and group.kind not in {'door','entrance_door'}
                    for polygon,(z0,z1) in [shapes[item.id]]
                    if z1>reservation.floor_z_m+CONTACT_EPS_M
                    and z0<reservation.floor_z_m+reservation.clear_height_m-CONTACT_EPS_M
                    and polygon.intersection(area).area>AREA_EPS]
        if blockers:
            finding('LAYOUT-CLEARANCE-BLOCKED',reservation.space_id,'Use/service/aisle volume is occupied by constructed geometry.',[reservation.id,*blockers])
    # This is the internal theatre route only. The building egress graph separately
    # has to reach a real passable doorway from its front cross aisle.
    for space in plan.spaces:
        if space.space_type!='auditorium':
            continue
        walking=[reservation for reservation in plan.reservations
                 if reservation.space_id==space.space_id and reservation.purpose in {
                     'longitudinal_aisle','seat_row_access','cross_aisle','wheelchair_position'}]
        polygons=[Polygon(reservation.polygon) for reservation in walking]
        walk_index=STRtree(polygons)
        neighbours=defaultdict(set)
        for i,a in enumerate(polygons):
            for j in walk_index.query(a.buffer(CONTACT_EPS_M)):
                if i==j or abs(walking[i].floor_z_m-walking[j].floor_z_m)>AISLE_STEP_REVIEW_M+CONTACT_EPS_M:
                    continue
                shared=a.boundary.intersection(polygons[j].buffer(CONTACT_EPS_M)).length
                if shared>=ROW_PASSAGE_M-CONTACT_EPS_M:
                    neighbours[i].add(int(j))
        reached={i for i,reservation in enumerate(walking) if reservation.id.endswith('-CROSS-FRONT')}
        queue=list(reached)
        while queue:
            for nxt in neighbours[queue.pop()]-reached:
                reached.add(nxt)
                queue.append(nxt)
        missing=[reservation.id for i,reservation in enumerate(walking) if i not in reached]
        if missing:
            finding('LAYOUT-ROW-ACCESS',space.space_id,
                'Aisle, wheelchair bay or row passage lacks a 0.60 m contact route with steps at most 0.18 m to the front cross aisle.',missing)
    return RoomLayoutReport(status='failed' if any(f.status=='failed' for f in findings)
                            else 'unevaluated' if findings else 'passed',
        assembly_count=sum(counts.values()),counts_by_recipe=dict(counts),
        reservation_count=len(plan.reservations),findings=findings,
        checks_run=['complete_assembly','full_room_footprint','actual_floor_contact',
                    'body_collisions','door_approaches','full_clearance_support',
                    'clearance_obstacles','internal_theatre_route_contacts'])
