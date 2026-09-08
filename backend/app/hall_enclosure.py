"""Registered indoor hall cap and its gravity framing.

The roof is the hall footprint minus the actual slab at the cap datum. Its
support grid replaces the coincident floor grid, preserving the floor load while
adding roof D/Lr and the actual selected framing weight. No code approval is
implied: metal deck span, weather joints, lateral action and connections need review.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union
from shapely.affinity import rotate

from .geometry import v2, v3
from .loads import LoadCase, composite_steel_deck, flat_roof_assembly, OCCUPANCY_LIVE
from .registry import catalogue, profile_for
from .sizing import SelectionResult, select_beam
from .hall_stations import HallSupportGrid, hall_axes, register_hall_grid, volume_section


class HallEnclosureReport(BaseModel):
    status: Literal['failed', 'review_required'] = 'failed'
    level_id: str | None = None
    roof_bottom_z: float | None = None
    clear_top_z: float | None = None
    roof_area_m2: float = 0.
    support_grid: HallSupportGrid | None = None
    roof_dead_kn: float = 0.
    roof_live_kn: float = 0.
    framing_dead_kn: float = 0.
    uncovered_area_m2: float | None = None
    open_wall_head_length_m: float | None = None
    primary: SelectionResult | None = None
    secondary: SelectionResult | None = None
    roof_ids: list[str] = Field(default_factory=list)
    framing_ids: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    unevaluated: list[str] = Field(default_factory=lambda: [
        'Metal deck local span, fasteners, diaphragm action and roof edge cantilevers require product/detail design.',
        'Roof falls, rain ponding, snow drift, drainage, waterproof joints and wall head movement require review.',
        'Wall self-weight remains on the existing base support; wall stability, anchorage and fire/acoustic assemblies require review.',
    ])


@dataclass
class HallGeometry:
    footprint: object
    missing: object
    level: object
    roof_bottom_z: float
    clear_top_z: float
    x_indices: list[int]
    y_indices: list[int]
    roof_id: str = 'ENV-HALL-ROOF'


def slab_polygon(level):
    result = Polygon([(p.x, p.y) for p in level.plate])
    for hole in level.voids:
        result = result.difference(Polygon([(p.x, p.y) for p in hole]))
    return result


def enclosure_geometry(lattice, carve, slab_t):
    """Return the common enclosure interface, or None if no registered cap fits."""
    if not hasattr(carve, 'clear_house_m'):
        return None
    from .transfer_structure import MIN_TRUSS_DEPTH_M
    from .archetypes import STAGE_RISE_M
    sections = catalogue('steel_w_shape') + catalogue('steel_hss_square')
    envelope = max(max(s.depth_mm, s.width_mm) for s in sections) / 1000.
    clear = lattice.occupied[0].z + max(carve.clear_house_m, STAGE_RISE_M+carve.clear_stage_m)
    level = next((lv for lv in lattice.levels
                  if lv.z - slab_t - envelope - clear >= MIN_TRUSS_DEPTH_M), None)
    if level is None:
        return None
    footprint = unary_union([box(*carve.house), box(*carve.stage)])
    # A roof reaches the outside face of the existing 290 mm maximum hall wall.
    cap = footprint.buffer(.145, join_style=2)
    grid = register_hall_grid(lattice, footprint,
        max(s.width_mm for s in catalogue('steel_hss_square'))/1000.)
    if grid is not None:
        lattice.hall_support_grid = grid
        # The hall cap belongs to its enclosing volume below the cap datum.
        # A wall-face allowance cannot extend the roof outside that authority.
        cap = cap.intersection(volume_section(lattice, level.z-slab_t/2))
        return HallGeometry(footprint, cap.difference(slab_polygon(level)), level,
            level.z-slab_t, clear, grid.indices('x'), grid.indices('y'))
    x0, y0, x1, y1 = footprint.bounds
    west = [i for i, x in enumerate(lattice.x_lines) if x <= x0 + .002]
    east = [i for i, x in enumerate(lattice.x_lines) if x >= x1 - .002]
    south = [i for i, y in enumerate(lattice.y_lines) if y <= y0 + .002]
    north = [i for i, y in enumerate(lattice.y_lines) if y >= y1 - .002]
    if not all((west, east, south, north)):
        return None
    return HallGeometry(footprint, cap.difference(slab_polygon(level)), level,
        level.z - slab_t, clear, list(range(max(west), min(east) + 1)),
        list(range(max(south), min(north) + 1)))


def prepare_hall(b, occupancy, carve):
    geometry = enclosure_geometry(b.lattice, carve, b.datums.value('slab_thickness_m'))
    if geometry is None:
        return None
    report = HallEnclosureReport(level_id=geometry.level.id,
        roof_bottom_z=geometry.roof_bottom_z, clear_top_z=geometry.clear_top_z,
        roof_area_m2=geometry.missing.area,
        support_grid=getattr(b.lattice, 'hall_support_grid', None))
    b.hall_geometry, b.hall_enclosure = geometry, report
    xl, yl = hall_axes(b)
    bx = max(xl[c] - xl[a] for a, c in zip(geometry.x_indices, geometry.x_indices[1:]))
    by = max(yl[c] - yl[a] for a, c in zip(geometry.y_indices, geometry.y_indices[1:]))
    spacing = b.datums.value('joist_spacing_m')
    # Both layers conservatively use the greater retained-floor/roof area load.
    # 1.4/1.2 envelopes the dead-only combination in the existing beam checker.
    dead = max(composite_steel_deck().superimposed_dead_kpa(),
               flat_roof_assembly().superimposed_dead_kpa()) * 1.4 / 1.2
    live = max(occupancy.live_kpa, OCCUPANCY_LIVE['roof_ordinary'].live_kpa)
    sections = catalogue('steel_w_shape')
    report.secondary = select_beam('STR-HALL-JST', by, spacing,
        LoadCase(dead_kpa=dead, live_kpa=live), sections, unbraced_length_m=by)
    if not report.secondary.selected:
        report.findings.append('No catalogue secondary member carries the complete retained floor/roof envelope.')
        return geometry
    secondary = next(s for s in sections if s.id == report.secondary.check.section_id)
    report.primary = select_beam('STR-HALL-BMX', bx, by,
        LoadCase(dead_kpa=dead + secondary.self_weight_kn_m / spacing * 1.4 / 1.2,
                 live_kpa=live), sections, role='girder', unbraced_length_m=bx)
    if not report.primary.selected:
        report.findings.append('No catalogue primary member carries the complete retained floor/roof envelope.')
        return geometry
    primary = next(s for s in sections if s.id == report.primary.check.section_id)
    b.hall_primary_z = geometry.roof_bottom_z - secondary.depth_mm / 1000. - primary.depth_mm / 2000.
    b.hall_secondary_z = geometry.roof_bottom_z - secondary.depth_mm / 2000.
    # Store actual service reactions at each support node, not a roof-wide lump.
    reactions = {(xi, yj): [0., 0.] for xi in geometry.x_indices for yj in geometry.y_indices}
    # The wall-face cap can project beyond any of the four registered grid edges.
    # Read its actual bounds; a fixed east-only strip left west edge load behind.
    roof_bounds = geometry.missing.bounds if not geometry.missing.is_empty else (
        xl[geometry.x_indices[0]], yl[geometry.y_indices[0]],
        xl[geometry.x_indices[-1]], yl[geometry.y_indices[-1]])
    for a, c in zip(geometry.x_indices, geometry.x_indices[1:]):
        xa, xc = xl[a], xl[c]
        divisions = max(1, math.ceil((xc - xa) / spacing))
        for j in geometry.y_indices:
            # Each real primary's weight is carried by its two end nodes.
            weight = primary.self_weight_kn_m * (xc - xa)
            for xi in (a, c): reactions[xi, j][0] += weight / 2
        for ja, jc in zip(geometry.y_indices, geometry.y_indices[1:]):
            ya, yc = yl[ja], yl[jc]
            # Roof area integrated by bilinear simple-span reaction influence.
            # Polygon first moments are exact for the x/y-linear factors used
            # in each strip; a fine deterministic split handles their product.
            for sub in range(divisions):
                left = xa + (xc - xa) * sub / divisions
                right = xa + (xc - xa) * (sub + 1) / divisions
                if a == geometry.x_indices[0] and sub == 0:
                    left = min(left, roof_bounds[0])
                if c == geometry.x_indices[-1] and sub == divisions - 1:
                    right = max(right, roof_bounds[2])
                bottom = min(ya, roof_bounds[1]) if ja == geometry.y_indices[0] else ya
                top = max(yc, roof_bounds[3]) if jc == geometry.y_indices[-1] else yc
                region = geometry.missing.intersection(box(left, bottom, right, top))
                if region.area:
                    # Use tributary load centroid to preserve vertical force and
                    # both first moments; mixed xy moment is not a global balance.
                    q = region.centroid
                    # Linear influence extends over the small deck overhang.
                    # Clamping moves its load onto the support and loses moment.
                    fx = (q.x-xa)/(xc-xa)
                    fy = (q.y-ya)/(yc-ya)
                    for xi, wx in ((a,1-fx),(c,fx)):
                        for yj, wy in ((ja,1-fy),(jc,fy)):
                            reactions[xi,yj][0] += region.area * wx * wy * flat_roof_assembly().superimposed_dead_kpa()
                            reactions[xi,yj][1] += region.area * wx * wy * OCCUPANCY_LIVE['roof_ordinary'].live_kpa
            # Include both boundary secondaries. Shared lines are emitted once;
            # their weight is half allocated from each adjacent bay.
            for sub in range(divisions + 1):
                fraction = sub / divisions
                share = .5 if sub in (0,divisions) else 1.
                if (a == geometry.x_indices[0] and sub == 0) or (c == geometry.x_indices[-1] and sub == divisions): share = 1.
                weight = secondary.self_weight_kn_m * (yc-ya) * share
                for xi, wx in ((a,1-fraction),(c,fraction)):
                    for yj in (ja,jc): reactions[xi,yj][0] += weight * wx / 2
    b.hall_reactions = reactions
    report.roof_dead_kn = geometry.missing.area * flat_roof_assembly().superimposed_dead_kpa()
    report.roof_live_kn = geometry.missing.area * OCCUPANCY_LIVE['roof_ordinary'].live_kpa
    report.framing_dead_kn = sum(v[0] for v in reactions.values()) - report.roof_dead_kn
    if abs(sum(v[1] for v in reactions.values()) - report.roof_live_kn) > .01:
        report.findings.append('Roof reaction integration does not cover the complete roof area.')
    return geometry


def replaces_framing(b, level, direction, xi, yj):
    g = getattr(b, 'hall_geometry', None)
    report = getattr(b, 'transfer_structure', None)
    if g is None or report is None or report.status != 'review_required' or level.id != g.level.id:
        return False
    if direction == 'BMX':
        return xi in g.x_indices[:-1] and yj in g.y_indices
    if direction == 'BMY':
        return xi in g.x_indices and yj in g.y_indices[:-1]
    return xi in g.x_indices[:-1] and yj in g.y_indices[:-1]


def roof_bearings(piece, bottom_z, members, profiles):
    """Measure actual horizontal beam bodies at the deck underside, not axes."""
    from .physical_geometry import physical_projection
    result = []
    for identifier,geometry in members.items():
        body = physical_projection(geometry,profiles=profiles)
        if abs(body.z_top-bottom_z) <= 1e-5 and piece.intersection(body.footprint).area > 1e-8:
            result.append(identifier)
    return result


def emit_hall(b):
    """Emit the activated roof and replacement grid, all at actual bearing heights."""
    g = getattr(b, 'hall_geometry', None)
    transfer = getattr(b, 'transfer_structure', None)
    if g is None or transfer is None or transfer.status != 'review_required': return
    from .transfer_structure import column_id, post_id
    report = b.hall_enclosure
    xl, yl = hall_axes(b)
    storey = b.lattice.levels[g.level.index - 1]
    frames = {f.x_index:f for f in transfer.frames}
    secondary_members={}
    def support(xi,yj):
        f = frames.get(xi)
        return post_id(f,yj) if f and yj in f.y_indices[1:-1] else column_id(xi,yj,g.level.index-1,b.lattice)
    def member(identifier,kind,points,choice,supports):
        if any(s not in b.element_ids for s in supports):
            raise ValueError(f'Hall framing {identifier} has an absent support: {supports}')
        geometry = b.member(points,b.profile(profile_for(choice.check.section_id)))
        b.add(identifier,kind,'structure','beams',geometry,
            'steel_white',level_id=storey.id,datum_refs=['bay_x_m','bay_y_m','joist_spacing_m','slab_thickness_m'],
            lattice_index={'hall_support': 1, 'level': storey.index},
            supports=supports,section_id=choice.check.section_id,sizing_status='sized_by_calculation',
            utilisation=choice.check.max_ratio,governing_check=choice.check.governing,
            rule_refs=['STR-HALL-GRAVITY-001'],reason='Catalogue gravity envelope of retained floor and new roof; actual selected framing self weight reaches the reaction piers. Connections and lateral action require review.')
        report.framing_ids.append(identifier)
        return geometry
    primary_ids={}
    for a,c in zip(g.x_indices,g.x_indices[1:]):
        for j in g.y_indices:
            identifier=f'STR-BMX-X{a:02d}-Y{j:02d}-{g.level.id}'
            member(identifier,'primary_beam',[v3(xl[a],yl[j],b.hall_primary_z),v3(xl[c],yl[j],b.hall_primary_z)],
                   report.primary,[support(a,j),support(c,j)])
            primary_ids[a,j]=identifier
    seen=set()
    for a,c in zip(g.x_indices,g.x_indices[1:]):
        divisions=max(1,math.ceil((xl[c]-xl[a])/b.datums.value('joist_spacing_m')))
        for sub in range(divisions+1):
            x=xl[a]+(xl[c]-xl[a])*sub/divisions
            for ja,jc in zip(g.y_indices,g.y_indices[1:]):
                key=(round(x,6),ja)
                if key in seen: continue
                seen.add(key)
                identifier=f'STR-HALL-JST-X{a:02d}-S{sub:02d}-Y{ja:02d}-{g.level.id}'
                geometry=member(identifier,'secondary_joist',[v3(x,yl[ja],b.hall_secondary_z),v3(x,yl[jc],b.hall_secondary_z)],
                    report.secondary,[primary_ids[a,ja],primary_ids[a,jc]])
                secondary_members[identifier]=geometry
    parts=[g.missing] if g.missing.geom_type=='Polygon' else list(g.missing.geoms)
    for i,poly in enumerate(parts):
        identifier=g.roof_id if i==0 else f'{g.roof_id}-P{i:02d}'
        from .plan_regions import extrusions
        geometries=extrusions(
            [v2(*p) for p in list(poly.exterior.coords)[:-1]],
            [[v2(*p) for p in list(r.coords)[:-1]] for r in poly.interiors],
            g.roof_bottom_z,g.level.z)
        for n,geometry in enumerate(geometries):
            part_id=identifier if n==0 else f'{identifier}-S{n:02d}'
            piece=Polygon([(v.x,v.y) for v in geometry.boundary])
            supports=roof_bearings(piece,g.roof_bottom_z,secondary_members,b.profiles)
            if not supports:
                raise ValueError(f'Hall roof {part_id} has no real secondary bearing.')
            b.add(part_id,'roof_deck','envelope','hall_enclosure',geometry,'white',level_id=g.level.id,
                datum_refs=['slab_thickness_m','floor_to_floor_m'],supports=supports,
                rule_refs=['ENV-HALL-CLOSURE-001'],reason='Indoor hall cap is the actual hall-to-slab difference at the registered transfer floor. Gravity reactions include the stated flat-roof assembly and ordinary roof live load; drainage, deck product and joints require review.')
            report.roof_ids.append(part_id)
    report.status='review_required'


def inspect_hall(b):
    """Measure emitted cap coverage and wall heads; no semantic roof shortcut."""
    g=getattr(b,'hall_geometry',None)
    report=getattr(b,'hall_enclosure',None)
    if g is None or report is None: return
    covers,heads=[],[]
    for group in b.groups.values():
        for instance in group.instances:
            shape=instance.geometry
            if shape.type=='extrusion':
                poly=Polygon([(p.x,p.y) for p in shape.boundary],
                    [[(p.x,p.y) for p in ring] for ring in shape.holes])
                if group.kind in {'roof_deck','floor_slab'} and abs(shape.z_base-g.roof_bottom_z)<.002:
                    covers.append(poly)
                if group.kind in {'partition','partition_wall','partition_head'} and shape.z_base<g.roof_bottom_z-.002<=shape.z_top:
                    heads.append(poly)
            elif shape.type=='box' and group.kind in {'partition','partition_wall','partition_head','wall'}:
                if shape.center.z-shape.size.z/2 < g.roof_bottom_z-.002 <= shape.center.z+shape.size.z/2:
                    poly=box(shape.center.x-shape.size.x/2,shape.center.y-shape.size.y/2,
                             shape.center.x+shape.size.x/2,shape.center.y+shape.size.y/2)
                    heads.append(rotate(poly,shape.rotation_z,origin=(shape.center.x,shape.center.y)))
    report.uncovered_area_m2=g.footprint.difference(unary_union(covers)).area
    report.open_wall_head_length_m=g.footprint.boundary.difference(unary_union(heads).buffer(.002)).length
    if report.uncovered_area_m2>.01:
        report.findings.append(f'Emitted hall cap leaves {report.uncovered_area_m2:.3f} m2 uncovered.')
    if report.open_wall_head_length_m>.02:
        report.findings.append(f'Emitted outer wall heads leave {report.open_wall_head_length_m:.3f} m open at the cap underside.')
    if report.findings: report.status='failed'
