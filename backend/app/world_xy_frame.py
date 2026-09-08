"""Physical boundary stations alongside, never inserted into, the World XY grid.

This adapter closes directly grounded perimeter spans. Transfer-required stations
remain in the serialized plan; it does not invent a load path through a void.
Sections reused from the frame are explicitly convention-sized here, pending a
station-level load calculation including the roof and transfer reactions.
"""
from __future__ import annotations

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from .geometry import v3
from .models_v3 import BoxGeometry
from .world_xy_grid import (
    ColumnFootprint, GridBounds, ProgramVolumeLevelFootprint, plan_world_xy_columns,
)


def emit_boundary_columns(b, column_profile, material, core_boxes, openings):
    lattice = b.lattice
    grid = lattice.world_xy_grid
    if grid is None:
        return []
    levels = lattice.levels[1:]
    shapes = {level.id: Polygon([(p.x,p.y) for p in level.plate],
                               holes=[[(p.x,p.y) for p in ring] for ring in level.voids])
              for level in levels}
    extent = unary_union(list(shapes.values())).bounds
    profile = b.profiles[column_profile]
    # The square envelope covers either orientation of the actual catalogue shape.
    breadth = max(profile.width_m, profile.depth_m)
    footprint = ColumnFootprint(breadth, breadth)
    plan = plan_world_xy_columns(grid,
        [ProgramVolumeLevelFootprint(level.id, shapes[level.id], level.index) for level in levels],
        GridBounds(*extent), footprint=footprint)
    lattice.world_xy_column_plan = plan
    available = {level.id: shapes[level.id].difference(unary_union(
                    [box(*r) for r in [*core_boxes, *openings(level.id)]]))
                 for level in levels}
    from .core_access import column_access_regions
    keepouts = column_access_regions(lattice,b.datums,b.approach)
    for level in levels:
        available[level.id] = available[level.id].difference(
            unary_union(keepouts[level.id]))
    # The registry contains floor-specific discoveries. One XY axis owns one
    # physical stack even when several levels discover the same boundary station.
    def key(point):
        return tuple(round(float(v), 7) for v in point)

    existing = {key((instance.geometry.path[0].x,instance.geometry.path[0].y))
                for group in b.groups.values() if group.kind in ('column','piloti_column')
                for instance in group.instances}
    stations = {}
    for index, candidate in enumerate(plan.candidates):
        if candidate.grid_source != 'grid_node' and candidate.fits_whole_footprint:
            stations.setdefault(key(candidate.point_xy), index)
    # A boundary discovery close to an existing grid column must not create two
    # intersecting physical posts. Preserve the independent regular nodes first.
    occupied_posts = unary_union([footprint.geometry_at(point) for point in existing])
    def continuous_height(index):
        body = footprint.geometry_at(plan.candidates[index].point_xy)
        height = 0
        for level in levels:
            if not available[level.id].covers(body):
                break
            height += 1
        return height
    ordered_stations = sorted(stations.items(), key=lambda item:(-continuous_height(item[1]),item[1]))
    count_columns = 0
    suppressed = 0
    for point, index in ordered_stations:
        if point in existing:
            continue
        candidate = plan.candidates[index]
        x,y = candidate.point_xy
        body = footprint.geometry_at((x,y))
        if body.intersection(occupied_posts).area > 1e-7:
            suppressed += 1
            continue
        lower, host = lattice.levels[0], None
        for upper in levels:
            if not available[upper.id].covers(body):
                break
            # Actual successive floor support, not the candidate's descriptive
            # status, authorizes this continuous segment.
            if host is None:
                host = f'STR-WXB-FDN-{index:04d}'
                b.add(host,'footing','structure','foundations',
                    BoxGeometry(center=v3(x,y,lower.z-.45), size=v3(1.6,1.6,.9)),
                    'concrete', level_id=lower.id,
                    lattice_index={'boundary_station':index,'level':lower.index},
                    datum_refs=['bay_x_m','bay_y_m'],
                    rule_refs=['STR-LOAD-PATH-FOUNDATION-001'],
                    reason='Pad below a registered World XY boundary station; soil and pad capacity unverified.')
            identifier = f'STR-WXB-COL-{index:04d}-{lower.id}'
            b.add(identifier,'piloti_column' if lower.index == 0 else 'column',
                'structure','columns',b.member([v3(x,y,lower.z),v3(x,y,upper.z)],column_profile),
                material,level_id=lower.id,
                lattice_index={'boundary_station':index,'level':lower.index},
                datum_refs=['bay_x_m','bay_y_m','floor_to_floor_m'], supports=[host],
                section_id=profile.id, sizing_status='architectural_convention',
                rule_refs=['STF-INV-01','WORLD-XY-BOUNDARY-STATION'],
                reason=f'Column from station {candidate.id}; full footprint on every intervening floor. '
                       'Catalogue profile borrowed from frame; station loads, lateral and transfer sizing unverified.')
            host, lower = identifier, upper
            count_columns += 1
        if host is not None:
            occupied_posts = unary_union([occupied_posts,body])

    transfers = sum(c.support_status == 'transfer_required' for c in plan.candidates)
    return [f'World XY boundary frame: {count_columns} column segments emitted '
            f'from the serialized station registry without re-phasing the grid. {transfers} candidate stations '
            f'require transfer by floor containment; {suppressed} colliding boundary discoveries were suppressed. '
            'No unsupported stack was emitted. Boundary sections are '
            'catalogue-based architectural conventions, not station-load-sized members. Hall transfer endpoints, '
            'remaining unsupported perimeter portions, capacity and connections still require resolution.']


def emit_boundary_spans(b, level, beam_profile, material, core_boxes, openings):
    """Complete a storey's spans after regular beams, before its slabs claim hosts."""
    lattice = b.lattice
    plan = lattice.world_xy_column_plan
    if plan is None:
        return
    grid = lattice.world_xy_grid
    available = {level.id: Polygon([(p.x,p.y) for p in level.plate],
                 holes=[[(p.x,p.y) for p in ring] for ring in level.voids]).difference(
                 unary_union([box(*r) for r in [*core_boxes,*openings(level.id)]]))}
    existing_beams = unary_union([
        LineString([(p.x,p.y) for p in instance.geometry.path])
        for group in b.groups.values() if group.kind == 'primary_beam'
        for instance in group.instances if instance.level_id == level.id])
    # The same source grid lines now carry regular nodes and inboard boundary
    # endpoints. Join only adjacent real column tops with a complete in-floor beam.
    columns = [instance for group in b.groups.values() if group.kind in ('column','piloti_column')
               for instance in group.instances]
    beam = b.profiles[beam_profile]
    slab_t = b.datums.value('slab_thickness_m')
    count_beams = 0
    lower = lattice.levels[level.index-1]
    if level.z-lower.z < slab_t+beam.depth_m:
        return  # Grade slab has no exposed beam storey below it.
    tops = [c for c in columns if abs(c.geometry.path[-1].z-level.z) < 1e-7]
    for axis in ('x','y'):
        for line_index in grid.index_range(axis, plan.bounds):
            coordinate = grid.coordinate(axis,line_index)
            points = [c for c in tops if abs(
                (c.geometry.path[-1].x if axis == 'x' else c.geometry.path[-1].y)-coordinate) < 1e-7]
            points.sort(key=lambda c:c.geometry.path[-1].y if axis == 'x' else c.geometry.path[-1].x)
            for first,second in zip(points,points[1:]):
                if not any('boundary_station' in c.lattice_index for c in (first,second)):
                    continue  # Existing regular-grid emitter owns this bay.
                a,c = first.geometry.path[-1],second.geometry.path[-1]
                line = LineString([(a.x,a.y),(c.x,c.y)])
                if line.difference(existing_beams.buffer(1e-5)).length < 1e-5:
                    continue  # A real regular beam already owns this span.
                if line.length < beam.width_m or not available[level.id].covers(
                        line.buffer(beam.width_m/2,cap_style=2,join_style=2)):
                    continue
                z = level.z-slab_t-beam.depth_m/2
                index = {'level':level.index,'world_axis':0 if axis=='x' else 1,
                         'world_line':line_index,'segment':count_beams}
                b.add(f'STR-WXB-BM-{level.id}-{count_beams:04d}', 'primary_beam','structure','beams',
                    b.member([v3(a.x,a.y,z),v3(c.x,c.y,z)],beam_profile),material,
                    level_id=level.id,lattice_index=index, supports=[first.id,second.id],
                    datum_refs=['bay_x_m','bay_y_m','slab_thickness_m'],
                    section_id=beam.id,sizing_status='architectural_convention',
                    rule_refs=['WORLD-XY-BOUNDARY-STATION'],
                    reason='Full-width in-floor span along the independent grid to a registered boundary station. '
                           'Both columns exist; station-level load and connection sizing remain unverified.')
                count_beams += 1
