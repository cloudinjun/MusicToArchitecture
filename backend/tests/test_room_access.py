"""Upstream access proposals and compiler terminals share the same arithmetic."""
from types import SimpleNamespace

import pytest
from shapely.geometry import box

from backend.app.compiler_v3 import _preplaced_terminal_points
from backend.app.room_access import front_cross_aisle_bounds, owner_terminal_points


@pytest.mark.parametrize('clearance', [1e-5, 0.0])
def test_owner_terminal_order_radius_and_boundary_clearance(clearance):
    assert owner_terminal_points((2., 3., 10., 9.), .75,
                                 boundary_clearance_m=clearance) == [
        (6., 3.-.75-clearance), (6., 9.+.75+clearance),
        (2.-.75-clearance, 6.), (10.+.75+clearance, 6.)]


@pytest.mark.parametrize('front,expected', [(2., 2.), (7., 7.), (10., 10.), (11., 6.), (None, 6.)])
def test_front_station_only_moves_south_and_north_terminals_within_owner(front, expected):
    points = owner_terminal_points((2., 3., 10., 9.), .75, front_x=front)
    assert [p[0] for p in points[:2]] == [expected, expected]
    assert points[2:] == owner_terminal_points((2., 3., 10., 9.), .75)[2:]


def test_compiler_wrapper_preserves_exact_owner_and_legacy_fallback():
    zone = SimpleNamespace(x0=15.397, y0=1.4, x1=19.396, y1=8.9)
    owner = box(15.3967, 1.4, 19.3967, 8.9)
    assert _preplaced_terminal_points(zone, .745, owner=owner, front_x=17.) == (
        owner_terminal_points(owner.bounds, .745, front_x=17.))
    assert _preplaced_terminal_points(zone, .745) == owner_terminal_points(
        (zone.x0, zone.y0, zone.x1, zone.y1), .745)
    assert _preplaced_terminal_points(zone, .745, owner=owner)[3] == pytest.approx((20.14171, 5.15))


@pytest.mark.parametrize('direction,expected', [(1., (7.2, 9.)), (-1., (9., 10.8))])
def test_front_cross_aisle_keeps_full_width_on_either_side_of_first_row(direction, expected):
    interval = front_cross_aisle_bounds(9., direction, 1.8)
    assert interval == pytest.approx(expected)
    assert interval[1]-interval[0] == pytest.approx(1.8)
