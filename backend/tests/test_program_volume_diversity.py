from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.models import ArchitecturalScore, ScoreDimension
from backend.app.program_volumes import organize_program_volumes
from backend.scripts.evaluate_program_volume_diversity import measure_studies


DIMENSIONS = (
    'genre_style', 'hierarchy', 'repetition', 'variation', 'density',
    'continuity', 'interruption', 'polyphony', 'tension_release',
    'tempo_of_change',
)


def _score(**values) -> ArchitecturalScore:
    return ArchitecturalScore(
        score_id=f"score-diversity-{values.get('repetition', 0.4):.2f}",
        source_audio_sha256='1' * 64,
        dimensions=[ScoreDimension(
            id=dimension, value=values.get(dimension, 0.4),
            source_feature=f'test_{dimension}', extraction_method='manual',
            confidence=1.0,
            architectural_proposal='Program Volume diversity measurement test.')
                    for dimension in DIMENSIONS],
        mapping_rules=[])


def _ring(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _transform(
    ring: list[list[float]], *, sx: float = 1.0, sy: float = 1.0,
    dx: float = 0.0, dy: float = 0.0,
) -> list[list[float]]:
    return [[x * sx + dx, y * sy + dy] for x, y in ring]


def _write_study(
    root: Path,
    name: str,
    *,
    grammar: str,
    levels: dict[str, list[list[float]]],
    topology: str,
    digest: str,
) -> Path:
    model_path = root / f'{name}-program_volume_model.json'
    model_path.write_text(json.dumps({
        'schema_version': 'mta.program_volumes/1.0',
        'grammar_id': grammar,
        'level_unions': [
            {
                'level_id': level_id,
                'boundary': boundary,
                'voids': [],
            }
            for level_id, boundary in levels.items()
        ],
    }), encoding='utf-8')
    study_path = root / f'{name}-study.json'
    study_path.write_text(json.dumps({
        'schema_version': 'mta.program_volume_study/1.0',
        'candidates': [{
            'grammar_id': grammar,
            'topology_signature': topology,
            'program_volume_digest': digest,
            'program_volume_model': str(model_path),
        }],
    }), encoding='utf-8')
    return study_path


def _report_for(tmp_path: Path, studies: list[Path]) -> dict:
    return measure_studies(studies)


def test_translation_and_overall_xy_scaling_are_normalized_as_collision(tmp_path):
    base = {
        'L01': _ring(0, 0, 4, 2),
        'L02': _ring(1, 0, 3, 2),
    }
    scaled = {
        level_id: _transform(boundary, sx=2.0, sy=3.0, dx=10.0, dy=-7.0)
        for level_id, boundary in base.items()
    }
    first = _write_study(
        tmp_path, 'base', grammar='PVG-STACKED-BANDS', levels=base,
        topology='topology-a', digest='digest-a')
    second = _write_study(
        tmp_path, 'scaled', grammar='PVG-STACKED-BANDS', levels=scaled,
        topology='topology-b', digest='digest-b')

    grammar = _report_for(tmp_path, [first, second])['grammars']['PVG-STACKED-BANDS']

    assert grammar['candidate_count'] == 2
    assert grammar['raw']['topology_signature_unique_count'] == 2
    assert grammar['raw']['program_volume_digest_unique_count'] == 2
    assert grammar['normalized']['normalized_shape_signature_unique_count'] == 1
    assert grammar['normalized']['tolerance_collision_pair_count'] == 1
    pair = grammar['pairwise']['pairs'][0]
    assert pair['collision'] is True
    assert pair['shape_distance_summary']['max'] == pytest.approx(0.0)
    assert pair['profile_distance_l2'] == pytest.approx(0.0)


def test_relative_upper_level_offset_is_a_real_shape_difference(tmp_path):
    base = {
        'L01': _ring(0, 0, 4, 2),
        'L02': _ring(1, 0, 3, 2),
    }
    offset = {
        'L01': _ring(0, 0, 4, 2),
        'L02': _ring(2, 0, 4, 2),
    }
    first = _write_study(
        tmp_path, 'base', grammar='PVG-TERRACED-WEAVE', levels=base,
        topology='topology-a', digest='digest-a')
    second = _write_study(
        tmp_path, 'offset', grammar='PVG-TERRACED-WEAVE', levels=offset,
        topology='topology-b', digest='digest-b')

    grammar = _report_for(tmp_path, [first, second])['grammars']['PVG-TERRACED-WEAVE']
    pair = grammar['pairwise']['pairs'][0]
    per_level = {row['level_id']: row for row in pair['levels']}

    assert grammar['normalized']['normalized_shape_signature_unique_count'] == 2
    assert grammar['normalized']['tolerance_collision_pair_count'] == 0
    assert per_level['L01']['normalized_symmetric_difference_over_union'] == pytest.approx(0.0)
    assert per_level['L02']['normalized_symmetric_difference_over_union'] > 0.0
    assert pair['collision'] is False


def test_grammars_are_compared_independently(tmp_path):
    levels = {'L01': _ring(0, 0, 4, 2), 'L02': _ring(1, 0, 3, 2)}
    first = _write_study(
        tmp_path, 'stacked-a', grammar='PVG-STACKED-BANDS', levels=levels,
        topology='topology-a', digest='digest-a')
    second = _write_study(
        tmp_path, 'stacked-b', grammar='PVG-STACKED-BANDS', levels=levels,
        topology='topology-b', digest='digest-b')
    third = _write_study(
        tmp_path, 'bridge', grammar='PVG-SPLIT-BRIDGE', levels=levels,
        topology='topology-c', digest='digest-c')

    report = _report_for(tmp_path, [first, second, third])

    assert report['input_study_count'] == 3
    assert report['candidate_count'] == 3
    assert set(report['grammars']) == {'PVG-STACKED-BANDS', 'PVG-SPLIT-BRIDGE'}
    assert report['grammars']['PVG-STACKED-BANDS']['pairwise']['pair_count'] == 1
    assert report['grammars']['PVG-SPLIT-BRIDGE']['pairwise']['pair_count'] == 0


def test_cli_writes_parseable_measurement_only_report(tmp_path):
    levels = {'L01': _ring(0, 0, 4, 2), 'L02': _ring(1, 0, 3, 2)}
    study = _write_study(
        tmp_path, 'cli', grammar='PVG-STACKED-BANDS', levels=levels,
        topology='topology-a', digest='digest-a')
    output = tmp_path / 'diversity-report.json'
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, '-m', 'backend.scripts.evaluate_program_volume_diversity',
         '--study', str(study), '--out', str(output)],
        cwd=root, capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['schema_version'] == 'mta.program_volume_diversity/1.0'
    assert payload['measurement_only'] is True
    assert payload['authority']['current_geometry'] is False
    assert payload['authority']['accepted_geometry'] is False
    assert payload['candidate_count'] == 1
    assert payload['input_study_sha256'][str(study)]


def test_real_stacked_generator_changes_normalized_shape_with_repetition(tmp_path):
    models = [
        organize_program_volumes(
            _score(repetition=repetition), 'museum',
            grammar_id='PVG-STACKED-BANDS')
        for repetition in (0.0, 1.0)
    ]
    study = tmp_path / 'real-generator-study.json'
    study.write_text(json.dumps({
        'schema_version': 'mta.program_volume_study/1.0',
        'candidates': [
            {
                'grammar_id': model.grammar_id,
                'topology_signature': model.topology_signature,
                'program_volume_digest': model.digest(),
                'level_unions': [union.model_dump(mode='json')
                                 for union in model.level_unions],
            }
            for model in models
        ],
    }), encoding='utf-8')

    grammar = measure_studies([study])['grammars']['PVG-STACKED-BANDS']
    pair = grammar['pairwise']['pairs'][0]
    level_distance = {
        row['level_id']: row['normalized_symmetric_difference_over_union']
        for row in pair['levels']
    }

    assert grammar['normalized']['normalized_shape_signature_unique_count'] == 2
    assert grammar['normalized']['tolerance_collision_pair_count'] == 0
    assert pair['collision'] is False
    assert level_distance['L02'] > 0.0
    assert level_distance['L04'] > 0.0
