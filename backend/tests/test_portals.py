"""Physical aperture/support counterexamples; these are not code-compliance tests."""
from types import SimpleNamespace as NS

import pytest
from shapely.geometry import Polygon, box

from backend.app.geometry import BoxGeometry, v3
from backend.app.portals import (inspect_portals, approach_regions,
                                 choose_partition_opening, shaft_wall_parts,
                                 split_room_edges, select_lift_face,stage_access_plan)


def item(identifier, kind, x, y, z, sx, sy, sz, *, subsystem='partitions', rotation=0):
    return NS(kind=kind, subsystem=subsystem, thickness_m=None, rule_refs=[],
              instances=[NS(id=identifier, level_id='L01', geometry=BoxGeometry(
                  center=v3(x,y,z), size=v3(sx,sy,sz), rotation_z=rotation))])


def model(*groups):
    return NS(element_groups=list(groups), profiles={})


def room(*extras, floor=True):
    groups = [item('DOOR','door',0,0,1.05,.915,.1,2.1),
              item('WALL-A','partition',-1.72875,0,1.5,2.5425,.2,3),
              item('WALL-B','partition',1.72875,0,1.5,2.5425,.2,3),
              item('HEAD','partition_head',0,0,2.55,.915,.2,.9)]
    if floor:
        groups.append(item('FLOOR','floor_slab',0,0,-.15,8,8,.3))
    return model(*groups, *extras)


def test_real_opening_with_two_floor_approaches_is_passable():
    report = inspect_portals(room())
    assert report.status == 'passed'
    portal = report.portals[0]
    assert portal.passable and portal.aperture_clear
    assert portal.door_ids == ['DOOR']
    assert portal.wall_depth_m == pytest.approx(.2)
    assert portal.side_a.support_ids == portal.side_b.support_ids == ['FLOOR']
    assert len(approach_regions(room(), 'L01')) == 2
    assert report.model_dump(mode='json')['portals'][0]['floor_z'] == 0


@pytest.mark.parametrize('x,y', [(0,0), (0,.65)])
def test_wall_in_aperture_or_approach_prevents_traversal(x,y):
    report = inspect_portals(room(item('BLOCK','partition',x,y,1,.4,.4,2)))
    assert not report.portals[0].passable
    assert any('BLOCK' in f.elements for f in report.findings)


def test_one_sided_floor_cannot_create_door_edge():
    report = inspect_portals(room(item('HALF','floor_slab',0,-2,-.15,8,4,.3),floor=False))
    portal = report.portals[0]
    assert not portal.passable
    assert portal.side_a.unsupported_m2 > 1
    assert portal.side_b.unsupported_m2 == 0


def test_floor_at_wrong_height_is_measured_not_assumed_from_level_id():
    report = inspect_portals(room(item('LOW','floor_slab',0,0,-.27,8,8,.3),floor=False))
    portal = report.portals[0]
    assert not portal.passable
    assert portal.side_a.elevation_mismatch_m == pytest.approx(.12)


def test_threshold_gap_is_not_hidden_by_supported_approaches():
    report = inspect_portals(room(
        item('FLOORA','floor_slab',0,2.05,-.15,8,3.9,.3),
        item('FLOORB','floor_slab',0,-2.05,-.15,8,3.9,.3),floor=False))
    assert not report.portals[0].passable
    assert report.portals[0].side_a.unsupported_m2 == 0
    assert report.portals[0].side_b.unsupported_m2 == 0
    assert any(f.rule_id == 'PORTAL-THRESHOLD-UNSUPPORTED' for f in report.findings)


@pytest.mark.parametrize('face_x,side', [(True,1),(True,-1),(False,1),(False,-1)])
def test_lift_wall_has_real_hole_and_head_in_every_orientation(face_x,side):
    parts = shaft_wall_parts(0,0,3.4,.2,0,3.5,face_x=face_x,side=side,
                             opening_bottom=0,opening_width=.9,opening_height=2.1)
    groups = [NS(kind='elevator_shaft',subsystem='vertical_core',rule_refs=[],
                 instances=[NS(id=tag,level_id='L01',geometry=g)]) for tag,g in parts]
    x,y = (side*1.6,0) if face_x else (0,side*1.6)
    sx,sy = (.2,.9) if face_x else (.9,.2)
    groups.append(item('LIFT-DR','door',x,y,1.05,sx,sy,2.1,subsystem='vertical_core'))
    portal = inspect_portals(model(*groups)).portals[0]
    assert portal.aperture_clear
    assert not portal.passable  # no car floor is invented
    assert any(tag == 'HEAD' for tag,_ in parts)
    from backend.app.geometry_review import _polygon
    aperture = Polygon(portal.aperture).buffer(-1e-5)
    assert all(_polygon(g).intersection(aperture).area < 1e-6
               for tag,g in parts if tag != 'HEAD')


def test_lift_landing_bridges_opening_without_inventing_car_floor():
    """A measured landing supports the door threshold; the shaft stays unresolved."""
    parts = shaft_wall_parts(0,0,3.4,.2,0,3.5,face_x=True,side=1,
                             opening_bottom=0,opening_width=.9,opening_height=2.1)
    groups = [NS(kind='elevator_shaft',subsystem='vertical_core',rule_refs=[],
                 instances=[NS(id=tag,level_id='L01',geometry=g)]) for tag,g in parts]
    groups.extend([
        item('LIFT-DR','door',1.6,0,1.05,.2,.9,2.1,subsystem='vertical_core'),
        item('LANDING','lift_landing',1.6,0,-.075,.2,.9,.15,
             subsystem='vertical_core'),
        item('FLOOR','floor_slab',3.3,0,-.15,3.2,3,.3),
    ])
    report = inspect_portals(model(*groups))
    portal = report.portals[0]
    assert report.status == 'unevaluated'
    assert portal.aperture_clear
    assert portal.side_b.unsupported_m2 == 0
    assert portal.side_b.support_ids == ['FLOOR']
    assert not any(f.rule_id in {'PORTAL-APPROACH-UNSUPPORTED',
                                 'PORTAL-THRESHOLD-UNSUPPORTED'}
                   for f in report.findings)
    assert [f.rule_id for f in report.findings] == ['PORTAL-LIFT-CAR-UNVERIFIED']
    assert not portal.passable


def test_partition_choice_moves_off_obstacle_but_never_off_floor():
    groups = [item('FLOOR','floor_slab',0,0,-.15,8,8,.3),
              item('COLUMN','column',0,.65,1.5,.4,.4,3)]
    builder = NS(groups=dict(enumerate(groups)),profiles={})
    level = NS(z=0)
    position = choose_partition_opening(builder,level,(-3,0),(3,0),.915,.2)
    assert position is not None and abs(position-3) > .5
    builder.groups[0] = item('HALF','floor_slab',0,-2,-.15,8,4,.3)
    assert choose_partition_opening(builder,level,(-3,0),(3,0),.915,.2) is None


def test_required_unplaced_door_remains_visible_in_report():
    wall = item('CLOSED','partition',0,0,1.5,5,.2,3)
    wall.rule_refs = ['MTA-DOOR-UNRESOLVED']
    report = inspect_portals(model(wall))
    assert report.status == 'failed'
    assert report.findings[0].rule_id == 'PORTAL-REQUIRED-UNPLACED'


@pytest.mark.parametrize('supported', [True, False])
def test_partition_emitter_preserves_required_wall_when_no_door_fits(supported):
    from backend.app.compiler_v3 import _emit_partition_run
    from backend.app.partitions import required_separation, select_partition
    floor = (item('FLOOR','floor_slab',0,0,-.15,8,8,.3) if supported else
             item('HALF','floor_slab',0,-2,-.15,8,4,.3))
    builder = NS(groups={'floor':floor}, profiles={})
    def add(identifier, kind, layer, subsystem, geometry, material, **metadata):
        builder.groups[identifier] = NS(kind=kind,subsystem=subsystem,
            thickness_m=None,rule_refs=metadata.get('rule_refs',[]),
            reason=metadata.get('reason',''),instances=[NS(id=identifier,
            level_id=metadata['level_id'],geometry=geometry)])
    builder.add = add
    requirement = required_separation('mechanical','circulation',category_a='service',
        category_b='circulation',storeys=3,sprinklered=True,area_a_m2=50)
    partition = select_partition(requirement)
    level = NS(id='L01',index=1,z=0)
    zone = NS(category='service',space_type='mechanical',band_index=0,label='Plant')
    _emit_partition_run(builder,'TEST',partition,requirement,level,-3,0,3,0,3,zone)
    emitted = model(*builder.groups.values())
    report = inspect_portals(emitted)
    if supported:
        assert report.portals[0].passable
        assert any(group.kind=='partition_head' for group in builder.groups.values())
    else:
        assert not report.portals
        assert any(group.kind=='partition' for group in builder.groups.values())
        assert any('MTA-DOOR-UNRESOLVED' in group.rule_refs for group in builder.groups.values())
        assert report.findings[0].rule_id == 'PORTAL-REQUIRED-UNPLACED'


def test_partial_neighbours_do_not_claim_an_entire_long_wall():
    a=NS(space_id='A',x0=0,y0=0,x1=10,y1=5)
    b=NS(space_id='B',x0=0,y0=5,x1=3,y1=10)
    c=NS(space_id='C',x0=3,y0=5,x1=10,y1=10)
    shared=[(n.space_id,coords) for z,n,edge,coords in split_room_edges([a,b,c])
            if z.space_id=='A' and edge.startswith('N')]
    assert shared == [('B',(0,5,3,5)),('C',(3,5,10,5))]


def test_lift_faces_clear_floor_instead_of_the_nearest_stair_obstacle():
    builder=NS(groups={0:item('FLOOR','floor_slab',0,0,-.15,12,12,.3),
                       1:item('STAIR','stair_tread',2.3,0,.5,1.2,2,1)},profiles={})
    face_x,side,served=select_lift_face(builder,[NS(id='L01',z=0)],0,0,3.4,.2,.9,(True,1))
    assert served==['L01']
    assert (face_x,side)!=(True,1)


def room_builder(*extra,supported=True):
    floor=item('FLOOR','floor_slab',0,0,-.15,12,12,.3)
    builder=NS(groups={**({'floor':floor} if supported else {}),
                       **{f'extra{i}':g for i,g in enumerate(extra)}},profiles={})
    def add(identifier,kind,layer,subsystem,geometry,material,**metadata):
        builder.groups[identifier]=NS(kind=kind,subsystem=subsystem,
            thickness_m=metadata.get('thickness_m'),rule_refs=metadata.get('rule_refs',[]),
            instances=[NS(id=identifier,level_id=metadata['level_id'],geometry=geometry)])
    builder.add=add
    level=NS(id='L01',index=1,z=0)
    builder.lattice=NS(occupied=[level])
    builder.datums=NS(value=lambda key:{'floor_to_floor_m':3.5,'slab_thickness_m':.25}[key])
    zone=NS(space_id='PLANT',space_type='mechanical',category='service',label='Plant',
            level_id='L01',band_index=0,x0=-2,y0=-2,x1=2,y1=2,area_delivered_m2=16)
    return builder,level,zone


@pytest.mark.parametrize('supported',[True,False])
def test_access_is_required_once_per_room_not_on_every_wall(supported):
    from backend.app.compiler_v3 import _emit_partitions
    builder,_,zone=room_builder(supported=supported)
    allocation=NS(zones=[zone])
    _emit_partitions(builder,allocation,True)
    result=model(*builder.groups.values())
    result.program_allocation=allocation
    report=inspect_portals(result)
    assert len(report.portals)==(1 if supported else 0)
    assert sum(f.rule_id=='PORTAL-ROOM-INACCESSIBLE' for f in report.findings)==(0 if supported else 1)
    assert not any(f.rule_id=='PORTAL-REQUIRED-UNPLACED' for f in report.findings)
    assert sum(g.kind=='partition' for g in builder.groups.values()) >= 4


def test_existing_entrance_continues_through_program_wall_without_duplicate_leaf():
    from backend.app.compiler_v3 import _emit_partitions
    entrance=item('ENV-ENT','entrance_door',0,-2,1.05,1,.08,2.1,subsystem='entrance')
    builder,_,zone=room_builder(entrance)
    _emit_partitions(builder,NS(zones=[zone]),True)
    result=model(*builder.groups.values())
    result.program_allocation=NS(zones=[zone])
    report=inspect_portals(result)
    portal=next(p for p in report.portals if p.kind=='entrance')
    assert portal.aperture_clear and portal.passable
    aperture=Polygon(portal.aperture).buffer(-1e-5)
    from backend.app.geometry_review import _polygon
    assert not any(_polygon(i.geometry).intersection(aperture).area>1e-6
                   for g in builder.groups.values() if g.kind=='door' for i in g.instances)


def test_stage_steps_occupy_a_carved_pocket_and_meet_real_floor_and_stage():
    builder,level,_=room_builder()
    carve=NS(stage=(-3,-3,3,3),focal_h_m=.9,proscenium_x=-3)
    access=stage_access_plan(builder,level,carve)
    assert access is not None
    assert access['rise_m']==pytest.approx(.18)
    assert access['tread_m']==pytest.approx(.3)
    from backend.app.geometry_review import _polygon,_z_interval
    body=box(-2.95,-2.95,2.95,2.95).difference(access['pocket'])
    pieces=access['parts']
    assert len(pieces)==6
    assert [kind for _,kind,_ in pieces].count('stair_tread')==5
    assert [kind for _,kind,_ in pieces].count('stage_platform')==1
    assert not [kind for _,kind,_ in pieces if kind=='stair_landing']
    assert _z_interval(pieces[0][2])[0]==pytest.approx(level.z)
    assert _z_interval(pieces[-1][2])[1]==pytest.approx(level.z+.9)
    for _,_,geometry in pieces:
        assert _polygon(geometry).intersection(body).area<1e-6
    assert access['bottom_region'].intersection(_polygon(pieces[0][2])).area<1e-6
    assert _polygon(pieces[-1][2]).boundary.intersection(body.boundary).length>1


def test_stage_pocket_refuses_when_real_support_is_absent():
    builder,level,_=room_builder(supported=False)
    carve=NS(stage=(-3,-3,3,3),focal_h_m=.9,proscenium_x=-3)
    assert stage_access_plan(builder,level,carve) is None
