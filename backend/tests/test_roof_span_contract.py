"""Roof span registration must respect the authored plan, including voids."""

from __future__ import annotations

import pytest
from shapely.affinity import translate
from shapely.geometry import LineString, MultiPolygon, Polygon, box

from backend.app.compiler_v3 import _emit_roof
from backend.app.roof import (
    roof_control_for,
    supported_purlin_stations,
    validate_roof_emission,
)
from backend.tests.test_envelope_closure import builder, elements, ring


def _member_footprint(x0: float, x1: float, y: float, width_m: float):
    """Plan footprint of the horizontal member used by the roof contract."""

    return LineString([(x0, y), (x1, y)]).buffer(
        width_m / 2.0, cap_style=2, join_style=2)


def _assert_full_spans_inside(
    region, stations: list[float], x0: float, x1: float, width_m: float,
) -> None:
    # The implementation may land exactly on a parallel offset.  A tiny tolerance
    # is appropriate for the contract because the geometry is represented in metres.
    allowed = region.buffer(1.0e-8)
    for station in stations:
        assert allowed.covers(_member_footprint(x0, x1, station, width_m)), station


def test_rectangle_registers_complete_spans_at_declared_max_spacing():
    region = box(0.0, 0.0, 12.0, 10.0)

    stations = supported_purlin_stations(
        region, 1.0, 11.0, 1.0, 9.0, width_m=0.4, max_spacing_m=3.0,
    )

    assert stations[0] == pytest.approx(1.0)
    assert stations[-1] == pytest.approx(9.0)
    assert all(b - a <= 3.0 + 1.0e-8 for a, b in zip(stations, stations[1:]))
    _assert_full_spans_inside(region, stations, 1.0, 11.0, 0.4)


def test_concave_notch_does_not_bridge_between_valid_endpoints():
    outer = box(0.0, 0.0, 12.0, 10.0)
    notch = Polygon([(4.0, 5.0), (8.0, 5.0), (8.0, 10.0), (4.0, 10.0)])
    region = outer.difference(notch)

    stations = supported_purlin_stations(
        region, 1.0, 11.0, 1.0, 9.0, width_m=0.4, max_spacing_m=2.0,
    )

    assert stations
    assert max(stations) < 5.0
    assert all(notch.buffer(1.0e-8).intersection(
        _member_footprint(1.0, 11.0, station, 0.4)).area < 1.0e-7
               for station in stations)
    _assert_full_spans_inside(region, stations, 1.0, 11.0, 0.4)


def test_hole_splits_spans_and_never_places_a_station_through_it():
    outer = box(0.0, 0.0, 12.0, 10.0)
    void = box(4.0, 4.0, 8.0, 8.0)
    region = outer.difference(void)

    stations = supported_purlin_stations(
        region, 1.0, 11.0, 1.0, 9.0, width_m=0.4, max_spacing_m=2.5,
    )

    assert stations == pytest.approx([1.0, 2.4, 3.8, 8.2, 9.0])
    assert all(void.buffer(1.0e-8).intersection(
        _member_footprint(1.0, 11.0, station, 0.4)).area < 1.0e-7
               for station in stations)
    _assert_full_spans_inside(region, stations, 1.0, 11.0, 0.4)


def test_disconnected_regions_do_not_receive_a_fabricated_bridge():
    region = MultiPolygon([
        box(0.0, 0.0, 4.0, 10.0),
        box(8.0, 0.0, 12.0, 10.0),
    ])

    stations = supported_purlin_stations(
        region, 1.0, 11.0, 1.0, 9.0, width_m=0.4, max_spacing_m=2.0,
    )

    assert stations == []


def test_translation_preserves_station_pattern_and_moves_it_with_the_volume():
    region = box(0.0, 0.0, 12.0, 10.0)
    base = supported_purlin_stations(
        region, 1.0, 11.0, 0.0, 10.0, width_m=0.4, max_spacing_m=2.7,
    )
    dx, dy = 117.0, -33.0
    shifted = supported_purlin_stations(
        translate(region, xoff=dx, yoff=dy),
        1.0 + dx, 11.0 + dx, 0.0 + dy, 10.0 + dy,
        width_m=0.4, max_spacing_m=2.7,
    )

    assert shifted == pytest.approx([station + dy for station in base])


def test_member_section_breadth_is_reserved_at_span_ends():
    region = box(0.0, 0.0, 12.0, 10.0)

    narrow = supported_purlin_stations(
        region, 1.0, 11.0, 0.0, 10.0, width_m=0.4, max_spacing_m=100.0,
    )
    broad = supported_purlin_stations(
        region, 1.0, 11.0, 0.0, 10.0, width_m=1.0, max_spacing_m=100.0,
    )

    assert narrow == pytest.approx([0.2, 9.8])
    assert broad == pytest.approx([0.5, 9.5])
    _assert_full_spans_inside(region, narrow, 1.0, 11.0, 0.4)
    _assert_full_spans_inside(region, broad, 1.0, 11.0, 1.0)


def test_concave_roof_emitter_validates_every_emitted_footprint():
    # Reuse the focused compiler builder so this test exercises the actual emitter,
    # including its truss, purlin, deck, closure and warm-roof pieces.
    plate = ring([
        (0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (8.0, 8.0),
        (8.0, 5.0), (4.0, 5.0), (4.0, 8.0), (0.0, 8.0),
    ])
    b = builder([plate, plate, plate])
    roof = b.lattice.roof
    control = roof_control_for(
        [(point.x, point.y) for point in roof.plate], [],
        datum_z=roof.z, truss_depth_m=b.datums.value('truss_depth_m'),
    )
    b.lattice.roof_control = control
    before = set(b.element_ids)

    _emit_roof(b)

    emitted = [
        (instance.id, instance.geometry, group.thickness_m)
        for group in b.groups.values()
        for instance in group.instances
        if instance.id not in before
    ]
    assert emitted
    assert any(instance.kind == 'purlin' for instance in elements(b))
    validate_roof_emission(control, emitted, profiles=b.profiles)
