"""Complete subassemblies, actual hosts, and deliberate missing-part regressions."""
from copy import deepcopy
from types import SimpleNamespace
from math import pi

import pytest
from shapely.geometry import box

from backend.app.assembly_review import review_furniture
from backend.app.axis import AxisSkeleton
from backend.app.compiler_v3 import _Builder, _emit_program
from backend.app.dependencies import compile_dependency_graph
from backend.app.furniture import furniture_parts, emit_furniture, usable_floor, footprint, REQUIRED_ROLES
from backend.app.geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, convention_profile, v2, v3
from backend.app.models_v3 import ElementInstance
from backend.app.spatial_rules import SpatialIndex, check_spatial_rules, plan_overlap


def builder_with_floor():
    b = _Builder.__new__(_Builder)
    b.groups={}; b.element_ids=set(); b.element_kinds={}; b.element_levels={}
    b.profiles={}; b.count=0; b.axis=AxisSkeleton()
    b.add('SIT-POD-001','podium_slab','site','podium',
          BoxGeometry(center=v3(0,0,-.25),size=v3(20,20,.5)),'concrete',level_id='L00')
    b.add('STR-SLB-L01','floor_slab','structure','slabs',
          ExtrusionGeometry(boundary=[v2(-5,-5),v2(5,-5),v2(5,5),v2(-5,5)],
                            z_base=2.7,z_top=3.0),'concrete',level_id='L01',supports=['SIT-POD-001'])
    level=SimpleNamespace(id='L01',index=1,z=3.,plate=[v2(-5,-5),v2(5,-5),v2(5,5),v2(-5,5)],voids=[])
    zone=SimpleNamespace(x0=-4,y0=-4,x1=4,y1=4,category='public',space_type='reading',
                         band_index=0,space_id='reading-zone',label='Reading',
                         area_delivered_m2=64,area_required_m2=64,deviation=0)
    b.lattice=SimpleNamespace(occupied=[level],levels=[level])
    return b,level,zone


def model_of(b):
    return SimpleNamespace(element_groups=list(b.groups.values()),profiles=b.profiles,
                           lattice=b.lattice,program_allocation=SimpleNamespace(cores_unreserved=[]))


def placed(kind='desk'):
    b,level,zone=builder_with_floor()
    parts=furniture_parts(kind,0,0,level.z,1.6 if kind=='desk' else .48 if kind=='seat' else 4.2,
                          .8 if kind=='desk' else .48 if kind=='seat' else .55)
    assert emit_furniture(b,'ROOT',kind,parts,level,zone,usable_floor(level,zone))
    return b


@pytest.mark.parametrize('kind',['desk','seat','shelving_run'])
def test_recipe_is_complete_and_physically_supported(kind):
    b=placed(kind)
    assert review_furniture(model_of(b)) == []
    items=[i for g in b.groups.values() if g.subsystem=='furniture' for i in g.instances]
    assert {i.part_role for i in items} == REQUIRED_ROLES[kind]
    assert all(i.assembly_id=='ROOT' for i in items)
    assert 'ROOT' in [i.id for i in items]
    graph=compile_dependency_graph(list(b.groups.values()))
    assert review_furniture(model_of(b)) == []
    assert not any(c.status=='failed' for c in graph.checks)
    # A rebuild retains the explicit part graph rather than replacing it with floor edges.
    again=compile_dependency_graph(list(b.groups.values()))
    assert graph.model_dump()==again.model_dump()


def test_deleting_a_leg_fails_completeness_and_contact():
    b=placed()
    for g in b.groups.values():
        g.instances=[i for i in g.instances if i.part_role != 'leg_0']
    rules={f.rule_id for f in review_furniture(model_of(b))}
    assert rules == {'SP-FURNITURE-COMPLETE','SP-FURNITURE-CONTACT'}


def test_declared_host_does_not_excuse_a_floating_part():
    b=placed()
    leg=next(i for g in b.groups.values() for i in g.instances if i.part_role=='leg_0')
    leg.geometry.center.z+=.1
    assert any(f.rule_id=='SP-FURNITURE-CONTACT' and leg.id in f.elements
               for f in review_furniture(model_of(b)))


def test_legacy_named_tabletop_is_not_complete():
    b=placed()
    for g in b.groups.values():
        for item in g.instances:
            item.assembly_id=None; item.part_role=None
    assert any(f.rule_id=='SP-FURNITURE-COMPLETE' for f in review_furniture(model_of(b)))


def test_point_contact_is_not_a_bearing():
    from backend.app.assembly_review import _contact
    a=BoxGeometry(center=v3(0,0,0),size=v3(1,1,1))
    b=BoxGeometry(center=v3(1,1,1),size=v3(1,1,1))
    assert not _contact(a,b)


def test_full_footprint_is_checked_not_only_its_centre():
    b,level,zone=builder_with_floor()
    parts=furniture_parts('desk',0,0,3,1.6,.8)
    region=usable_floor(level,zone,forbidden=[box(.5,-1,1,1)])
    assert not emit_furniture(b,'ROOT','desk',parts,level,zone,region)
    assert 'ROOT' not in b.element_ids


def test_floor_void_under_a_leg_cannot_be_given_a_fake_floor_host():
    b,level,zone=builder_with_floor()
    slab=next(i for g in b.groups.values() for i in g.instances if i.id=='STR-SLB-L01')
    slab.geometry.holes=[[v2(-.9,-.5),v2(-.5,-.5),v2(-.5,0),v2(-.9,0)]]
    # Deliberately leave this core hole out of lattice. Actual floor solid still wins.
    parts=furniture_parts('desk',0,0,3,1.6,.8)
    assert not emit_furniture(b,'ROOT','desk',parts,level,zone,usable_floor(level,zone))


def test_actual_program_emitter_builds_parts_not_floating_boards():
    b,level,zone=builder_with_floor()
    allocation=SimpleNamespace(zones_on=lambda index:[zone])
    _emit_program(b,allocation)
    assert review_furniture(model_of(b)) == []
    assemblies={i.assembly_id for g in b.groups.values() if g.subsystem=='furniture' for i in g.instances}
    assert assemblies and None not in assemblies
    for g in b.groups.values():
        for flat in g.expand():
            if g.subsystem=='furniture':
                assert flat.assembly_id and flat.part_role


def test_optional_metadata_keeps_old_instance_payload_readable():
    payload=dict(id='old',level_id='L01',position=v3(0,0,0).model_dump(),
                 dimensions=v3(1,1,1).model_dump(),geometry=BoxGeometry(center=v3(0,0,0),size=v3(1,1,1)).model_dump())
    instance=ElementInstance.model_validate(payload)
    assert instance.assembly_id is None and instance.part_role is None


def test_spatial_bounds_use_rotation_and_actual_profile():
    b,_,_=builder_with_floor()
    b.add('ROT','partition','program','partitions',
          BoxGeometry(center=v3(0,0,4),size=v3(4,.2,2),rotation_z=pi/2),'concrete',level_id='L01')
    b.profiles['P']=convention_profile('P','rectangle',.6,.4)
    b.add('BEAM','primary_beam','structure','frame',
          MemberGeometry(path=[v3(0,0,5),v3(4,0,5)],profile='P'),'concrete',level_id='L01')
    solids={s.id:s for s in SpatialIndex(model_of(b)).solids}
    assert solids['ROT'].x1-solids['ROT'].x0 == pytest.approx(.2)
    assert solids['ROT'].y1-solids['ROT'].y0 == pytest.approx(4)
    assert solids['BEAM'].z1-solids['BEAM'].z0 == pytest.approx(.6)


def test_limit_zero_cannot_hide_violations():
    b=placed()
    for g in b.groups.values():
        g.instances=[i for i in g.instances if i.part_role != 'leg_0']
    report=check_spatial_rules(model_of(b),limit=0)
    assert report.status=='failed' and report.counts['SP-FURNITURE-COMPLETE']>0
    assert report.findings==[]


def test_edge_cut_void_uses_subtraction_not_an_invalid_nested_hole():
    _,level,zone=builder_with_floor()
    level.voids=[[v2(3,-6),v2(6,-6),v2(6,6),v2(3,6)]]
    region=usable_floor(level,zone)
    assert region.is_valid and region.bounds[2] < 3.0
