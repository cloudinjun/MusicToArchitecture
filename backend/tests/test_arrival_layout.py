"""Whole-arrival authoring: physical reservations precede room allocation."""
import pytest
from shapely.geometry import box
from shapely.ops import unary_union

from backend.app.approach import plan_compact_arrival, local_region_to_world, PUBLIC_STAIR_TREAD_M


def _plan(origin=(4.73,10.43), tangent=(0.,-1.), outward=(-1.,0.), rise=.3):
    return plan_compact_arrival(parcel=box(0,0,25,20),origin=origin,
        tangent=tangent,outward=outward,rise_m=rise,flight_width_m=1.2,
        riser_m=.175,tread_m=PUBLIC_STAIR_TREAD_M,weather_reach_m=1.)


@pytest.mark.parametrize('origin,tangent,outward',[
    ((4.73,10.43),(0.,-1.),(-1.,0.)),
    ((20.27,10.43),(0.,1.),(1.,0.)),
    ((12.5,4.73),(1.,0.),(0.,-1.)),
])
def test_whole_arrival_fits_actual_parcel_in_boundary_frame(origin,tangent,outward):
    plan = _plan(origin,tangent,outward)
    assert plan is not None
    assert not plan.ramp.compliance()
    footprint = local_region_to_world(unary_union([box(*r) for r in plan.reserved_rects]),
                                      origin,tangent,outward)
    assert box(0,0,25,20).covers(footprint)
    assert plan.stair_end_v == plan.entry_rect[3]
    assert plan.stair_start_v-plan.stair_end_v == pytest.approx(2*PUBLIC_STAIR_TREAD_M)
    link = box(*plan.link_rect)
    top = next(p for p in plan.ramp.landings if p.kind=='top')
    assert link.intersection(box(*plan.entry_rect)).area > 0
    assert link.intersection(box(top.x-top.size_x/2,top.y-top.size_y/2,
                                 top.x+top.size_x/2,top.y+top.size_y/2)).area > 0


def test_whole_arrival_is_refused_without_parcel_depth_or_for_unimplemented_high_rise():
    assert _plan(origin=(1.75,10.43)) is None
    assert _plan(rise=3.) is None


def test_arrival_selects_other_side_when_existing_volume_blocks_first_ramp():
    origin,tangent,outward = (4.73,10.43),(0.,-1.),(-1.,0.)
    baseline = _plan(origin,tangent,outward)
    def bottom_footprint(plan):
        p = next(p for p in plan.ramp.landings if p.kind=='bottom')
        return local_region_to_world(box(p.x-p.size_x/2,p.y-p.size_y/2,
                                         p.x+p.size_x/2,p.y+p.size_y/2),
                                     origin,tangent,outward)
    def with_protection(protected):
        return plan_compact_arrival(parcel=box(0,0,25,20),origin=origin,
            tangent=tangent,outward=outward,rise_m=.3,flight_width_m=1.2,
            riser_m=.175,tread_m=PUBLIC_STAIR_TREAD_M,weather_reach_m=1.,
            protected=protected,landing_clearance_m=.29)
    protected = bottom_footprint(baseline)
    alternate = with_protection(protected)
    assert alternate is not None and not alternate.ramp.compliance()
    assert alternate.reserved_footprint(origin,tangent,outward,
        landing_clearance_m=.29).intersection(protected).area == 0
    assert alternate.ramp.width_m == baseline.ramp.width_m
    assert alternate.stair_width_m == baseline.stair_width_m
    for plan in (baseline,alternate):
        top = next(p for p in plan.ramp.landings if p.kind=='top')
        bottom = next(p for p in plan.ramp.landings if p.kind=='bottom')
        assert abs(top.x) < abs(bottom.x)
        link = box(*plan.link_rect)
        assert link.intersection(box(bottom.x-bottom.size_x/2,bottom.y-bottom.size_y/2,
                                     bottom.x+bottom.size_x/2,bottom.y+bottom.size_y/2)).area == 0
        for run in plan.ramp.runs:
            assert link.intersection(box(min(run.x_start,run.x_end),run.y-plan.ramp.pitch_m/2,
                                         max(run.x_start,run.x_end),run.y+plan.ramp.pitch_m/2)).area == 0
            assert run.direction == (1 if run.x_end>run.x_start else -1)
    assert with_protection(protected.union(bottom_footprint(alternate))) is None


def test_room_reservation_includes_downstream_landing_wall_allowance():
    from backend.app.compiler_v3 import _approach_landing_footprints, _local_rect_bounds, _transform_ramp_plan
    from backend.app.partitions import PARTITION_TYPES

    origin,tangent,outward = (4.73,10.43),(0.,-1.),(-1.,0.)
    plan = _plan(origin,tangent,outward)
    ramp = _transform_ramp_plan(plan.ramp,origin,tangent,outward)
    top = next(p for p in ramp.landings if p.kind == 'top')
    approach = {'podium_id':'L01',
        'entry':_local_rect_bounds(origin,tangent,outward,*plan.entry_rect),
        'ramp_top':(top.x-top.size_x/2,top.y-top.size_y/2,
                    top.x+top.size_x/2,top.y+top.size_y/2)}
    wall = max(p.thickness_mm for p in PARTITION_TYPES)/1000
    physical = plan.reserved_footprint(origin,tangent,outward)
    room_exclusion = plan.reserved_footprint(origin,tangent,outward,landing_clearance_m=wall)
    downstream = unary_union([box(a-wall,b-wall,c+wall,d+wall)
        for a,b,c,d in _approach_landing_footprints(approach,'L01')])
    assert room_exclusion.symmetric_difference(physical.union(downstream)).area < 1e-7
    assert room_exclusion.difference(physical).area > 0
    # The old proposal touched the arrival slab but occupied its wall allowance.
    old_room = box(2.0633,6.23,4.73,9.23)
    assert old_room.intersection(physical).area < 1e-7
    assert old_room.intersection(room_exclusion).area > .49


def test_shared_arrival_survives_real_volume_and_spatial_boundaries():
    from backend.tests.test_legacy_program_layout import _brief, _score, _organize
    from backend.app.program_massing import prepare_massing
    from backend.app.envelope import planned_entrance
    from backend.app.compiler_v3 import _plan_approach

    score,brief = _score(),_brief()
    volumes = _organize(score,brief,core_inset_fraction=.15,
        lift_layout='core_front_inner',arrival_layout='west_forecourt',
        foyer_layout='hall_front_shared',room_groups=[{
            'space_ids':['SP-FIRE','SP-REFUSE'],'axis':'y','reason':'Shared-width service strip'}])
    foyer = next(v for v in volumes.volumes if 'SP-FOYER' in v.space_ids)
    footprint = box(*volumes.rect_of(foyer))
    # Final room branches can join a commons after it was first authored. Every
    # intersecting route must survive in that owner's frozen sharing record.
    for route in volumes.volumes:
        if route.level_id==foyer.level_id and route.role in ('circulation_spine','connector'):
            if footprint.intersection(box(*volumes.rect_of(route))).area > 1e-7:
                assert route.id in foyer.shared_route_volume_ids
    prepared = prepare_massing(volumes.to_program_massing(),score=score)
    assert prepared.allocation.fits
    assert not prepared.allocation.public_circulation.unresolved
    zone = next(z for z in prepared.allocation.zones if z.space_id=='SP-FOYER')
    assert zone.area_delivered_m2 == 22.
    assert (zone.x0,zone.y0,zone.x1,zone.y1) == pytest.approx(footprint.bounds)
    approach = _plan_approach(prepared.lattice,prepared.datums)
    assert approach['arrival_assembly'] == volumes.circulation_intent.arrival_assembly
    assert planned_entrance(prepared.lattice,prepared.datums,approach) is not None
