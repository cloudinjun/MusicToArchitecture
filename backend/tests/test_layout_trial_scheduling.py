"""Trial scheduling keeps rejected layout work visible to the bounded search."""

from __future__ import annotations

import pytest
from shapely.geometry import box

from backend.app.legacy_program_layout import _placement_trials, _placements


def test_shared_access_precedes_detached_ellipse_preference_without_snapping_to_grid():
    domain, street = box(0,0,12,10), box(0,0,12,1.8)
    options = _placements(domain,[street],3,2,(8,7),accept=lambda _:True,
                          access_rects=[street.bounds],access_width=1.8)
    first = next(options)
    assert first.area == pytest.approx(6)
    assert first.bounds[1] == 1.8
    assert first.boundary.intersection(street.boundary).length >= 1.8
    assert first.bounds[0] == 6.5  # Free musical XY preference remains along that frontage.
    assert domain.covers(first) and first.intersection(street).area == 0


def test_short_face_contact_does_not_replace_full_width_access():
    street = box(0,0,1,1)
    options = _placements(box(0,0,12,10),[street],3,2,(8,7),accept=lambda _:True,
                          access_rects=[street.bounds],access_width=1.8)
    # Every contact is too short, so the original free-XY preference wins.
    assert next(options).bounds == (6.5,6.,9.5,8.)


def test_legal_rejection_yields_after_one_accept_call_and_later_accepts_appear():
    domain = box(0, 0, 4, 4)
    calls = []

    def accept_after_first(rect):
        calls.append(rect.bounds)
        return len(calls) >= 2

    trials = _placement_trials(
        domain, [], 2, 2, (1, 1), accept=accept_after_first)

    first = next(trials)
    assert first is None
    assert len(calls) == 1

    second = next(trials)
    assert second is not None
    assert len(calls) == 2


def test_geometric_rejection_yields_none_before_route_acceptance():
    # The preferred rectangle lies in the missing lower-left quadrant. The
    # generator must expose that rejected attempt instead of scanning ahead.
    domain = box(0, 0, 4, 4).difference(box(0, 0, 2, 2))
    calls = []

    def accept(rect):
        calls.append(rect.bounds)
        return True

    trials = _placement_trials(domain, [], 2, 2, (1, 1), accept=accept)

    assert next(trials) is None
    assert calls == []
    assert any(rect is not None for rect in trials)


def test_placements_filters_none_without_changing_accepted_order_or_bounds():
    domain = box(0, 0, 4, 4)

    def accept_left_half(rect):
        return rect.bounds[0] < 1.0

    trials = list(_placement_trials(
        domain, [], 2, 2, (1, 1), accept=accept_left_half))
    placements = list(_placements(
        domain, [], 2, 2, (1, 1), accept=accept_left_half))

    expected = [rect for rect in trials if rect is not None]
    assert any(rect is None for rect in trials)
    assert [rect.bounds for rect in placements] == [rect.bounds for rect in expected]


def test_placement_trials_preserve_domain_and_non_overlap_constraints():
    domain = box(0, 0, 6, 6)
    occupied = [box(2, 2, 4, 4)]
    trials = list(_placement_trials(
        domain, occupied, 2, 2, (3, 3), accept=lambda _rect: True))
    placements = [rect for rect in trials if rect is not None]

    assert trials[0] is None  # preferred rectangle overlaps the occupied room
    assert placements
    for rect in placements:
        assert domain.covers(rect)
        assert rect.intersection(occupied[0]).area < 1e-7
