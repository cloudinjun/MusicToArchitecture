"""Shared public-floor identity never cancels an independent separation."""
from types import SimpleNamespace as NS

import pytest


@pytest.mark.parametrize('neighbour_type,rating,opens',[
    (None,0.,True),(None,1.,False),('auditorium',0.,False),('mechanical',1.,False)])
def test_shared_crossing_applies_only_to_unrated_commons_interface(
        monkeypatch,neighbour_type,rating,opens):
    from backend.app import compiler_v3 as compiler, portals, shared_boundaries
    from backend.app.partitions import required_separation
    zone=NS(space_id='FOYER',space_type='theatre_foyer',category='circulation',
            area_delivered_m2=22.,level_id='L01')
    neighbour=(NS(space_id='OTHER',space_type=neighbour_type,category='public')
               if neighbour_type else None)
    requirement=required_separation('theatre_foyer',neighbour_type or 'circulation',
        category_a='circulation',category_b='public',storeys=4,sprinklered=True,
        area_a_m2=22.).model_copy(update={'fire_rating_hours':rating})
    assert requirement.stc_target > 40
    monkeypatch.setattr(compiler,'required_separation',lambda *a,**kw:requirement)
    monkeypatch.setattr(portals,'split_room_edges',lambda zones:[(zone,neighbour,'N',(0.,0.,4.,0.))])
    calls=[]
    def split(*args):
        calls.append(args)
        return [((0.,0.,1.,0.),False),((1.,0.,3.,0.),True),((3.,0.,4.,0.),False)]
    monkeypatch.setattr(shared_boundaries,'split_shared_route_boundary',split)
    monkeypatch.setattr(compiler,'_clear_of_cores',lambda *args:[args[:4]])
    monkeypatch.setattr(portals,'matching_entrances',lambda *a:[])
    monkeypatch.setattr(portals,'wall_run_parts',lambda *a:[])
    monkeypatch.setattr(portals,'choose_partition_opening',lambda *a:None)
    emitted=[]
    monkeypatch.setattr(compiler,'_emit_partition_run',lambda *a,**kw:emitted.append(a))
    level=NS(id='L01',index=1,z=0.)
    builder=NS(lattice=NS(occupied=[level]),groups={},profiles={},
        datums=NS(value=lambda key:4. if key=='floor_to_floor_m' else .2))
    compiler._emit_partitions(builder,NS(zones=[zone]),True)
    assert bool(calls)==opens
    assert [tuple(args[5:9]) for args in emitted] == (
        [(0.,0.,1.,0.),(3.,0.,4.,0.)] if opens else [(0.,0.,4.,0.)])
    assert all(args[3] is requirement for args in emitted)
