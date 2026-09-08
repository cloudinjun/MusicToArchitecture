from __future__ import annotations

from backend.app.layout_search import search_layout


def test_storeys_share_geometric_trials_without_losing_rejection_signals():
    from backend.app.layout_search import interleave_trials
    def blocked_floor():
        yield None
        yield None
        yield 'later-L02'
    stream = interleave_trials([blocked_floor(), iter(['shared-L03']), iter(['shared-L04'])])
    assert list(stream) == [None, 'shared-L03', 'shared-L04', None, 'later-L02']


def test_last_room_budget_failure_rolls_back_its_route_and_tries_another_batch():
    def proposals(item, path):
        yield (8, 5)  # Room and oversized new corridor.
        yield (8, 1)  # Same room, a shared shorter connection.
    result = search_layout(['room'], [3], proposals, max_nodes=2,
                           accept=lambda path: sum(path) <= 12)
    assert result.complete and result.nodes == 2
    assert result.placed == [3, 8, 1]


def test_rejected_budget_batch_spends_node_without_becoming_partial_evidence():
    result = search_layout(['room'], [3], lambda *_: [(8, 5)], max_nodes=1,
                           accept=lambda path: sum(path) <= 12, fair_roots=True)
    assert not result.complete and result.exhausted
    assert result.nodes == 1 and result.placed == [3] and result.unplaced == ['room']


def test_joint_search_services_another_hall_before_a_stalled_room_drains_work():
    work = []
    def proposals(item,path):
        if item == 'hall':
            yield ('hall-a','gallery-a','clearance-a')
            yield ('hall-b','gallery-b','clearance-b')
        elif 'hall-a' in path:
            for index in range(100):
                work.append(index)
                yield None
        else:
            yield ('room','room-route')
    result = search_layout(['hall','room'],['core'],proposals,max_nodes=4,fair_roots=True)
    assert result.complete and result.nodes == 3
    assert len(work) < 100
    assert result.placed == ['core','hall-b','gallery-b','clearance-b','room','room-route']
    assert result.unplaced == []


def test_joint_search_keeps_global_budget_and_best_complete_batch():
    def proposals(item,path):
        if item == 'hall':
            yield ('hall-a','gallery-a')
            raise AssertionError('another root requested beyond the node budget')
        yield ('room',)
    result = search_layout(['hall','room'],['core'],proposals,max_nodes=1,fair_roots=True)
    assert result.exhausted and not result.complete and result.nodes == 1
    assert result.placed == ['core','hall-a','gallery-a']
    assert result.unplaced == ['room']


def test_deadline_inside_geometry_preserves_last_complete_room_route_batch():
    from backend.app.layout_search import SearchDeadline
    now = [0.0]
    deadline = SearchDeadline(2.0, clock=lambda: now[0])

    def proposals(item, current):
        if item == 'a':
            yield ('room-a', 'route-a')
        else:
            # An expensive iterator can expire without ever yielding a node.
            now[0] = 2.0
            deadline.check()
            yield ('room-b', 'route-b')

    initial = ['core']
    result = search_layout(['a','b'], initial, proposals, max_nodes=50,
                           checkpoint=deadline.check)
    assert result.timed_out and not result.complete and not result.exhausted
    assert result.placed == ['core', 'room-a', 'route-a']
    assert result.unplaced == ['b'] and result.nodes == 1
    assert initial == ['core']


def test_search_does_not_swallow_unrelated_geometry_errors():
    import pytest

    def proposals(item, current):
        raise ValueError('invalid polygon')
        yield ()

    with pytest.raises(ValueError, match='invalid polygon'):
        search_layout(['a'], [], proposals, max_nodes=1)


def test_search_backtracks_a_room_and_keeps_its_route_with_the_selected_batch():
    items = ("room-a", "room-b")
    initial = ["core"]
    seen = []

    def proposals(item, current):
        seen.append((item, tuple(current)))
        if item == "room-a":
            yield ("a-blocked", "route-to-blocked")
            yield ("a-open", "route-to-open")
        elif "a-open" in current:
            yield ("b", "route-to-b")

    result = search_layout(items, initial, proposals, max_nodes=10)

    assert result.complete is True
    assert result.exhausted is False
    assert result.nodes == 3
    assert result.unplaced == []
    assert result.placed == ["core", "a-open", "route-to-open", "b", "route-to-b"]
    assert "route-to-blocked" not in result.placed
    assert initial == ["core"]
    assert seen == [
        ("room-a", ("core",)),
        ("room-b", ("core", "a-blocked", "route-to-blocked")),
        ("room-b", ("core", "a-open", "route-to-open")),
    ]


def test_node_budget_is_strict_and_returns_best_partial_path():
    initial = ["core"]

    def proposals(item, current):
        if item == "room-a":
            yield ("a", "route-a")
        else:
            yield ("b", "route-b")

    result = search_layout(("room-a", "room-b"), initial, proposals, max_nodes=1)

    assert result.complete is False
    assert result.exhausted is True
    assert result.nodes == 1
    assert result.placed == ["core", "a", "route-a"]
    assert result.unplaced == ["room-b"]
    assert initial == ["core"]


def test_empty_proposal_domain_is_incomplete_without_exhausting_budget():
    initial = ["core"]

    def proposals(item, current):
        if item == "room-a":
            return
        yield (item,)

    result = search_layout(("room-a", "room-b"), initial, proposals, max_nodes=4)

    assert result.complete is False
    assert result.exhausted is False
    assert result.nodes == 0
    assert result.placed == initial
    assert result.unplaced == ["room-a", "room-b"]


def test_failed_sibling_routes_do_not_mutate_initial_or_selected_path():
    initial = [{"kind": "core"}]

    def proposals(item, current):
        if item == "room-a":
            yield ({"kind": "room", "id": "blocked"},
                   {"kind": "route", "id": "bad-route"})
            yield ({"kind": "room", "id": "open"},
                   {"kind": "route", "id": "good-route"})
            return
        if any(record.get("id") == "open" for record in current if isinstance(record, dict)):
            yield ({"kind": "room", "id": "b"},
                   {"kind": "route", "id": "b-route"})

    result = search_layout(("room-a", "room-b"), initial, proposals, max_nodes=10)

    assert result.complete is True
    assert [record.get("id") for record in result.placed[1:] if "id" in record] == [
        "open", "good-route", "b", "b-route"
    ]
    assert initial == [{"kind": "core"}]
