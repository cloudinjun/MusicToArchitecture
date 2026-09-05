"""Portable regression for the JSON extrusion ring contract consumed by Blender."""

import ast
import copy
import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from backend.app.geometry import v2
from backend.app.plan_regions import extrusions
from backend.scripts.audit_glb_holes import audit_glb_holes


ROOT = Path(__file__).parents[2]
VISUAL_AUDIT_ROOT = ROOT / 'artifacts' / 'visual_audit' / '2026-09-03'


def _signed_area(ring):
    ring = [(point['x'], point['y']) if isinstance(point, dict) else point
            for point in ring]
    return 0.5 * sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(ring, ring[1:] + ring[:1])
    )


def _import_keyhole():
    """Load only the importer’s pure ring helper, without importing bpy."""
    source = (ROOT / 'blender' / 'import_building_model_v3.py').read_text(
        encoding='utf-8')
    tree = ast.parse(source)
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == '_keyhole')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 '<importer-keyhole>', 'exec'), namespace)
    return namespace['_keyhole']


def test_plan_regions_emits_all_extrusion_rings_counter_clockwise():
    parts = extrusions(
        [v2(0, 0), v2(10, 0), v2(10, 10), v2(0, 10)],
        [[v2(3, 3), v2(7, 3), v2(7, 7), v2(3, 7)]],
        0.0, 0.3,
    )
    result = unary_union([
        Polygon([(point.x, point.y) for point in part.boundary])
        for part in parts
    ])
    expected = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]).difference(
        Polygon([(3, 3), (7, 3), (7, 7), (3, 7)]))
    assert result.symmetric_difference(expected).area < 1.0e-8
    assert all(not part.holes for part in parts)
    assert all(_signed_area([(point.x, point.y) for point in part.boundary]) > 0
               for part in parts)


def test_existing_keyhole_reversal_preserves_hole_area_for_contract_winding():
    """The importer reverses each hole, so source rings must share outer winding."""
    keyhole = _import_keyhole()
    boundary = [{'x': x, 'y': y} for x, y in
                [(0, 0), (10, 0), (10, 10), (0, 10)]]
    holes = [[{'x': x, 'y': y} for x, y in
              [(3, 3), (7, 3), (7, 7), (3, 7)]]]
    bridged = keyhole(boundary, holes)
    expected_area = abs(_signed_area(boundary)) - sum(
        abs(_signed_area(hole)) for hole in holes)
    assert abs(_signed_area(bridged)) == pytest.approx(expected_area)


def test_opposite_source_hole_winding_exposes_the_old_keyhole_assumption():
    """This is the failure mode from a Shapely exterior CW/interior CCW payload."""
    keyhole = _import_keyhole()
    boundary = [{'x': x, 'y': y} for x, y in
                [(0, 10), (10, 10), (10, 0), (0, 0)]]  # clockwise
    hole = [{'x': x, 'y': y} for x, y in
            [(3, 3), (7, 3), (7, 7), (3, 7)]]  # counter-clockwise
    bridged = keyhole(boundary, [hole])
    expected_area = abs(_signed_area(boundary)) - abs(_signed_area(hole))
    assert abs(_signed_area(bridged)) != pytest.approx(expected_area)
    assert abs(_signed_area(bridged)) == pytest.approx(116.0)


def _artifact(stage, track):
    result_path = VISUAL_AUDIT_ROOT / stage / 'tracks' / track / 'result.json'
    if not result_path.exists():
        pytest.skip(f'{stage}/{track} visual audit artifact is unavailable')
    model_id = json.loads(result_path.read_text(encoding='utf-8'))['model_id']
    model_path = (VISUAL_AUDIT_ROOT / stage / 'geometry' / model_id /
                  'building_model_v3.json')
    glb_path = VISUAL_AUDIT_ROOT / stage / 'models' / f'{model_id}.glb'
    if not model_path.exists() or not glb_path.exists():
        pytest.skip(f'{stage}/{track} geometry/export pair is unavailable')
    return model_path, glb_path


@pytest.mark.parametrize('target_kind', ['floor_slab', 'ceiling'])
def test_after_frozen_couperin_detects_filled_holes_at_both_surface_kinds(target_kind):
    """The pre-split exporter must remain a red regression fixture."""
    model_path, glb_path = _artifact('after-frozen', 'couperin-harpsichord')
    result = audit_glb_holes(model_path, glb_path, target_kind=target_kind)
    assert result['status'] == 'failed'
    assert result['declared_hole_count'] > 0
    assert result['filled_hole_count'] > 0
    assert result['surface_parity_failed_level_count'] > 0
    assert result['evaluated_hole_count'] + result['unevaluated_hole_count'] == (
        result['declared_hole_count'])


@pytest.mark.parametrize('stage,track', [
    ('verified-frozen', 'couperin-harpsichord'),
    ('verified-frozen', 'valse-gymnopedie'),
])
@pytest.mark.parametrize('target_kind', ['floor_slab', 'ceiling'])
def test_hole_free_frozen_export_has_surface_parity(stage, track, target_kind):
    """The verified split export passes when its JSON has no interior holes."""
    model_path, glb_path = _artifact(stage, track)
    result = audit_glb_holes(model_path, glb_path, target_kind=target_kind)
    assert result['status'] == 'passed'
    assert result['declared_hole_count'] == 0
    assert result['coverage_ratio'] is None
    assert result['surface_parity_failed_level_count'] == 0
    assert result['surface_parity_unevaluated_level_count'] == 0
    assert all(row['status'] == 'passed' for row in result['surface_parity'])


def test_unknown_surface_geometry_does_not_change_hole_counts():
    """Malformed target geometry is unknown, with null coverage when no holes exist."""
    model_path, glb_path = _artifact('verified-frozen', 'valse-gymnopedie')
    model = json.loads(model_path.read_text(encoding='utf-8'))
    fixture = copy.deepcopy(model)
    slab_group = next(group for group in fixture['element_groups']
                      if group.get('kind') == 'floor_slab')
    slab_group['instances'] = [{
        'id': 'fixture-missing-boundary',
        'level_id': 'L01',
        'geometry': {'z_base': 0.0, 'z_top': 0.3},
    }]
    result = audit_glb_holes(fixture, glb_path, target_kind='floor_slab')
    assert result['status'] == 'unevaluated'
    assert result['declared_hole_count'] == 0
    assert result['evaluated_hole_count'] == 0
    assert result['unevaluated_hole_count'] == 0
    assert result['coverage_ratio'] is None
    assert result['surface_parity_unevaluated_level_count'] == 1
    assert result['surface_parity'][0]['expected_area_m2'] is None
    assert result['surface_parity'][0]['actual_area_m2'] is None


@pytest.mark.parametrize('target_kind', ['floor_slab', 'missing_semantic_kind'])
def test_absent_source_target_is_unevaluated(target_kind):
    """An empty or absent semantic group cannot falsely pass export parity."""
    _, glb_path = _artifact('verified-frozen', 'valse-gymnopedie')
    result = audit_glb_holes(
        {'model_id': 'fixture-empty-source', 'element_groups': []},
        glb_path,
        target_kind=target_kind,
    )
    assert result['status'] == 'unevaluated'
    assert result['source_target_instance_count'] == 0
    assert result['declared_hole_count'] == 0
    assert result['evaluated_hole_count'] == 0
    assert result['unevaluated_hole_count'] == 0
    assert result['coverage_ratio'] is None
    assert result['surface_parity_level_count'] == 1
    assert result['surface_parity_unevaluated_level_count'] == 1
    row = result['surface_parity'][0]
    assert row['status'] == 'unevaluated'
    assert row['expected_area_m2'] is None
    assert row['actual_area_m2'] is None
    assert row['symmetric_difference_area_m2'] is None
    assert target_kind in row['reason']
