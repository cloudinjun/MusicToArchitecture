"""Located, complete furniture assemblies; dimensions are presentation conventions.

The compiler chooses locations from allocated zones. This module only resolves each
location into named parts. It does not invent a new placement, structural capacity, or
print thickness. Root IDs survive and every child carries an assembly/role identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .geometry import BoxGeometry, v3
from .mesh_primitives import box_mesh


@dataclass(frozen=True)
class FurniturePart:
    role: str
    geometry: BoxGeometry
    support_roles: tuple[str, ...]


REQUIRED_ROLES = {
    'desk': frozenset({'top', 'leg_0', 'leg_1', 'leg_2', 'leg_3'}),
    'seat': frozenset({'seat', 'back', 'leg_0', 'leg_1', 'leg_2', 'leg_3'}),
    'shelving_run': frozenset({*(f'upright_{i}' for i in range(4)),
                              *(f'shelf_{i}' for i in range(6))}),
}
ROOT_ROLES = {'desk': 'top', 'seat': 'seat', 'shelving_run': 'shelf_0'}


def furniture_parts(kind: str, x: float, y: float, floor_z: float,
                    width: float, depth: float, *, facing: int = 1) -> list[FurniturePart]:
    if kind not in REQUIRED_ROLES:
        raise ValueError(f'No furniture recipe for {kind}')
    if not all(math.isfinite(v) for v in (x,y,floor_z,width,depth)) or min(width,depth) < .2:
        raise ValueError('Furniture coordinates must be finite and its footprint usable')
    if facing not in (-1,1):
        raise ValueError('Seat facing must be -1 or 1')
    parts = []
    def add(role, dx,dy,base,w,d,h,supports):
        parts.append(FurniturePart(role, BoxGeometry(
            center=v3(x+dx,y+dy,floor_z+base+h/2),size=v3(w,d,h)),tuple(supports)))
    if kind in ('desk','seat'):
        height,thickness,leg = (.75,.06,.06) if kind == 'desk' else (.45,.04,.035)
        legs = tuple(f'leg_{i}' for i in range(4))
        for i,(sx,sy) in enumerate(((-1,-1),(1,-1),(1,1),(-1,1))):
            add(legs[i],sx*(width/2-leg),sy*(depth/2-leg),0,
                leg,leg,height-thickness,('$floor',))
        root = ROOT_ROLES[kind]
        add(root,0,0,height-thickness,width,depth,thickness,legs)
        if kind == 'seat':
            add('back',0,facing*(depth/2-.02),height,width,.04,.36,('seat',))
    else:
        height,board = 2.1,.035
        uprights = tuple(f'upright_{i}' for i in range(4))
        for i,role in enumerate(uprights):
            add(role,-width/2+board/2+i*(width-board)/3,0,0,
                board,depth,height,('$floor',))
        # Intermediate uprights pass through the shelf, an intentional cabinet joint.
        for i in range(6):
            add(f'shelf_{i}',0,0,i*(height-board)/5,width,depth,board,uprights)
    return parts


def footprint(parts: list[FurniturePart]):
    return unary_union([Polygon([(x,y) for x,y,_ in box_mesh(p.geometry.model_dump())[0][:4]])
                        for p in parts])


def usable_floor(level, zone, forbidden=()):
    plate = Polygon([(p.x,p.y) for p in level.plate])
    cuts = [Polygon([(p.x,p.y) for p in ring]) for ring in level.voids]
    if not plate.is_valid or any(not cut.is_valid for cut in cuts):
        raise ValueError('Cannot place furniture on an invalid floor boundary')
    # Voids may overlap or meet the edge: they are subtraction regions, not
    # necessarily strictly nested polygon holes. Match plan_regions.extrusions.
    if cuts:
        plate = plate.difference(unary_union(cuts))
    region = plate.intersection(box(zone.x0,zone.y0,zone.x1,zone.y1))
    if forbidden:
        region = region.difference(unary_union(forbidden))
    # Keep a convention clearance to zone edges; never shrink program areas.
    return region.buffer(-.05)


def emit_furniture(builder, root_id: str, kind: str, parts: list[FurniturePart],
                   level, zone, region) -> bool:
    if not region.covers(footprint(parts)):
        return False
    root_role = ROOT_ROLES[kind]
    ids = {p.role: root_id if p.role == root_role else f'{root_id}-PART-{p.role}' for p in parts}
    # A floor may have been decomposed into multiple islands around actual core
    # openings. Choose contact from its real solids, never the first slab ID.
    from .geometry_review import _polygon, _z_interval
    floor_candidates = []
    for group in builder.groups.values():
        if group.kind not in ('floor_slab', 'podium_slab'):
            continue
        for item in group.instances:
            if item.level_id != level.id:
                continue
            polygon, vertical = _polygon(item.geometry), _z_interval(item.geometry)
            if polygon is not None and vertical and abs(vertical[1] - level.z) <= 1e-4:
                floor_candidates.append((item.id, polygon))
    floor_hosts = {}
    for part in parts:
        if '$floor' not in part.support_roles:
            continue
        base = footprint([part])
        hosts = [(name, polygon) for name, polygon in floor_candidates
                 if polygon.intersection(base).area > 1e-9]
        if not hosts or not unary_union([polygon for _, polygon in hosts]).buffer(1e-5).covers(base):
            return False
        floor_hosts[part.role] = [name for name, _ in hosts]
    for part in parts:
        hosts = [host for role in part.support_roles
                 for host in (floor_hosts[part.role] if role == '$floor' else [ids[role]])]
        builder.add(ids[part.role],kind,'program','furniture',part.geometry,'furn',
                    category=zone.category,program=zone.space_type,level_id=level.id,
                    lattice_index={'level':level.index,'band':zone.band_index},
                    datum_refs=['bay_x_m','bay_y_m','level_count','circulation_allowance',
                                'cantilever_m','plate_step_m','plate_rotation_deg','apse_radius_m'],
                    supports=hosts,assembly_id=root_id,part_role=part.role,
                    rule_refs=['MTA-FURNITURE-ASSEMBLY-001'],
                    reason=f'{kind} assembly, {part.role}; architectural convention, not sized by calculation.')
    return True
