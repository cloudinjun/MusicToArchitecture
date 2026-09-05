"""Focused exact-solid fixtures for the runtime spatial geometry review."""

from math import pi
from types import SimpleNamespace

import pytest

from backend.app.geometry import BoxGeometry, ExtrusionGeometry, v2, v3
from backend.app.geometry_review import (
    check_intercore_stair_overlap,
    check_invalid_plan_rings,
    check_stair_head_clearance,
    check_tread_elevator_shaft_overlap,
    check_tread_floor_slab_overlap,
)
from backend.app.spatial_rules import check_spatial_rules


def _instance(element_id, kind, geometry, level_id='L01'):
    return SimpleNamespace(id=element_id, level_id=level_id, geometry=geometry)


def _group(kind, *instances, subsystem='test', semantic_layer='circulation'):
    return SimpleNamespace(kind=kind, instances=list(instances), subsystem=subsystem,
                           semantic_layer=semantic_layer)


def _model(*groups):
    return SimpleNamespace(
        element_groups=list(groups),
        lattice=SimpleNamespace(levels=[]),
        program_allocation=SimpleNamespace(cores_unreserved=[]),
    )


def _box(element_id, kind, centre, size, *, rotation=0.0, level_id='L01'):
    return _instance(element_id, kind, BoxGeometry(
        center=centre, size=size, rotation_z=rotation), level_id)


def _square_extrusion(element_id, kind, *, x0=-5.0, y0=-5.0, x1=5.0,
                      y1=5.0, z0=0.0, z1=0.3, holes=None, level_id='L01'):
    return _instance(element_id, kind, ExtrusionGeometry(
        boundary=[v2(x0, y0), v2(x1, y0), v2(x1, y1), v2(x0, y1)],
        holes=holes or [], z_base=z0, z_top=z1), level_id)


def test_hole_and_rotation_are_respected_for_tread_slab_overlap():
    floor = _square_extrusion(
        'SLAB', 'floor_slab', holes=[
            [v2(-1.5, -1.5), v2(1.5, -1.5), v2(1.5, 1.5), v2(-1.5, 1.5)]])
    tread = _box('CIR-TRD-A01-S001', 'stair_tread', v3(0, 0, 0.15),
                 v3(1.0, 1.0, 0.2), rotation=pi / 4)
    assert check_tread_floor_slab_overlap(_model(
        _group('floor_slab', floor), _group('stair_tread', tread))) == []


def test_exact_rotated_solid_collision_reports_positive_volume():
    floor = _square_extrusion('SLAB', 'floor_slab', x0=0, y0=0, x1=4, y1=4)
    tread = _box('CIR-TRD-A01-S001', 'stair_tread', v3(2, 2, 0.2),
                 v3(1.4, 0.8, 0.2), rotation=pi / 4)
    findings = check_tread_floor_slab_overlap(_model(
        _group('floor_slab', floor), _group('stair_tread', tread)))
    assert len(findings) == 1
    assert findings[0].severity == 'violation'
    assert findings[0].measure > 0
    assert findings[0].unit == 'm³'


def test_head_clearance_uses_obstacle_underside_and_names_review_convention():
    tread = _box('CIR-TRD-A01-S001', 'stair_tread', v3(0, 0, 0.5), v3(1, 1, 0.2))
    slab = _square_extrusion('SLAB-ABOVE', 'floor_slab', x0=-2, y0=-2, x1=2,
                             y1=2, z0=1.8, z1=2.0)
    findings = check_stair_head_clearance(_model(
        _group('stair_tread', tread), _group('floor_slab', slab)))
    assert len(findings) == 1
    assert findings[0].severity == 'violation'
    assert findings[0].measure == pytest.approx(1.2)
    assert 'design-review convention' in findings[0].detail


def test_lift_and_distinct_core_tread_collisions_are_measured_in_3d():
    tread_a = _box('CIR-TRD-A01-S001', 'stair_tread', v3(0, 0, 0.5), v3(1, 1, 0.2))
    tread_j = _box('CIR-TRD-J01-S001', 'stair_tread', v3(0.2, 0.2, 0.5),
                   v3(1, 1, 0.2))
    shaft = _square_extrusion('LIFT', 'elevator_shaft', x0=-0.5, y0=-0.5, x1=0.5,
                              y1=0.5, z0=0.3, z1=0.8)
    model = _model(_group('stair_tread', tread_a, tread_j),
                   _group('elevator_shaft', shaft))
    lift_findings = check_tread_elevator_shaft_overlap(model)
    core_findings = check_intercore_stair_overlap(model)
    assert len(lift_findings) == 2
    assert all(item.measure > 0 for item in lift_findings)
    assert len(core_findings) == 1
    assert set(core_findings[0].elements) == {tread_a.id, tread_j.id}


def test_intercore_check_does_not_turn_rotated_aabb_or_same_pair_into_collision():
    long_primary = _box('CIR-TRD-A01-S001', 'stair_tread', v3(0, 0, 0.5),
                        v3(4, 0.2, 0.2), rotation=pi / 4)
    same_core = _box('CIR-TRD-B01-S001', 'stair_tread', v3(0, 0, 0.5),
                     v3(4, 0.2, 0.2), rotation=pi / 4)
    aabb_only = _box('CIR-TRD-J01-S001', 'stair_tread', v3(1, 0, 0.5),
                     v3(0.4, 0.4, 0.2))
    findings = check_intercore_stair_overlap(_model(
        _group('stair_tread', long_primary, same_core, aabb_only)))
    assert findings == []


def test_invalid_ring_is_named_and_missing_geometry_stays_unevaluated():
    bowtie = _instance('BAD-SLAB', 'floor_slab', ExtrusionGeometry(
        boundary=[v2(-2, -2), v2(2, 2), v2(-2, 2), v2(2, -2)],
        z_base=0, z_top=0.3))
    invalid = check_invalid_plan_rings(_model(_group('floor_slab', bowtie)))
    assert len(invalid) == 1
    assert invalid[0].severity == 'violation'
    assert 'non-adjacent edge intersection' in invalid[0].detail

    missing = _instance('MISSING-TREAD', 'stair_tread', None)
    unknown = check_tread_floor_slab_overlap(_model(_group('stair_tread', missing)))
    assert len(unknown) == 1
    assert unknown[0].severity == 'warning'
    assert unknown[0].unit == 'unevaluated'
    assert unknown[0].elements == ('MISSING-TREAD',)


def test_geometry_rules_are_carried_by_the_existing_spatial_report_schema():
    model = _model(_group(
        'stair_tread',
        _box('CIR-TRD-A01-S001', 'stair_tread', v3(0, 0, 0.5), v3(1, 1, 0.2))),
        _group('floor_slab', _square_extrusion(
            'SLAB', 'floor_slab', x0=-2, y0=-2, x1=2, y1=2, z0=0, z1=0.3)))
    report = check_spatial_rules(model)
    expected = {
        'SP-STAIR-HEAD-CLEARANCE', 'SP-STAIR-TREAD-SLAB-OVERLAP',
        'SP-STAIR-TREAD-LIFT-OVERLAP', 'SP-STAIR-INTERCORE-OVERLAP',
        'SP-INVALID-PLAN-RING',
    }
    assert expected <= report.counts.keys()
    assert expected <= report.watches.keys()


def test_warning_only_report_is_unevaluated():
    report = check_spatial_rules(_model(_group(
        'stair_tread', _instance('MISSING-TREAD', 'stair_tread', None))))
    assert report.status == 'unevaluated'


def test_capped_report_keeps_a_violation_ahead_of_warnings():
    floor = _square_extrusion('SLAB', 'floor_slab', x0=-2, y0=-2, x1=2, y1=2,
                               z0=0, z1=0.3)
    colliding = _box('CIR-TRD-A01-S001', 'stair_tread', v3(0, 0, 0.2), v3(1, 1, 0.2))
    missing = _instance('MISSING-TREAD', 'stair_tread', None)
    report = check_spatial_rules(_model(
        _group('floor_slab', floor), _group('stair_tread', colliding, missing)), limit=1)
    assert report.status == 'failed'
    assert report.counts['SP-STAIR-TREAD-SLAB-OVERLAP'] == 2
    displayed = report.by_rule('SP-STAIR-TREAD-SLAB-OVERLAP')
    assert displayed and displayed[0].severity == 'violation'
    assert colliding.id in displayed[0].elements
