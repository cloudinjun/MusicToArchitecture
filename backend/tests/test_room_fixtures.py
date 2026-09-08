"""Room layout counterexamples inspect emitted parts, not placement flags."""
from types import SimpleNamespace as NS

import pytest
from shapely.geometry import Polygon, box

from backend.app.datums import Lattice, LevelDatum
from backend.app.geometry import BoxGeometry, ExtrusionGeometry, bounds, v2, v3
from backend.app.models_v3 import ElementGroup, ElementInstance
from backend.app.program import AllocatedZone, ProgramAllocation
from backend.app.room_fixtures import (
    RoomLayoutPlan, emit_auditorium_seating, emit_service_room, fixture_recipe,
    inspect_room_layouts, placement_obstacles, emit_theatre_floor,
)
from backend.app.archetypes import BowlRow, ROW_DEPTH_M, SEAT_LINE_OFFSET_M
from backend.app.geometry_review import _polygon, _z_interval


class Builder:
    def __init__(self, width=12, depth=10):
        self.level = LevelDatum(id='L01',index=0,z=0,kind='occupied',
            plate=[v2(x,y) for x,y in [(0,0),(width,0),(width,depth),(0,depth)]],voids=[])
        self.lattice = Lattice(levels=[self.level],x_lines=[0,width],y_lines=[0,depth],
            apse_nodes=[],plan_x_m=width,plan_y_m=depth)
        self.groups = {}
        self.profiles = {}
        self.room_layout_plan = RoomLayoutPlan()
        self.add('SLAB','floor_slab','structure','floors',
            BoxGeometry(center=v3(width/2,depth/2,-.1),size=v3(width,depth,.2)),
            'concrete',level_id='L01')

    def add(self, identifier, kind, layer, subsystem, geometry, material, **metadata):
        position,dimensions = bounds(geometry)
        instance_fields = {'level_id','lattice_index','supports','assembly_id','part_role'}
        instance_kwargs = {key:metadata.pop(key) for key in list(metadata) if key in instance_fields}
        instance_kwargs.setdefault('level_id','L01')
        instance = ElementInstance(id=identifier,geometry=geometry,position=position,
                                   dimensions=dimensions,**instance_kwargs)
        metadata.setdefault('program','test')
        metadata.setdefault('category','public')
        metadata.setdefault('reason','Test construction')
        self.groups[identifier] = ElementGroup(group_id=identifier,kind=kind,
            semantic_layer=layer,subsystem=subsystem,material_profile=material,
            instances=[instance],**metadata)

    def model(self, zone):
        return NS(element_groups=list(self.groups.values()),profiles=self.profiles,lattice=self.lattice,
            room_layout_plan=self.room_layout_plan,
            program_allocation=ProgramAllocation(zones=[zone],unplaced=[],
                usable_area_by_level={'L01':zone.area_delivered_m2},
                required_area_m2=zone.area_required_m2,delivered_area_m2=zone.area_delivered_m2))


def zone(builder, space_type='public_restroom'):
    x1,y1 = builder.level.plate[2].x,builder.level.plate[2].y
    return AllocatedZone(space_id='ROOM',space_type=space_type,label='Test room',
        category='public',occupancy_id='business',level_index=0,level_id='L01',
        band_index=0,x0=0,y0=0,x1=x1,y1=y1,area_required_m2=x1*y1,
        area_delivered_m2=x1*y1,daylight_satisfied=True,level_preference_satisfied=True)


def failures(report):
    return {item.check_id for item in report.findings if item.status=='failed'}


def test_member_obstacle_reads_only_its_own_section_profile():
    from backend.app.geometry import MemberGeometry, convention_profile
    from backend.app.room_fixtures import _shape

    class UnusedProfile:
        def model_dump(self):
            pytest.fail('Obstacle sweep serialized an unrelated profile')

    profile = convention_profile('USED', 'rectangle', .3, .2)
    geometry = MemberGeometry(path=[v3(0, 0, 0), v3(0, 0, 4)], profile=profile.id)
    shape, vertical = _shape(NS(thickness_m=None), NS(id='COLUMN', geometry=geometry),
                             {'USED': profile, 'UNUSED': UnusedProfile()})
    assert shape.area == pytest.approx(.3 * .2)
    assert vertical == pytest.approx((0, 4))


@pytest.mark.parametrize('space,recipes',[
    ('public_restroom',{'toilet':1,'basin':1}),
    ('staff_restroom',{'toilet':1,'basin':1}),
    ('mechanical',{'air_handler':1}),
    ('electrical_it',{'electrical_cabinet':1}),
])
def test_service_rooms_have_named_bodies_and_separate_clearance_volumes(space,recipes):
    b = Builder()
    z = zone(b,space)
    assert emit_service_room(b,b.level,z,[])
    report = inspect_room_layouts(b.model(z))
    assert report.counts_by_recipe == recipes
    assert not failures(report)
    assert report.status == 'unevaluated'  # No adopted quantities or equipment schedule.
    assert report.quantity_adequacy == 'unevaluated'
    assert all(group.kind not in {'desk','program_zone'} for group in b.groups.values())
    assert all(part.part_role for group in b.groups.values() if group.kind!='floor_slab'
               for part in group.instances)


def test_fixture_and_full_use_region_are_refused_in_tiny_room():
    b = Builder(1,1)
    z = zone(b)
    emit_service_room(b,b.level,z,[])
    report = inspect_room_layouts(b.model(z))
    assert report.assembly_count == 0
    assert 'LAYOUT-UNPLACED' in failures(report)
    assert len(b.room_layout_plan.spaces[0].omitted)==2


def test_actual_door_approach_is_reserved_before_fixtures_are_placed():
    b = Builder(4,4)
    z = zone(b)
    b.add('DOOR','door','program','partitions',
          BoxGeometry(center=v3(2,0,1.05),size=v3(1.2,.04,2.1)),'white')
    forbidden = placement_obstacles(b,b.level)
    assert forbidden
    emit_service_room(b,b.level,z,forbidden)
    report = inspect_room_layouts(b.model(z))
    assert report.counts_by_recipe == {'toilet':1,'basin':1}
    assert 'LAYOUT-DOOR-APPROACH' not in failures(report)


def test_clearance_obstruction_is_detected_even_when_fixture_body_is_clear():
    b = Builder()
    z = zone(b,'mechanical')
    emit_service_room(b,b.level,z,[])
    reservation = b.room_layout_plan.reservations[0]
    centre = Polygon(reservation.polygon).centroid
    b.add('BLOCKER','column','structure','frame',
          BoxGeometry(center=v3(centre.x,centre.y,1),size=v3(.2,.2,2)),'concrete')
    report = inspect_room_layouts(b.model(z))
    assert 'LAYOUT-CLEARANCE-BLOCKED' in failures(report)
    assert 'LAYOUT-BODY-CLASH' not in failures(report)


def test_full_clearance_support_detects_hole_far_from_fixture_feet():
    b = Builder()
    z = zone(b,'electrical_it')
    emit_service_room(b,b.level,z,[])
    centre = Polygon(b.room_layout_plan.reservations[0].polygon).centroid
    b.groups['SLAB'].instances[0].geometry = ExtrusionGeometry(
        boundary=b.level.plate,z_base=-.2,z_top=0,
        holes=[[v2(x,y) for x,y in list(box(centre.x-.15,centre.y-.15,
                                         centre.x+.15,centre.y+.15).exterior.coords)[:-1]]])
    report = inspect_room_layouts(b.model(z))
    assert 'LAYOUT-CLEARANCE-SUPPORT' in failures(report)
    assert 'LAYOUT-FLOOR-SUPPORT' not in failures(report)


def test_incomplete_assembly_and_floating_base_do_not_pass():
    b = Builder()
    z = zone(b)
    emit_service_room(b,b.level,z,[])
    first = b.room_layout_plan.assemblies[0]
    del b.groups[first.assembly_id+'-PART-bowl_front']
    second = b.room_layout_plan.assemblies[1]
    pedestal = b.groups[second.assembly_id+'-PART-pedestal'].instances[0]
    pedestal.geometry.center.z += .1
    report = inspect_room_layouts(b.model(z))
    assert {'LAYOUT-ASSEMBLY','LAYOUT-FLOOR-SUPPORT'} <= failures(report)


def test_later_fixture_body_in_door_approach_is_reported():
    b = Builder()
    z = zone(b,'mechanical')
    emit_service_room(b,b.level,z,[])
    body = next(group.instances[0].geometry for group in b.groups.values()
                if group.kind=='mechanical_equipment')
    b.add('LATER-DOOR','door','program','partitions',
        BoxGeometry(center=v3(body.center.x,body.center.y,1.05),size=v3(1.2,.04,2.1)),'white')
    report = inspect_room_layouts(b.model(z))
    assert 'LAYOUT-DOOR-APPROACH' in failures(report)


def auditorium(direction=1):
    b = Builder(12,10)
    z = zone(b,'auditorium')
    rows = [BowlRow(index=index,offset_front_m=2.7+index*ROW_DEPTH_M,
        offset_back_m=2.7+(index+1)*ROW_DEPTH_M,
        distance_m=2.7+index*ROW_DEPTH_M+SEAT_LINE_OFFSET_M,
        floor_m=.25*index,eye_m=1.2+.25*index) for index in range(5)]
    carve = NS(house=(0,0,12,10),zones=[z],rows=rows,
               proscenium_x=0 if direction>0 else 12,audience_dx=direction)
    emit_theatre_floor(b,carve)
    return b,z


@pytest.mark.parametrize('direction',[-1,1])
def test_every_bowl_row_gets_complete_seats_and_connected_aisle_reservations(direction):
    b,z = auditorium(direction)
    emit_auditorium_seating(b,b.level,z)
    report = inspect_room_layouts(b.model(z))
    assert report.counts_by_recipe['theatre_seat'] == 40
    assert report.counts_by_recipe['companion_seat'] == 2
    assert not failures(report)
    assert len([r for r in b.room_layout_plan.reservations if r.purpose=='longitudinal_aisle'])==42
    assert len([r for r in b.room_layout_plan.reservations if r.purpose=='cross_aisle'])==2
    assert len([r for r in b.room_layout_plan.reservations if r.purpose=='wheelchair_position'])==2
    assert any(group.subsystem=='auditorium_handrail' for group in b.groups.values())
    assert all(len(intent.required_roles)==6 for intent in b.room_layout_plan.assemblies)


@pytest.mark.parametrize('mutation',['missing','moved'])
def test_rail_solid_bearing_is_measured_at_both_real_posts(mutation):
    from backend.app.dependencies import rail_solid_bearings
    b,z = auditorium()
    emit_auditorium_seating(b,b.level,z)
    connected,failed = rail_solid_bearings(b.groups.values())
    assert connected and not failed
    identifier = sorted(connected)[0]
    member = b.groups[identifier].instances[0]
    post = member.supports[0]
    if mutation=='missing':
        del b.groups[post]
    else:
        b.groups[post].instances[0].geometry.center.y += .01
        b.groups[post].instances[0].geometry.center.x += .05
    connected,failed = rail_solid_bearings(b.groups.values())
    assert identifier in failed and identifier not in connected


def test_auditorium_handrail_endpoints_survive_element_group_json_round_trip():
    from backend.app.dependencies import rail_solid_bearings

    b,z = auditorium()
    emit_auditorium_seating(b,b.level,z)
    round_tripped = [
        ElementGroup.model_validate_json(group.model_dump_json())
        for group in b.groups.values()
    ]
    connected, failed = rail_solid_bearings(round_tripped)
    assert connected
    assert not failed


def test_seat_or_aisle_at_removed_floor_is_a_failure():
    b,z = auditorium()
    emit_auditorium_seating(b,b.level,z)
    del b.groups['PRG-BWL-L01-R03-B0']
    report = inspect_room_layouts(b.model(z))
    assert {'LAYOUT-FLOOR-SUPPORT','LAYOUT-CLEARANCE-SUPPORT'} <= failures(report)


def test_auditorium_without_risers_never_claims_zero_seats_is_complete():
    b = Builder()
    z = zone(b,'auditorium')
    emit_auditorium_seating(b,b.level,z)
    report = inspect_room_layouts(b.model(z))
    assert 'LAYOUT-UNPLACED' in failures(report)
    assert report.assembly_count==0


def test_missing_room_plan_is_detected_from_the_actual_allocation():
    b = Builder()
    report = inspect_room_layouts(b.model(zone(b)))
    assert 'LAYOUT-MISSING-ROOM' in failures(report)


def test_recipe_typo_is_not_replaced_with_an_arbitrary_desk():
    with pytest.raises(ValueError,match='Unknown room fixture recipe'):
        fixture_recipe('toielt')


def test_split_bowl_has_intermediate_steps_and_no_overlapping_concrete_pieces():
    b,z=auditorium()
    floor=[item for group in b.groups.values()
           if group.kind in {'auditorium_riser','auditorium_aisle'} for item in group.instances]
    assert any(_z_interval(item.geometry)[1]==pytest.approx(.125) for item in floor)
    for index,a in enumerate(floor):
        az=_z_interval(a.geometry)
        for other in floor[index+1:]:
            bz=_z_interval(other.geometry)
            if min(az[1],bz[1])-max(az[0],bz[0])>1e-5:
                assert _polygon(a.geometry).intersection(_polygon(other.geometry)).area<1e-7


def test_whole_depth_seating_runs_fit_around_obstruction_without_fake_missing_seats():
    b,z=auditorium()
    row,front,back,top=b.theatre_layout.rows[0]
    a,end=b.theatre_layout.seat_bands[0]
    b.add('ROW-OBSTACLE','column','structure','frame',
        BoxGeometry(center=v3(front+SEAT_LINE_OFFSET_M,(a+end)/2,.7),
                    size=v3(.15,.18,1.4)),'concrete')
    emit_auditorium_seating(b,b.level,z)
    report=inspect_room_layouts(b.model(z))
    assert 0<report.counts_by_recipe['theatre_seat']<=40
    assert not any(key.startswith('PRG-TSEA-') for key in b.room_layout_plan.spaces[0].omitted)
    assert 'LAYOUT-BODY-CLASH' not in failures(report)


def test_detached_wheelchair_bay_does_not_claim_a_route_to_cross_aisle():
    b,z=auditorium()
    emit_auditorium_seating(b,b.level,z)
    bay=next(r for r in b.room_layout_plan.reservations if r.purpose=='wheelchair_position')
    bay.polygon=[(x-.1,y) for x,y in bay.polygon]
    assert 'LAYOUT-ROW-ACCESS' in failures(inspect_room_layouts(b.model(z)))
