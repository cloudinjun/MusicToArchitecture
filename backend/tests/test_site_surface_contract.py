"""The parcel reaches real site geometry without a second fixed display plinth."""
import pytest
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from backend.app.approach import site_approach_finding
from backend.app.compiler_v3 import _emit_site
from backend.app.geometry import BoxGeometry, v3
from backend.app.physical_geometry import physical_projection
from backend.tests.test_envelope_closure import builder, elements, ring


def site_builder(parcel, rise=.3):
    b = builder(datum_updates={'slab_thickness_m':.3})
    b.lattice.site_boundary = ring(parcel)
    b.lattice.levels[1].z = rise
    b.approach = {'podium_id':'L01','entry':(-1,2,1,4),'access':None,'ramp_top':None}
    return b


@pytest.mark.parametrize('parcel', [
    [(-2,-2),(15,-2),(15,10),(-2,10)],
    [(-2,-2),(15,-2),(15,10),(6,10),(6,9),(-2,9)],
])
def test_site_paving_and_earth_use_parcel_and_release_floor_ownership(parcel):
    b = site_builder(parcel)
    _emit_site(b)
    emitted = elements(b)
    earth = unary_union([physical_projection(e.geometry).footprint for e in emitted
                         if e.kind == 'site_ground'])
    paving = unary_union([physical_projection(e.geometry).footprint for e in emitted
                          if e.kind == 'podium_slab'])
    expected = Polygon(parcel).difference(box(0,0,12,8).union(box(-1,2,1,4)))
    assert earth.equals(Polygon(parcel))
    assert paving.symmetric_difference(expected).area < 1e-8
    assert not any(e.kind == 'site_step' for e in emitted)
    assert all(e.geometry.z_top == pytest.approx(0.) for e in emitted if e.kind=='podium_slab')


def test_lifted_building_keeps_ground_paving_below_it():
    parcel = [(-2,-2),(15,-2),(15,10),(-2,10)]
    b = site_builder(parcel,rise=4.)
    _emit_site(b)
    paving = unary_union([physical_projection(e.geometry).footprint for e in elements(b)
                          if e.kind=='podium_slab'])
    assert paving.equals(Polygon(parcel))


@pytest.mark.parametrize('rise',[.3,.6])
def test_paving_reads_complete_frozen_arrival_without_removing_lifted_floor_projection(rise):
    from backend.app.approach import plan_compact_arrival, local_region_to_world
    parcel = [(0,0),(25,0),(25,20),(0,20)]
    b = site_builder(parcel,rise=rise)
    origin,tangent,outward = (12.,4.),(0.,1.),(1.,0.)
    assembly = plan_compact_arrival(parcel=Polygon(parcel),origin=origin,tangent=tangent,
        outward=outward,rise_m=rise,flight_width_m=1.2,riser_m=.175,
        tread_m=.3,weather_reach_m=1.)
    assert assembly is not None
    claim = assembly.reserved_footprint(origin,tangent,outward)
    b.approach.update(arrival_assembly=assembly,entry_point=origin,
        entry_tangent=tangent,entry_outward=outward,
        entry=local_region_to_world(box(*assembly.entry_rect),origin,tangent,outward).bounds)
    _emit_site(b)
    paving = unary_union([physical_projection(e.geometry).footprint for e in elements(b)
                          if e.kind=='podium_slab'])
    expected = Polygon(parcel).difference(claim.union(box(0,0,12,8)) if rise==.3 else claim)
    assert paving.symmetric_difference(expected).area < 1e-8
    assert paving.intersection(claim).area < 1e-8


@pytest.mark.parametrize('cx,expected', [(0,'passed'),(-2,'failed')])
def test_external_stair_exception_does_not_waive_parcel(cx,expected):
    b = site_builder([(-2,-2),(15,-2),(15,10),(-2,10)])
    b.add('ENTRY','stair_landing','circulation','entry',
          BoxGeometry(center=v3(cx,3,.2),size=v3(2,2,.2)),'white')
    assert site_approach_finding(b,['ENTRY']).status == expected
    assert site_approach_finding(b,['ABSENT']).status == 'unevaluated'
