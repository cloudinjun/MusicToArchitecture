"""Complete subassemblies, actual hosts, and deliberate missing-part regressions."""
from copy import deepcopy
from types import SimpleNamespace
from math import pi

import pytest
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from backend.app.assembly_review import review_furniture
from backend.app.axis import AxisSkeleton
from backend.app.compiler_v3 import (
    SHELF_CROSS_AISLE_M, SHELF_DEPTH_M, SHELF_FIRST_ROW_OFFSET_M,
    SHELF_REGION_BODY_MARGIN_M, SHELF_ROW_PITCH_M, _Builder, _emit_program,
    _plan_shelving_field, _shelving_cross_aisle_x, _shelving_run_layout,
)
from backend.app.dependencies import compile_dependency_graph
from backend.app.furniture import furniture_parts, emit_furniture, usable_floor, footprint, REQUIRED_ROLES
from backend.app.geometry import BoxGeometry, ExtrusionGeometry, MemberGeometry, convention_profile, v2, v3
from backend.app.models_v3 import ElementInstance
from backend.app.navigation import BODY_WIDTH_M, WalkMesh, free_floor, polygons
from backend.app.room_fixtures import placement_obstacles
from backend.app.spatial_rules import SpatialIndex, check_spatial_rules, plan_overlap


def builder_with_floor():
    b = _Builder.__new__(_Builder)
    b.groups={}; b.element_ids=set(); b.element_kinds={}; b.element_levels={}
    b.profiles={}; b.count=0; b.axis=AxisSkeleton()
    # `_Builder.add` now reads the optional facade-control protocol. This narrow
    # fixture bypasses `__init__`, so install its explicit no-control lattice before
    # emitting the first test solid.
    b.lattice = SimpleNamespace(facade_control=None)
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


def test_shelf_rows_reserve_one_continuous_measured_cross_aisle():
    b, level, zone = builder_with_floor()
    zone.space_type = 'special_collections'
    allocation = SimpleNamespace(zones_on=lambda index: [zone])
    b.add('STR-COL-AISLE-TEST', 'column', 'structure', 'columns',
          BoxGeometry(center=v3(0, 0, 4.5), size=v3(0.4, 0.4, 3.0)),
          'concrete', level_id=level.id, supports=['STR-SLB-L01'])
    region = usable_floor(level, zone, placement_obstacles(b, level))
    row_count = max(1, int((zone.y1 - zone.y0) / SHELF_ROW_PITCH_M))
    aisle_x = _shelving_cross_aisle_x(
        region, zone.x0, zone.y0, zone.x1, zone.y1, row_count)
    assert aisle_x is not None
    assert aisle_x != pytest.approx(0.0)

    _emit_program(b, allocation)

    elements = [element for group in b.groups.values() for element in group.expand()]
    shelf_roots = [element for element in elements
                   if element.kind == 'shelving_run' and element.part_role == 'shelf_0']
    assert shelf_roots
    for shelf in shelf_roots:
        shelf_edge = (shelf.position.x - shelf.dimensions.x / 2.0
                      if shelf.position.x > aisle_x
                      else shelf.position.x + shelf.dimensions.x / 2.0)
        assert abs(shelf_edge - aisle_x) >= SHELF_CROSS_AISLE_M / 2.0 - 1e-9

    model = SimpleNamespace(elements=elements, profiles=b.profiles)
    domain, unresolved = free_floor(model, level)
    cross_aisle = LineString([(aisle_x, zone.y0 + 0.5),
                              (aisle_x, zone.y1 - 0.5)])
    assert not unresolved
    assert domain.covers(cross_aisle)
    assert WalkMesh(domain).route(*cross_aisle.coords) is not None


@pytest.mark.parametrize(
    ('bounds', 'column_centres'),
    [
        (
            (-35.07, 3.489, -26.47, 17.441),
            [(x, y) for x in (-35.0702, -31.882)
             for y in (6.3448, 13.9528, 16.6774)],
        ),
        (
            (-25.87, -17.441, -5.325, 3.488),
            ([(x, y) for x in (-25.5056, -19.1292)
              for y in (-13.538, -6.9764, -3.2054, 0.0, 1.559)]
             + [(x, y) for x in (-15.0702, -12.7528, -6.3764)
                for y in (-13.538, -6.9764)]),
        ),
    ],
)
def test_shelf_field_keeps_every_fixed_grid_bay_connected(bounds, column_centres):
    """Round 04: shelf rows plus columns must not create sampled floor islands."""

    columns = [box(x - .1524, y - .1524, x + .1524, y + .1524)
               for x, y in column_centres]
    region = box(*bounds).difference(unary_union(columns)).buffer(-.05, join_style=2)
    x0, y0, x1, y1 = bounds
    row_count = max(1, int((y1 - y0) / SHELF_ROW_PITCH_M))
    aisle_x = _shelving_cross_aisle_x(region, *bounds, row_count)
    assert aisle_x is not None
    runs = _shelving_run_layout(x0, x1, aisle_centre=aisle_x)
    candidates = [
        (row, column, x,
         y0 + SHELF_FIRST_ROW_OFFSET_M + row * SHELF_ROW_PITCH_M, width)
        for row in range(row_count)
        for column, (x, width) in enumerate(runs)
    ]

    def navigation_domain(placements):
        domain = region.buffer(-SHELF_REGION_BODY_MARGIN_M, join_style=2)
        for _row, _column, x, y, width in placements:
            footprint = box(
                x - width / 2.0, y - SHELF_DEPTH_M / 2.0,
                x + width / 2.0, y + SHELF_DEPTH_M / 2.0)
            if region.covers(footprint):
                domain = domain.difference(
                    footprint.buffer(BODY_WIDTH_M / 2.0, join_style=2))
        return domain

    # The long stacks field reproduces the Round 04 islands with the former
    # cross-aisle-only layout.  The smaller processing fixture still exercises the
    # column-bound perimeter bay, although its simplified obstacle set lets the
    # aisle search choose a safer centre than the complete emitted room did.
    if len(column_centres) > 10:
        assert len(polygons(navigation_domain(candidates))) > 1

    kept, omitted = _plan_shelving_field(region, *bounds)
    assert kept and omitted
    assert len(kept) / (len(kept) + len(omitted)) >= .70
    assert len(polygons(navigation_domain(kept))) == 1


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
