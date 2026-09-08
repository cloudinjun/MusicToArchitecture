"""Arrival rails respect the landing plane by their physical section."""
import math
import pytest

from backend.app.compiler_v3 import _emit_flight
from backend.app.geometry import v3
from backend.app.mesh_primitives import primitive_mesh
from backend.tests.test_envelope_closure import builder,elements


@pytest.mark.parametrize('angle',[0.,math.pi/2,math.pi/4])
def test_clear_landing_keeps_rail_bodies_on_flight_side_without_moving_treads(angle):
    direction = math.cos(angle),math.sin(angle)
    start,end = v3(0.,0.,0.),v3(.6*direction[0],.6*direction[1],.3)
    versions=[]
    for clear in (False,True):
        b=builder(datum_updates={'riser_m':.175,'rail_height_m':1.1,'rail_post_spacing_m':1.2})
        _emit_flight(b,'F01',start,end,1.56,'L00',clear_end_landing=clear)
        versions.append(b)
    before,after=versions
    fixed=lambda b:{e.id:e.geometry.model_dump() for e in elements(b)
                    if e.kind in ('stair_tread','stair_stringer')}
    assert fixed(before)==fixed(after)
    assert {e.id for e in elements(before)}=={e.id for e in elements(after)}

    def normal_reach(b):
        profiles={k:p.model_dump() for k,p in b.profiles.items()}
        points=[v for e in elements(b) if e.kind=='railing'
                for v in primitive_mesh(e.geometry.model_dump(),profiles)[0]]
        return max((x-end.x)*direction[0]+(y-end.y)*direction[1] for x,y,z in points)
    assert normal_reach(before)>0
    assert normal_reach(after)<=1e-7
