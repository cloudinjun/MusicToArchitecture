"""Core floor interfaces own every served occupied floor exactly once."""

from __future__ import annotations

import pytest

from backend.app.compiler_v3 import (
    _core_landing_levels,
    _emit_core_floor_interfaces,
    _landing_footprints,
)
from backend.tests.test_envelope_closure import builder, elements


def _low_rise_builder():
    built = builder(
        datum_updates={'slab_thickness_m': 0.3},
    )
    levels = built.lattice.levels
    levels[0].kind, levels[0].z = 'podium', 0.0
    levels[1].kind, levels[1].z = 'occupied', 0.3
    levels[2].kind, levels[2].z = 'occupied', 4.3
    return built, levels


def _landing_instances(built):
    return {
        instance.id: instance
        for instance in elements(built)
        if instance.id.startswith('CIR-LND-')
    }


def test_low_rise_core_interfaces_keep_first_occupied_floor_and_skip_podium():
    built, levels = _low_rise_builder()
    point = (6.0, 4.0)
    width, run = 1.2, 2.88

    _emit_core_floor_interfaces(
        built, point, levels, 'LND', 1.0, width, run)

    all_instances = elements(built)
    interface_ids = [instance.id for instance in all_instances
                     if instance.id.startswith('CIR-LND-')]
    interfaces = {instance.id: instance for instance in all_instances
                  if instance.id.startswith('CIR-LND-')}
    assert {'CIR-LND-L01', 'CIR-LND-L01-THR',
            'CIR-LND-L02', 'CIR-LND-L02-THR'} <= set(interfaces)
    assert 'CIR-LND-L00' not in interfaces
    assert len(interfaces) == 4
    assert len(interface_ids) == len(set(interface_ids))
    assert not [instance for instance in all_instances
                if instance.kind in {'stair_tread', 'stair_half_landing'}]

    assert interfaces['CIR-LND-L01'].position.z + \
        interfaces['CIR-LND-L01'].dimensions.z / 2.0 == pytest.approx(0.3)
    assert interfaces['CIR-LND-L01-THR'].position.z + \
        interfaces['CIR-LND-L01-THR'].dimensions.z / 2.0 == pytest.approx(0.3)
    assert interfaces['CIR-LND-L02'].position.z + \
        interfaces['CIR-LND-L02'].dimensions.z / 2.0 == pytest.approx(4.3)


def test_served_run_starting_at_occupied_level_includes_its_first_interface():
    built, levels = _low_rise_builder()
    served = levels[1:]

    assert _core_landing_levels(served) == served
    _emit_core_floor_interfaces(
        built, (6.0, 4.0), served, 'LND', 1.0, 1.2, 2.88)

    ids = {instance.id for instance in elements(built)
           if instance.id.startswith('CIR-LND-')}
    assert {'CIR-LND-L01', 'CIR-LND-L01-THR',
            'CIR-LND-L02', 'CIR-LND-L02-THR'} <= ids
    assert 'CIR-LND-L00' not in ids


def test_emitted_landing_bounds_match_shared_landing_footprints():
    built, levels = _low_rise_builder()
    point = (6.0, 4.0)
    width, run = 1.2, 2.88
    served = levels[1:]
    anchors = {
        'width': width,
        'run': run,
        'primary': point,
        'served': served,
        'second': None,
        'second_served': [],
        'extras': [],
    }

    _emit_core_floor_interfaces(
        built, point, served, 'LND', 1.0, width, run)
    landing = next(instance for instance in elements(built)
                   if instance.id == 'CIR-LND-L01')
    centre = landing.position
    size = landing.dimensions
    emitted_bounds = (
        centre.x - size.x / 2.0, centre.y - size.y / 2.0,
        centre.x + size.x / 2.0, centre.y + size.y / 2.0,
    )

    assert emitted_bounds == pytest.approx(
        _landing_footprints(anchors, 'L01')[0])
