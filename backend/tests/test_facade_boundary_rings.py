"""All weather rings and actual caps participate in the same envelope interface."""
from types import SimpleNamespace

import pytest
from shapely.geometry import Point, Polygon

from backend.app import envelope
from backend.app.facade_control import facade_control_for
from backend.app.grammar_specs import spec_for
from backend.app.geometry import ExtrusionGeometry
from backend.app.tectonics import ENVELOPE_TECTONICS
from backend.tests.test_envelope_closure import (
    RECT, builder, elements, horizontal_section, ring,
)


def test_courtyard_receives_the_selected_facade_and_normals_face_the_void(monkeypatch):
    hole = ring([(3,2),(9,2),(9,6),(3,6)])
    b = builder(slab_holes={1:[hole],2:[hole]},datum_updates={'envelope_offset_m':.4})
    for level in b.lattice.levels[1:]:
        level.voids = [hole]
    b.lattice.program_volume_source_digest = 'courtyard-regression'
    env,spec = ENVELOPE_TECTONICS['ENV-CURTAIN-WALL'],spec_for('FCD-01-INTERNATIONAL-STYLE')
    b.lattice.facade_control = facade_control_for(b.lattice,b.datums,env,spec)
    seen = []
    original = envelope._bay_subdivided
    def record(builder,bay,*args,**kwargs):
        if bay.index['boundary_ring']:
            seen.append(bay)
        return original(builder,bay,*args,**kwargs)
    monkeypatch.setattr(envelope,'_bay_subdivided',record)
    envelope.emit_envelope(b,env,spec)
    weather = Polygon(b.lattice.facade_control.level('L01').weather_voids[0])
    assert seen
    for bay in seen:
        mid = bay.at(.5,5.)
        dx,dy = bay.outward(.01)
        assert weather.contains(Point(mid.x+dx,mid.y+dy))
    cut = horizontal_section(b,5.)
    assert weather.boundary.difference(cut.buffer(1e-6)).length < 1e-5
    inner_ids = {e.id for e in elements(b) if e.lattice_index.get('boundary_ring')}
    assert any(e.id in inner_ids and e.kind=='mullion' and e.supports for e in elements(b))


def test_return_reads_the_real_hall_cap_without_bridging_its_clear_airspace():
    retained = ring([(0,0),(6,0),(6,8),(0,8)])
    cap = ring([(6,0),(12,0),(12,8),(6,8)])
    b = builder([RECT,RECT,retained])
    b.lattice.facade_control = SimpleNamespace(grammar_id='TEST-FACADE')
    b.lattice.carved = {1:[(6.,0.,12.,8.)]}
    b.add_plate('HALL-CAP','roof_deck','envelope','hall_enclosure',cap,[],7.7,8.,
                'white',level_id='L02')
    skin = ring([(-.7,-.7),(12.7,-.7),(12.7,8.7),(-.7,8.7)])
    envelope._emit_level_returns(b,b.lattice.levels[1],b.lattice.levels[2],skin,
        ring([(12.7,4)]),ENVELOPE_TECTONICS['ENV-CURTAIN-WALL'])
    tie = next(e for e in elements(b) if e.id=='ENV-RET-L01-HEAD-S000')
    assert tie.supports == ['HALL-CAP']
    assert tie.geometry.path[0].x == pytest.approx(12.)
    assert tie.id in envelope.closure_solid_bearings(b)[0]


def test_return_topology_registration_removes_only_subprecision_hairpin():
    source = Polygon([(0,0),(4,0),(4,4),(0,4),(0,2),(3,2),
                      (3,2-1e-14),(0,2-1e-14)])
    assert source.is_valid
    solids = envelope._registered_return_solids(source,0.,.075)
    assert solids
    projected = [envelope._surface_polygon(s.boundary,s.holes) for s in solids]
    assert all(p.is_valid for p in projected)
    assert sum(p.area for p in projected) == pytest.approx(source.area,abs=1e-9)


@pytest.mark.parametrize('bounds,z,expected', [
    ((12,2,12.5,6),3.7,['SLAB']),
    ((12,8,12.5,8.5),3.7,[]),  # corner contact alone
    ((12,2,14,6),3.7,[]),       # entire return exceeds collar
    ((12,2,12.5,6),4.1,[]),     # no shared vertical face
])
def test_direct_edge_host_requires_whole_panel_reach_and_face_contact(bounds,z,expected):
    from shapely.geometry import box
    x0,y0,x1,y1 = bounds
    solid = ExtrusionGeometry(boundary=RECT,holes=[],z_base=3.7,z_top=4.)
    panel = ExtrusionGeometry(boundary=ring([(x0,y0),(x1,y0),(x1,y1),(x0,y1)]),
                              holes=[],z_base=z,z_top=z+.075)
    assert envelope._direct_return_hosts(panel,[('SLAB',solid,box(0,0,12,8))],.7) == expected
