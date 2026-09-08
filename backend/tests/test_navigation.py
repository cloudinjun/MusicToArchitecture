from types import SimpleNamespace as NS
import math
import pytest

from shapely.geometry import LineString, Polygon, box

from backend.app.geometry import BoxGeometry, ExtrusionGeometry, v2, v3
from backend.app.navigation import WalkMesh, SteppedWalkMesh, build_navigation, free_floor


def element(name, kind, geometry):
    return NS(id=name, kind=kind, level_id='L01', geometry=geometry,
              semantic_layer='structure', thickness_m=None)


def fixture(extra=(), holes=()):
    floor = ExtrusionGeometry(boundary=[v2(0,0),v2(12,0),v2(12,10),v2(0,10)],
        holes=[[v2(x,y) for x,y in list(hole.exterior.coords)[:-1]] for hole in holes],
        z_base=-.2, z_top=0)
    level = NS(id='L01',z=0)
    model = NS(elements=[element('slab','floor_slab',floor),*extra], profiles={},
        lattice=NS(levels=[level]),program_allocation=NS(zones=[
        NS(level_id='L01',space_id='ROOM',x0=1,y0=1,x1=3,y1=4)]))
    nodes = [NS(id='SP-L01-ROOM',kind='space',level_id='L01',x=2,y=2.5),
             NS(id='EXIT',kind='exit_stair',level_id='L01',x=10,y=2.5)]
    return model,level,nodes


def obstacle(name,x,y,w,d,h=3):
    return element(name,'partition',BoxGeometry(center=v3(x,y,h/2),size=v3(w,d,h)))


def test_actual_detour_around_partition_and_hole():
    model,level,_ = fixture([obstacle('wall',6,4,1,8)])
    domain,unknown = free_floor(model,level)
    assert not unknown
    path = WalkMesh(domain).route((2,2.5),(10,2.5))
    assert path is not None and len(path)>2
    assert LineString(path).length>8
    assert all(domain.covers(LineString([a,b])) for a,b in zip(path,path[1:]))
    crossing=LineString(path).intersection(LineString([(6,0),(6,10)]))
    assert crossing.y>8


def test_sealed_room_never_gets_straight_line_exit_edge():
    model,_,nodes = fixture([obstacle('wall',6,5,1,10)])
    report=build_navigation(model,nodes)
    assert report.samples and not report.routes
    assert any(f.id=='NAV-UNREACHABLE' for f in report.findings)


def test_floor_hole_separates_islands_even_when_centroids_look_near():
    model,level,_=fixture(holes=[box(5,0,7,10)])
    domain,_=free_floor(model,level)
    assert WalkMesh(domain).route((2,2),(10,2)) is None


def test_site_podium_is_still_real_walking_support():
    model,level,_=fixture()
    model.elements[0].kind='podium_slab'
    model.elements[0].semantic_layer='site'
    domain,unknown=free_floor(model,level)
    assert not unknown and WalkMesh(domain).route((2,2),(10,2)) is not None


def test_body_does_not_fit_a_point_or_narrow_gap():
    domain=box(0,0,10,10).difference(box(4,0,6,4.8).union(box(4,5.2,6,10)))
    assert WalkMesh(domain.buffer(-.3,join_style='mitre')).route((2,5),(8,5)) is None


def test_overhead_and_floor_elevations_control_obstruction():
    beam=element('beam','partition',BoxGeometry(center=v3(6,5,3),size=v3(1,10,.5)))
    model,level,_=fixture([beam])
    domain,_=free_floor(model,level)
    assert WalkMesh(domain).route((2,2),(10,2)) is not None
    level.z=.1
    domain,unknown=free_floor(model,level)
    assert domain.is_empty and unknown


def test_unknown_obstacle_does_not_silently_disappear():
    unknown=element('unknown','column',None)
    unknown.level_id='L00'  # A column's registration floor is not its full extent.
    model,_,nodes=fixture([unknown])
    report=build_navigation(model,nodes)
    assert not report.routes
    assert any(f.id=='NAV-GEOMETRY-UNKNOWN' for f in report.findings)


def test_closed_leaf_only_opens_with_verified_portal():
    model,_,nodes=fixture([obstacle('left',6,2,1,4),obstacle('right',6,7.5,1,5)])
    door=obstacle('door',6,4.5,1,1)
    door.kind='door'
    model.elements.append(door)
    assert not build_navigation(model,nodes).routes
    report=build_navigation(model,nodes,NS(portals=[NS(passable=True,door_ids=['door'])]))
    assert report.routes
    for route in report.routes:
        assert abs(route.distance_m-LineString(route.points).length)<1e-5


def test_concave_mesh_does_not_triangulate_across_missing_floor():
    domain=Polygon([(0,0),(8,0),(8,2),(2,2),(2,8),(0,8)])
    mesh=WalkMesh(domain)
    path=mesh.route((1,7),(7,1))
    assert path and len(path)>2
    assert domain.covers(LineString(path))


def test_floating_stair_is_not_reachable_by_walking_underneath_it():
    from backend.app.life_safety import build
    model,level,_=fixture()
    level.index=0
    model.program_allocation.zones=[]
    model.datum_set=NS(value=lambda key:1.2)
    landing=element('CIR-LND-L01','stair_landing',
        BoxGeometry(center=v3(10,2,3.1),size=v3(1.2,1.2,.2)))
    landing.position=v3(10,2,3.1)
    model.elements.append(landing)
    graph=build(model,[],typology='theater')
    assert not graph.exits
    assert any(f.clause=='NAV-STAIR-LANDING' and f.status=='fail' for f in graph.findings)


def test_landing_owns_floor_opening_and_joins_floor_at_its_edges():
    from backend.app.life_safety import build
    model,level,_=fixture(holes=[box(9,1,11,3)])
    level.index=0
    model.program_allocation.zones=[]
    model.datum_set=NS(value=lambda key:1.2)
    landing=element('CIR-LND-L01','stair_landing',
        BoxGeometry(center=v3(10,2,-.1),size=v3(2,2,.2)))
    landing.position=v3(10,2,-.1)
    model.elements.append(landing)
    graph=build(model,[],typology='theater')
    assert len(graph.exits)==1
    assert not any(f.clause=='NAV-STAIR-LANDING' for f in graph.findings)


def stage_fixture(*, width=1.2, rise=.18, floating=0):
    parts=[]
    for index in range(3):
        top=rise*(index+1)
        part=element(f'stage-step-{index}','stair_tread',BoxGeometry(
            center=v3(4+.3*(index+.5),5,(top+floating)/2),size=v3(.3,width,top-floating)))
        part.subsystem='stage_access'
        parts.append(part)
    parts.append(element('stage','stage_platform',BoxGeometry(
        center=v3(6.45,5,rise*3/2),size=v3(3.1,4,rise*3))))
    model,level,nodes=fixture(parts)
    zone=model.program_allocation.zones[0]
    zone.space_type='stage'
    zone.x0,zone.x1,zone.y0,zone.y1=4,8,3,7
    return model,level,nodes


def test_stage_routes_use_emitted_steps_and_keep_measured_vertical_distance():
    model,level,nodes=stage_fixture()
    report=build_navigation(model,nodes)
    samples=[sample for sample in report.samples if sample.origin=='stage']
    assert samples and all(sample.reachable_exits for sample in samples)
    routes=[route for route in report.routes if route.sample_id in {sample.id for sample in samples}]
    assert all(route.step_count==3 for route in routes)
    for route in routes:
        assert route.points_3d[0][2]==pytest.approx(.54)
        assert route.points_3d[-1][2]==level.z
        assert route.distance_m==pytest.approx(sum(math.dist(a,b) for a,b in zip(route.points_3d,route.points_3d[1:])),abs=1e-5)
        assert {'stage',*(f'stage-step-{index}' for index in range(3))}<=set(route.source_surface_ids)
        assert route.distance_m>LineString(route.points).length
    assert any(f.id=='NAV-CODE-BASIS' and f.status=='unevaluated' for f in report.findings)


@pytest.mark.parametrize('change',['missing_tread','floating_steps','too_high','too_narrow','blocked_headroom'])
def test_stage_graph_refuses_disconnected_or_nontraversable_physical_steps(change):
    model,level,nodes=stage_fixture(width=.59 if change=='too_narrow' else 1.2,
        rise=.20 if change=='too_high' else .18,floating=.05 if change=='floating_steps' else 0)
    if change=='missing_tread':
        model.elements=[e for e in model.elements if e.id!='stage-step-1']
    if change=='blocked_headroom':
        model.elements.append(element('low-beam','primary_beam',BoxGeometry(
            center=v3(4.45,5,1.75),size=v3(.9,1.2,.1))))
    graph=SteppedWalkMesh(model,level)
    assert not graph.unknown
    assert graph.route((6,5),.6 if change=='too_high' else .54,(10,2.5)) is None
    report=build_navigation(model,nodes)
    samples=[sample for sample in report.samples if sample.origin=='stage']
    assert samples and not any(sample.reachable_exits for sample in samples)


@pytest.mark.parametrize('bottom,top',[(.08,.15),(.002,.003)])
def test_floating_platform_above_close_floor_never_gets_a_vertical_centroid_link(bottom,top):
    platform=element('floating-stage','stage_platform',BoxGeometry(
        center=v3(6,5,(bottom+top)/2),size=v3(3,3,top-bottom)))
    model,level,_=fixture([platform])
    graph=SteppedWalkMesh(model,level)
    assert graph.route((6,5),top,(10,2.5)) is None


def test_seat_row_reservation_without_actual_raised_floor_is_visible_as_failure():
    model,_,nodes=stage_fixture()
    model.program_allocation.zones[0].space_type='auditorium'
    model.room_layout_plan=NS(reservations=[NS(id='row-access',space_id='ROOM',level_id='L01',
        purpose='seat_row_access',floor_z_m=.4,polygon=[(5,4),(7,4),(7,4.6),(5,4.6)])])
    report=build_navigation(model,nodes)
    assert any(f.id=='NAV-SEAT-SURFACE' and f.subject=='SP-L01-ROOM' for f in report.findings)
    assert not any(sample.origin=='seat_row_access' for sample in report.samples)


@pytest.mark.parametrize('direction',[-1,1])
def test_actual_emitted_seats_have_row_passages_routed_down_real_aisle_treads(direction):
    from backend.tests.test_room_fixtures import auditorium
    from backend.app.room_fixtures import emit_auditorium_seating
    builder,zone=auditorium(direction)
    emit_auditorium_seating(builder,builder.level,zone)
    model=builder.model(zone)
    model.elements=[element for group in model.element_groups for element in group.expand()]
    nodes=[NS(id='SP-L01-ROOM',kind='space',level_id='L01'),
           NS(id='EXIT',kind='exit_stair',level_id='L01',x=1 if direction>0 else 11,y=5)]
    report=build_navigation(model,nodes)
    rows=[sample for sample in report.samples if sample.origin=='seat_row_access']
    assert rows and {round(sample.floor_z_m,3) for sample in rows}=={0,.25,.5,.75,1}
    assert all(sample.reachable_exits for sample in rows)
    raised_ids={sample.id for sample in rows if sample.floor_z_m>0}
    routes=[route for route in report.routes if route.sample_id in raised_ids]
    assert routes and all(route.step_count>=2 for route in routes)
    assert all(any(identifier.startswith('PRG-AIS-') for identifier in route.source_surface_ids) for route in routes)
