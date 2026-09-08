"""Whole-composition freedoms retain spatial ownership and real access widths."""
import pytest
from shapely.geometry import box
from shapely.ops import unary_union

from backend.app.legacy_program_layout import _connect_room, LayoutRejected
from backend.tests.test_legacy_program_layout import _brief, _score, _organize


def test_exact_width_existing_landing_is_reused_without_extra_floor():
    from backend.app.legacy_program_layout import _connect_room
    room = box(4,2,5.8,10.12)
    landing = box(4,10.12,8,11.92)
    core = box(4,11.92,8,18)
    assert _connect_room(box(0,0,20,20),[core],[landing],room,1.8) == []
    assert _connect_room(box(0,0,20,20),[core],
                         [box(4,10.12,5,11.92)],room,1.8) != []


def test_hall_owners_can_use_frontage_without_full_depth_side_galleries():
    house,stage = box(0,0,8,10),box(8,0,11,10)
    limit,network = box(0,0,11,11.8),[box(0,10,11,11.8)]
    # Neither end has room for a gallery, but each owner has a full-width
    # frontage on the same public floor. The proscenium cannot be borrowed.
    assert _connect_room(limit,[stage],network,house,1.8) == []
    assert _connect_room(limit,[house],network,stage,1.8) == []
    assert _connect_room(limit,[house,box(8,10,11,11.8)],network,stage,1.8) is None


def test_explicit_owner_terminal_cannot_be_replaced_by_an_unrelated_open_face():
    room,limit = box(0,0,8,6),box(0,0,10,8)
    network = [box(0,6,2,8)]
    assert _connect_room(limit,[],network,room,1.8) == []
    links = _connect_room(limit,[],network,room,1.8,terminal_points=[(6,6.9)])
    assert links
    assert unary_union([*network,*links]).buffer(1e-7).covers(box(5.1,6,6.9,7.8))
    assert _connect_room(limit,[box(3,6,4,8)],network,room,1.8,
                         terminal_points=[(6,6.9)]) is None


def test_distributed_core_changes_whole_reservation_with_same_size(monkeypatch):
    from backend.app import layout_search
    captured = {}
    def capture(items,initial,proposals,**kwargs):
        captured['placed'] = list(initial)
        return layout_search.LayoutSearchResult(list(initial),False,0,False,list(items))
    monkeypatch.setattr(layout_search,'search_layout',capture)
    layouts = {}
    for kind in ('rear_commons','distributed_cores'):
        captured.clear()
        with pytest.raises(LayoutRejected):
            _organize(_score(),_brief(),backbone_layout=kind,stair_run_axis='x',
                core_inset_fraction=.15,lift_layout='core_front_inner',
                arrival_layout='complete_forecourt',foyer_layout='hall_front_shared')
        layouts[kind] = {p.identifier:p.shape for p in captured['placed']}
    before,after = (layouts[k]['PV-L01-CIRC-1'] for k in layouts)
    assert before.area == pytest.approx(after.area)
    assert before.bounds != after.bounds
    for level in range(1,5):
        second = layouts['distributed_cores'][f'PV-L{level:02d}-CIRC-1']
        assert second.equals(after)
        landing = layouts['distributed_cores'][f'PV-L{level:02d}-CIRC-8']
        assert second.boundary.intersection(landing.boundary).length >= 1.8
        assert _brief().massing_limit_shape.buffer(1e-7).covers(second.union(landing))


@pytest.mark.parametrize('inset',[0.,.08,.15])
def test_joint_foyer_preserves_area_and_responds_to_core_access_span(monkeypatch,inset):
    from backend.app import layout_search
    captured = []
    def capture(items,initial,proposals,**kwargs):
        captured.extend(initial)
        return layout_search.LayoutSearchResult(list(initial),False,0,False,list(items))
    monkeypatch.setattr(layout_search,'search_layout',capture)
    with pytest.raises(LayoutRejected):
        _organize(_score(),_brief(),backbone_layout='distributed_cores',stair_run_axis='x',
            core_inset_fraction=.15,secondary_core_inset_fraction=inset,
            lift_layout='core_front_inner',arrival_layout='complete_forecourt',
            foyer_layout='hall_front_shared')
    foyer = next(p for p in captured if p.spaces == ['SP-FOYER'])
    assert foyer.shape.area == pytest.approx(22)
    a,b,c,d = foyer.shape.bounds
    assert min(c-a,d-b) >= 3-1e-7
    assert foyer.shared_route_volume_ids
    for p in captured:
        if p.identifier in ('PV-L01-CIRC-0','PV-L01-CIRC-1','PV-L01-CIRC-3'):
            assert foyer.shape.intersection(p.shape).area < 1e-7


def test_complete_hall_proposal_owns_localized_full_width_access(monkeypatch):
    from backend.app import layout_search
    captured = []
    original = []
    def capture(items,initial,proposals,**kwargs):
        original.extend(initial)
        captured.extend(next(batch for batch in proposals(items[0],tuple(initial)) if batch is not None))
        return layout_search.LayoutSearchResult(list(initial),False,0,False,list(items))
    monkeypatch.setattr(layout_search,'search_layout',capture)
    with pytest.raises(LayoutRejected):
        _organize(_score(),_brief(),backbone_layout='distributed_cores',stair_run_axis='x',
            core_inset_fraction=.15,secondary_core_inset_fraction=.08,
            lift_layout='core_front_inner',arrival_layout='complete_forecourt',
            foyer_layout='hall_front_shared')
    rooms = [p for p in captured if p.role == 'archetype']
    assert sum(p.shape.area for p in rooms) == pytest.approx(110)
    assert not any('GALLERY' in p.identifier for p in captured)
    pair = unary_union([p.shape for p in rooms])
    links = [p for p in captured if p.role == 'connector']
    for p in links:
        assert pair.intersection(p.shape).area < 1e-7
        a,b,c,d = p.shape.bounds
        assert min(c-a,d-b) >= 1.8-1e-7
        assert _brief().massing_limit_shape.buffer(1e-7).covers(p.shape)
    network = unary_union([p.shape for p in original if p.category == 'circulation'
        and (not p.spaces or p.shared_route_volume_ids)
        and p.identifier not in ('PV-L01-CIRC-0','PV-L01-CIRC-1','PV-L01-CIRC-3','PV-L01-CIRC-4')
        and p.level == 0] + [p.shape for p in links])
    assert network.buffer(1e-7).geom_type == 'Polygon'
    for room in rooms:
        assert room.shape.boundary.intersection(network.boundary).length >= 1.8-1e-7
