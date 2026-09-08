"""Public paths are reserved floor; these tests establish no code approval."""
from types import SimpleNamespace as NS

import pytest
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from backend.app.datums import Lattice, LevelDatum
from backend.app.geometry import v2
from backend.app.plan_regions import usable_region
from backend.app.program import (ROOM_SEPARATION_M, PublicCirculationPlanner,
                                 PublicCirculationPlan, PublicPath,
                                 SpaceRequirement, allocate_program, level_bands)


def lattice(width=24,depth=18,holes=()):
    def ring(polygon):
        return [v2(x,y) for x,y in list(polygon.exterior.coords)[:-1]]
    level=LevelDatum(id='L01',index=1,z=0,kind='occupied',plate=ring(box(0,0,width,depth)),
                     voids=[ring(hole) for hole in holes])
    podium=level.model_copy(update={'id':'L00','index':0,'z':-3,'kind':'podium'})
    return Lattice(levels=[podium,level],x_lines=[0,width/2,width],
                   y_lines=[0,depth/3,depth*2/3,depth],apse_nodes=[],
                   plan_x_m=width,plan_y_m=depth)


def planner(grid,targets,**kwargs):
    return PublicCirculationPlanner(grid,obstacles={1:[]},terminals={1:targets},**kwargs)


def test_public_network_routes_around_real_hole_at_full_reserved_width():
    grid=lattice(holes=[box(10,4,14,14)])
    public=planner(grid,[('STAIR-A',[(2,2)]),('STAIR-B',[(22,16)])])
    assert not public.plan.unresolved
    assert len(public.plan.paths)==2
    assert public.plan.clear_width_m==1.2
    path=LineString(public.plan.paths[1].points)
    assert path.length>Point(2,2).distance(Point(22,16))
    assert usable_region(grid.level(1)).buffer(1e-7).covers(public.reserved(1))
    assert not public.reserved(1).intersects(box(10.01,4.01,13.99,13.99))


@pytest.mark.parametrize('hole',[box(11,0,13,18),box(11,.5,13,18)])
def test_disconnected_or_half_metre_gap_is_refused(hole):
    public=planner(lattice(holes=[hole]),[('STAIR-A',[(2,2)]),('STAIR-B',[(22,16)])])
    assert 'L01:STAIR-B' in public.plan.unresolved
    assert len(public.plan.paths)==1


def test_public_connection_never_passes_through_service_room():
    room=NS(level_index=1,x0=8,y0=3,x1=16,y1=15)
    public=planner(lattice(),[('STAIR-A',[(2,9)]),('STAGE',[(22,9)])],preplaced=[room])
    assert not public.plan.unresolved
    assert LineString(public.plan.paths[-1].points).length>20
    assert public.reserved(1).intersection(box(8,3,16,15)).area<1e-7


def test_room_branch_terminates_at_a_stair_instead_of_mid_network():
    grid = lattice(width=60, depth=30)
    stair_points = {(2, 2), (58, 2)}
    public = planner(grid, [
        ('STAIR-A', [(2, 2)]),
        ('STAIR-B', [(58, 2)]),
    ])
    room = NS(level_index=1, x0=26, y0=10, x1=34, y1=20)

    path = public.room_connection(room)

    assert path is not None
    assert path[-1] in stair_points
    assert not LineString(path).intersects(box(26, 10, 34, 20))


def test_rooms_cannot_consume_connected_public_floor_or_shrink_to_fit_it():
    grid=lattice()
    public=planner(grid,[('STAIR-A',[(2,9)]),('STAIR-B',[(22,9)])])
    brief=tuple(SpaceRequirement(id=f'ROOM-{i}',space_type='loading',label='Loading',
        category='service',area_m2=area,min_dimension_m=4,level_preference='any',
        daylight='none',occupancy_id='office',reason='Test exact room demand')
        for i,area in enumerate([36,36,500]))
    allocation=allocate_program(grid,NS(value=lambda key:.2),brief,public_circulation=public)
    assert len(allocation.zones)==2
    assert [room.space_id for room in allocation.unplaced]==['ROOM-2']
    assert allocation.unplaced[0].area_required_m2==500
    assert allocation.public_circulation is public.plan
    network=unary_union([public._shape(path.points) for path in public.plan.paths])
    assert network.geom_type=='MultiLineString' and len(public.plan.paths)==4
    for zone in allocation.zones:
        assert zone.area_delivered_m2>=zone.area_required_m2-.02
        assert public.reserved(1).intersection(box(zone.x0,zone.y0,zone.x1,zone.y1)).area<1e-7
        route=next(path for path in public.plan.paths if path.target_id==zone.space_id)
        assert len(route.points)>1


def test_entrance_without_any_stair_cannot_become_a_public_route_root():
    public=planner(lattice(),[('PUBLIC-ENTRY',[(2,2)])])
    assert not public.plan.paths and public.plan.unresolved


def test_entrance_apron_and_wall_allowance_are_protected_on_real_floor():
    grid=lattice()
    apron=box(10,0,14,1.4)
    public=planner(grid,[('STAIR-A',[(2,2)]),('PUBLIC-ENTRY',[(12,.825)])],aprons={1:[apron]})
    assert not public.plan.unresolved
    reserved=public.reserved(1)
    assert reserved.covers(apron)
    assert reserved.covers(box(9.855,0,14.145,1.545))
    assert usable_region(grid.level(1)).buffer(1e-7).covers(reserved)
    assert public.plan.aprons['L01']


def test_partition_door_uses_reserved_room_approach_before_other_free_sides():
    from backend.app.compiler_v3 import _emit_partitions
    from backend.app.portals import inspect_portals
    from backend.tests.test_portals import room_builder,model
    builder,_,zone=room_builder()
    public=PublicCirculationPlan(wall_allowance_m=.145,paths=[PublicPath(
        level_id='L01',target_id=zone.space_id,points=[(2.745001,.8),(5,.8)])])
    allocation=NS(zones=[zone],public_circulation=public)
    _emit_partitions(builder,allocation,True)
    report=inspect_portals(model(*builder.groups.values()))
    assert len(report.portals)==1
    assert report.portals[0].passable
    assert report.portals[0].center==pytest.approx((2,.8))


def test_room_clearance_edge_splits_the_band_at_the_floor_actually_removed():
    grid = lattice()
    room = NS(level_index=1, x0=0, y0=6, x1=4, y1=12)
    public = planner(grid, [('STAIR-A', [(20, 3)])], preplaced=[room])
    room_with_clearance = box(room.x0, room.y0, room.x1, room.y1).buffer(
        public.room_separation_m, join_style='mitre')
    remaining = usable_region(grid.level(1)).difference(room_with_clearance)
    bands = level_bands(
        grid.level(1), grid, region=remaining, split_y=public.split_y(1))

    assert public.room_separation_m > ROOM_SEPARATION_M
    assert public.room_separation_m >= (
        public.plan.clear_width_m + 2 * public.plan.wall_allowance_m)
    assert 6 - public.room_separation_m in public.split_y(1)
    assert 12 + public.room_separation_m in public.split_y(1)
    clear_bands = [band for band in bands
                   if band.y1 <= 6 - public.room_separation_m + 1.0e-7]
    assert sum(band.area for band in clear_bands) == pytest.approx(
        24 * (6 - public.room_separation_m))
    assert all(band.x0 == pytest.approx(0)
               and band.x1 == pytest.approx(24)
               for band in clear_bands)
