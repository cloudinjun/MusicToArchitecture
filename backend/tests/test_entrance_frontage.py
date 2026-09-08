"""Pure geometry tests for the entrance's named frontage interval."""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon

from backend.app.envelope import entrance_frontage_interval
from backend.app.geometry import v2


def _edge_measure(boundary, interval):
    edge, low, high = interval
    a = boundary[edge]
    b = boundary[(edge + 1) % len(boundary)]
    length = math.hypot(b.x - a.x, b.y - a.y)
    midpoint = (low + high) / 2.0
    projected = (a.x + (b.x - a.x) * midpoint,
                 a.y + (b.y - a.y) * midpoint)
    return (high - low) * length, projected


def test_frontage_interval_reserves_clear_width_and_both_jambs():
    boundary = [v2(0, 0), v2(10, 0), v2(10, 6), v2(0, 6)]

    interval = entrance_frontage_interval(
        boundary, (5, 0), (1, 0), clear_width=3.3, jamb_width=0.3)

    assert interval is not None
    edge, low, high = interval
    assert edge == 0
    assert (high - low) * 10.0 == pytest.approx(3.3 + 2 * 0.3)
    assert low == pytest.approx(0.305)
    assert high == pytest.approx(0.695)
    assert _edge_measure(boundary, interval)[1] == pytest.approx((5.0, 0.0))


def test_short_edge_rejects_when_clear_width_alone_cannot_fit():
    boundary = [v2(0, 0), v2(3.2, 0), v2(3.2, 6), v2(0, 6)]

    assert entrance_frontage_interval(
        boundary, (1.6, 0), (1, 0), clear_width=3.3, jamb_width=0.0) is None


def test_exact_jamb_contact_survives_float_arithmetic_but_one_mm_shortfall_fails():
    boundary = [v2(1.93,7.460000000000001),v2(1.93,12.760000000000002),
                v2(0,12.760000000000002),v2(0,7.460000000000001)]
    assert entrance_frontage_interval(boundary,(2.93,11.110000000000001),
        (0,-1),clear_width=2.5,jamb_width=.4) is not None
    assert entrance_frontage_interval(boundary,(2.93,11.111000000000001),
        (0,-1),clear_width=2.5,jamb_width=.4) is None


def test_short_edge_rejects_jamb_capacity_after_clear_width_check():
    boundary = [v2(0, 0), v2(3.5, 0), v2(3.5, 6), v2(0, 6)]

    assert entrance_frontage_interval(
        boundary, (1.75, 0), (1, 0), clear_width=3.3, jamb_width=0.2) is None


def test_concave_adjoining_protrusion_loses_frontage_after_square_offset():
    source = Polygon([
        (0, 0), (4, 0), (4, 2), (6, 2),
        (6, 0), (10, 0), (10, 6), (0, 6),
    ])
    offset = source.buffer(0.5, join_style=2)
    boundary = [v2(float(x), float(y))
                for x, y in list(offset.exterior.coords)[:-1]]

    # The adjoining concave protrusion leaves two short parallel edge pieces;
    # the named centre cannot be shifted to the distant full-width wall.
    assert entrance_frontage_interval(
        boundary, (5, 0), (1, 0), clear_width=3.3, jamb_width=0.3) is None


def test_frontage_measure_is_invariant_under_rotation_translation_and_winding():
    base = [v2(0, 0), v2(10, 0), v2(10, 6), v2(0, 6)]
    angle = 0.37
    cosine, sine = math.cos(angle), math.sin(angle)
    translation = (4.2, -1.3)

    def transform(point):
        return v2(
            cosine * point.x - sine * point.y + translation[0],
            sine * point.x + cosine * point.y + translation[1],
        )

    transformed_center = transform(v2(5, 0))
    transformed_tangent = (cosine, sine)
    transformed = [transform(point) for point in base]

    for boundary in (transformed, list(reversed(transformed))):
        interval = entrance_frontage_interval(
            boundary, (transformed_center.x, transformed_center.y),
            transformed_tangent, clear_width=3.3, jamb_width=0.3)
        assert interval is not None
        full_width, projected = _edge_measure(boundary, interval)
        assert full_width - 2 * 0.3 == pytest.approx(3.3, abs=1e-5)
        assert projected == pytest.approx(
            (transformed_center.x, transformed_center.y), abs=1e-5)
