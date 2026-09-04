"""Run a licensed real-recording corpus through the score -> v3 model chain.

The experiment distinguishes three endpoint questions:

1. raw audio metrics after their declared normalisation;
2. the ten Shared Score dimensions after blending/proxy logic;
3. variable datums after confidence-limited travel.

It also records rounded score/model signature collisions. A low endpoint rate is not
useful if different recordings still compile to the same building state.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import statistics
import subprocess
import tempfile
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from backend.app.audio import extract_audio_features
from backend.app.blender_export import find_blender_executable
from backend.app.compiler_v3 import compile_building_model_v3
from backend.app.score import compile_architectural_score
from backend.app.translation_report import compile_translation_report


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'docs/experiments/audio_saturation_corpus.json'
DEFAULT_OUTPUT = ROOT / 'artifacts/audio_saturation/corpus-2026-08-30'
DEFAULT_CACHE = Path(tempfile.gettempdir()) / 'codex-mta-audio-saturation-20260830'
BLENDER_IMPORT_SCRIPT = ROOT / 'blender/import_building_model_v3.py'

FEATURE_FIELDS = (
    'tempo_bpm', 'rms_energy', 'onset_density_hz', 'spectral_centroid_hz',
    'periodicity', 'timbre_variation', 'dynamic_range_db',
    'novelty_peak_rate_per_min', 'spectral_contrast_db', 'harmonic_ratio',
    'spectral_flatness', 'zero_crossing_rate',
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url, headers={'User-Agent': 'MusicToArchitecture saturation research/0.1'})
    temporary = target.with_suffix(target.suffix + '.partial')
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as out:
        shutil.copyfileobj(response, out)
    temporary.replace(target)


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def _make_excerpt(source: Path, target: Path, seconds: float) -> tuple[float, float]:
    duration = _probe_duration(source)
    start = max(0.0, (duration - seconds) / 2.0)
    actual = min(seconds, duration)
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{start:.6f}',
         '-i', str(source), '-t', f'{actual:.6f}', '-vn', '-ac', '1', '-ar', '22050',
         '-b:a', '192k', str(target)],
        check=True, capture_output=True, text=True)
    return duration, start


def _is_exact(value: float) -> bool:
    return value <= 1e-9 or value >= 1.0 - 1e-9


def _is_near(value: float, epsilon: float) -> bool:
    return value <= epsilon or value >= 1.0 - epsilon


def _series(values: Iterable[float], epsilon: float) -> dict[str, Any]:
    sequence = list(values)
    count = len(sequence)
    exact = sum(_is_exact(value) for value in sequence)
    near = sum(_is_near(value, epsilon) for value in sequence)
    return {
        'count': count,
        'min': min(sequence) if sequence else None,
        'max': max(sequence) if sequence else None,
        'mean': statistics.fmean(sequence) if sequence else None,
        'stdev': statistics.pstdev(sequence) if count > 1 else 0.0 if count else None,
        'exact_endpoint_count': exact,
        'exact_endpoint_rate': exact / count if count else 0.0,
        'near_endpoint_count': near,
        'near_endpoint_rate': near / count if count else 0.0,
        'unique_3dp': len({round(value, 3) for value in sequence}),
    }


def _percentile(values: Iterable[float], probability: float) -> float | None:
    sequence = sorted(values)
    if not sequence:
        return None
    position = (len(sequence) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sequence[low]
    fraction = position - low
    return sequence[low] * (1.0 - fraction) + sequence[high] * fraction


def _distribution(values: Iterable[float]) -> dict[str, Any]:
    sequence = list(values)
    return {
        'count': len(sequence),
        'min': min(sequence) if sequence else None,
        'p05': _percentile(sequence, 0.05),
        'median': _percentile(sequence, 0.5),
        'p95': _percentile(sequence, 0.95),
        'max': max(sequence) if sequence else None,
        'mean': statistics.fmean(sequence) if sequence else None,
        'stdev': statistics.pstdev(sequence) if len(sequence) > 1 else 0.0 if sequence else None,
    }


def _collision_groups(signatures: list[tuple[str, tuple]]) -> list[list[str]]:
    groups: dict[tuple, list[str]] = defaultdict(list)
    for track_id, signature in signatures:
        groups[signature].append(track_id)
    return sorted((ids for ids in groups.values() if len(ids) > 1), key=lambda ids: ids[0])


def _collision_rate(groups: list[list[str]], total: int) -> float:
    duplicate_entries = sum(len(group) - 1 for group in groups)
    return duplicate_entries / total if total else 0.0


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def _render_blender_evidence(model_path: Path, render_dir: Path) -> dict[str, Any]:
    """Run the approved presentation-only v3 adapter with no GLB or persistent .blend."""
    blender = find_blender_executable()
    if not BLENDER_IMPORT_SCRIPT.is_file():
        raise FileNotFoundError(BLENDER_IMPORT_SCRIPT)
    render_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mta-corpus-render-') as temporary:
        blend_path = Path(temporary) / 'presentation_only.blend'
        result = subprocess.run(
            [str(blender), '--background', '--factory-startup', '--python',
             str(BLENDER_IMPORT_SCRIPT), '--', str(model_path), str(blend_path),
             str(render_dir), '-', '-', 'semantic_layers'],
            cwd=ROOT, capture_output=True, text=True, timeout=240, check=False)
        if result.returncode != 0:
            excerpt = (result.stderr or result.stdout or '').strip().splitlines()[-10:]
            raise RuntimeError('Blender render failed: ' + ' | '.join(excerpt))
    renders = []
    for path in sorted(render_dir.glob('*.png')):
        renders.append({
            'name': path.name,
            'relative_path': path.relative_to(ROOT).as_posix(),
            'sha256': _sha256(path),
            'bytes': path.stat().st_size,
        })
    expected = {'01_program.png', '02_facade.png', '03_structure.png'}
    actual = {render['name'] for render in renders}
    if actual != expected:
        raise RuntimeError(
            f'Expected semantic layer renders {sorted(expected)}, found {sorted(actual)}')
    return {
        'authority': 'presentation_only',
        'adapter': BLENDER_IMPORT_SCRIPT.relative_to(ROOT).as_posix(),
        'blender_executable': str(blender),
        'render_mode': 'semantic_layers',
        'render_visibility': {
            '01_program.png': ['program', 'circulation'],
            '02_facade.png': ['envelope'],
            '03_structure.png': ['structure'],
        },
        'renders': renders,
        'blender_summary': next(
            (line for line in reversed(result.stdout.splitlines()) if line.startswith('[v3]')),
            None),
    }


def _track_run(entry: dict[str, Any], cache: Path, run_root: Path,
               window_seconds: float, epsilon: float,
               render_blender: bool = False) -> dict[str, Any]:
    source = cache / entry['cache_name']
    if not source.exists():
        _download(entry['download_url'], source)
    excerpt = cache / 'normalized_mp3' / f"{entry['id']}.mp3"
    source_duration, excerpt_start = _make_excerpt(source, excerpt, window_seconds)

    started = time.perf_counter()
    features = extract_audio_features(excerpt, f"{entry['id']}.mp3")
    score = compile_architectural_score(features)
    model = compile_building_model_v3(features, score)
    translation = compile_translation_report(features, score, model)
    runtime = time.perf_counter() - started

    dependency = model.dependency_graph
    if dependency is None:
        raise RuntimeError('v3 model did not emit a dependency graph')
    structural_count = model.layer_counts.get('structure', 0)
    dependency_connected_rate = (
        dependency.connected_element_count / dependency.required_element_count
        if dependency.required_element_count else 1.0)
    dependency_structural_path_rate = (
        dependency.gravity_path_count / structural_count
        if structural_count else 1.0)
    dependency_summary = {
        'status': dependency.status,
        'relation_count': len(dependency.relations),
        'relation_group_count': len(dependency.relation_groups),
        'required_element_count': dependency.required_element_count,
        'connected_element_count': dependency.connected_element_count,
        'connected_rate': dependency_connected_rate,
        'structural_element_count': structural_count,
        'gravity_path_count': dependency.gravity_path_count,
        'structural_path_rate': dependency_structural_path_rate,
        'connection_design_status': dependency.connection_design_status,
        'failed_checks': [
            check.id for check in dependency.checks if check.status == 'failed'],
        'checks': [check.model_dump(mode='json') for check in dependency.checks],
    }

    metrics = {
        name: getattr(features, name).normalized
        for name in FEATURE_FIELDS if getattr(features, name) is not None
    }
    metric_raw_values = {
        name: getattr(features, name).value
        for name in FEATURE_FIELDS if getattr(features, name) is not None
    }
    dimensions = {dimension.id: dimension.value for dimension in score.dimensions}
    datums = {
        datum.id: datum.applied_position
        for datum in model.datum_set.datums
        if datum.output_range is not None and datum.applied_position is not None
    }
    metric_exact = sorted(name for name, value in metrics.items() if _is_exact(value))
    metric_near = sorted(name for name, value in metrics.items() if _is_near(value, epsilon))
    dimension_exact = sorted(name for name, value in dimensions.items() if _is_exact(value))
    dimension_near = sorted(name for name, value in dimensions.items()
                            if _is_near(value, epsilon))
    datum_exact = sorted(name for name, value in datums.items() if _is_exact(value))
    datum_near = sorted(name for name, value in datums.items() if _is_near(value, epsilon))

    track_dir = run_root / 'tracks' / entry['id']
    model_path = track_dir / 'building_model_v3.json'
    _write_json(track_dir / 'source.json', {
        **entry,
        'source_sha256': _sha256(source),
        'source_duration_seconds': source_duration,
        'excerpt_start_seconds': excerpt_start,
        'excerpt_duration_seconds': features.provenance.duration_seconds,
        'excerpt_mp3_sha256': _sha256(excerpt),
    })
    _write_json(track_dir / 'audio_features.json', features.model_dump(mode='json'))
    _write_json(track_dir / 'architectural_score.json', score.model_dump(mode='json'))
    _write_json(track_dir / 'translation_report.json', translation.model_dump(mode='json'))
    _write_json(model_path, model.model_dump(mode='json'))
    _write_json(track_dir / 'model_manifest.json', {
        'schema_version': model.schema_version,
        'model_id': model.model_id,
        'typology': model.typology,
        'tectonic_system': model.tectonic_system,
        'structural_system_id': model.structural_system_id,
        # The four decisions the score now makes for itself. They were module
        # constants when this report was first written, so recording them was
        # pointless; they are the headline result of a corpus run now.
        'massing_id': model.selection.massing_id if model.selection else None,
        'facade_grammar_id': model.facade_grammar_id,
        'envelope_tectonic_id': model.envelope_tectonic_id,
        'selection': (model.selection.model_dump(mode='json')
                      if model.selection else None),
        'facade_gates': (model.facade_gates.model_dump(mode='json')
                         if model.facade_gates else None),
        # The accessible route as the geometry that was checked, or the reason a
        # stair stands where a ramp should. A corpus run is where the split between
        # the two becomes visible across massing families.
        'accessible_route': (model.accessible_route.model_dump(mode='json')
                             if model.accessible_route else None),
        'accessible_route_unresolved': model.accessible_route_unresolved,
        'datum_set': model.datum_set.model_dump(mode='json'),
        'program_allocation': model.program_allocation.model_dump(mode='json'),
        'sizing': [item.model_dump(mode='json') for item in model.sizing],
        'element_count': model.element_count,
        'element_counts': model.element_counts,
        'layer_counts': model.layer_counts,
        'dependency_graph': dependency_summary,
        'limitations': model.limitations,
    })
    render_evidence = (
        _render_blender_evidence(model_path, track_dir / 'renders')
        if render_blender else None)
    if render_evidence:
        _write_json(track_dir / 'render_evidence.json', render_evidence)

    return {
        'id': entry['id'], 'title': entry['title'], 'creator': entry['creator'],
        'style_family': entry['style_family'], 'source_page_url': entry['source_page_url'],
        'license': entry['license'], 'source_sha256': _sha256(source),
        'excerpt_mp3_sha256': _sha256(excerpt),
        'source_duration_seconds': round(source_duration, 3),
        'excerpt_start_seconds': round(excerpt_start, 3),
        'runtime_seconds': round(runtime, 3),
        'metrics': metrics, 'metric_raw_values': metric_raw_values,
        'dimensions': dimensions, 'datums': datums,
        'metric_exact_endpoints': metric_exact, 'metric_near_endpoints': metric_near,
        'dimension_exact_endpoints': dimension_exact,
        'dimension_near_endpoints': dimension_near,
        'datum_exact_endpoints': datum_exact, 'datum_near_endpoints': datum_near,
        'score_signature': tuple(round(dimensions[name], 3) for name in sorted(dimensions)),
        'model_signature': tuple(
            [(name, round(datums[name], 3)) for name in sorted(datums)]
            + [(name, count) for name, count in sorted(model.element_counts.items())]),
        'model_id': model.model_id, 'element_count': model.element_count,
        'element_kind_count': len(model.element_counts),
        'layer_counts': model.layer_counts,
        'coverage': translation.coverage,
        'variable_coverage': translation.variable_coverage,
        'clamped_datum_count': translation.clamped_datum_count,
        'program_fulfilment': translation.program_fulfilment,
        'program_fits': translation.program_fits,
        'program_unplaced': translation.program_unplaced,
        'translation_grades': translation.grades,
        'dependency_status': dependency.status,
        'dependency_failed_checks': dependency_summary['failed_checks'],
        'dependency_relation_count': dependency_summary['relation_count'],
        'dependency_relation_group_count': dependency_summary['relation_group_count'],
        'dependency_required_element_count': dependency.required_element_count,
        'dependency_connected_element_count': dependency.connected_element_count,
        'dependency_connected_rate': dependency_connected_rate,
        'dependency_structural_element_count': structural_count,
        'dependency_gravity_path_count': dependency.gravity_path_count,
        'dependency_structural_path_rate': dependency_structural_path_rate,
        'dependency_connection_design_status': dependency.connection_design_status,
        'render_evidence': render_evidence,
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = report['summary']
    acceptance = report['acceptance']
    lines = [
        '# Real-audio saturation corpus', '',
        (f"{summary['tracks_succeeded']}/{summary['tracks_total']} recordings completed "
         f"the audio → Shared Score → v3 datum/program/structure/envelope chain."), '',
        '## Saturation result', '',
        f"- Raw-feature exact endpoint rate: {summary['feature_exact_endpoint_rate']:.1%}",
        f"- Raw-feature near-endpoint rate (±{report['near_endpoint_epsilon']:.2f}): "
        f"{summary['feature_near_endpoint_rate']:.1%}",
        f"- Shared Score near-endpoint rate: {summary['score_near_endpoint_rate']:.1%}",
        f"- Variable-datum near-endpoint rate: {summary['datum_near_endpoint_rate']:.1%}",
        f"- Score/model collision rate: {summary['score_signature_collision_rate']:.1%} / "
        f"{summary['model_signature_collision_rate']:.1%}",
        f"- Dependency graph pass rate: {summary['dependency_graph_pass_rate']:.1%}",
        f"- Minimum constructed-element connection rate: "
        f"{summary['minimum_dependency_connected_rate']:.1%}",
        f"- Minimum structure-to-soil path rate: "
        f"{summary['minimum_structural_path_rate']:.1%}",
        '- Connection capacity status: not checked', '',
        '## Predeclared checks', '',
    ]
    for name, check in acceptance['checks'].items():
        lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} — {name}: {check['actual']}")
    lines += ['', '## Highest-saturation metrics', '',
              '| Metric | Near endpoint | Exact endpoint | Normalised span | Raw p05–p95 |',
              '|---|---:|---:|---:|---:|']
    worst = sorted(report['per_feature'].items(),
                   key=lambda item: item[1]['near_endpoint_rate'], reverse=True)[:6]
    for name, item in worst:
        raw = report['per_feature_raw'][name]
        lines.append(
            f"| {name} | {item['near_endpoint_rate']:.1%} | "
            f"{item['exact_endpoint_rate']:.1%} | {item['min']:.2f}–{item['max']:.2f} | "
            f"{raw['p05']:.3g}–{raw['p95']:.3g} |")
    lines += ['', '## Per recording', '',
              '| Recording | Curated style | Feature near | Score near | Datum near | Dependency | Structure path | Elements | Runtime |',
              '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for track in report['tracks']:
        feature_rate = len(track['metric_near_endpoints']) / len(track['metrics'])
        score_rate = len(track['dimension_near_endpoints']) / len(track['dimensions'])
        datum_rate = len(track['datum_near_endpoints']) / len(track['datums'])
        lines.append(
            f"| {track['title']} | {track['style_family']} | {feature_rate:.1%} | "
            f"{score_rate:.1%} | {datum_rate:.1%} | "
            f"{track['dependency_connected_rate']:.1%} | "
            f"{track['dependency_structural_path_rate']:.1%} | "
            f"{track['element_count']} | "
            f"{track['runtime_seconds']:.1f}s |")
    lines += ['', '## Scope', '',
              '- Each source is a real recording with a source page and declared license.',
              '- Every run uses a deterministic 30-second centre excerpt transcoded to mono MP3.',
              '- This evaluates calibration and output differentiation. It does not test full-song sectional form.',
              '- Style labels are curator/source metadata. The audio extractor does not classify genre.',
              '- Structural code tables remain project placeholders; no result claims code compliance or safety.', '']
    if summary['blender_render_count']:
        lines.insert(10, f"- Blender evidence renders: {summary['blender_render_count']}")
    if report['failures']:
        lines += ['## Failures', '']
        lines.extend(f"- {failure['id']}: {failure['error']}" for failure in report['failures'])
        lines.append('')
    return '\n'.join(lines)


def run(manifest_path: Path, cache: Path, output: Path,
        *, render_blender: bool = False) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    epsilon = float(manifest['saturation_definition']['near_endpoint_epsilon'])
    window_seconds = float(manifest['excerpt']['duration_seconds'])
    output.mkdir(parents=True, exist_ok=True)

    tracks: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, entry in enumerate(manifest['tracks'], 1):
        print(f"[{index:02d}/{len(manifest['tracks']):02d}] {entry['id']}", flush=True)
        try:
            tracks.append(_track_run(
                entry, cache, output, window_seconds, epsilon,
                render_blender=render_blender))
        except Exception as exc:  # the report must retain a failed corpus member
            failures.append({'id': entry['id'], 'error': f'{type(exc).__name__}: {exc}'})

    features_by_name: dict[str, list[float]] = defaultdict(list)
    raw_features_by_name: dict[str, list[float]] = defaultdict(list)
    dimensions_by_name: dict[str, list[float]] = defaultdict(list)
    datums_by_name: dict[str, list[float]] = defaultdict(list)
    for track in tracks:
        for name, value in track['metrics'].items():
            features_by_name[name].append(value)
        for name, value in track['metric_raw_values'].items():
            raw_features_by_name[name].append(value)
        for name, value in track['dimensions'].items():
            dimensions_by_name[name].append(value)
        for name, value in track['datums'].items():
            datums_by_name[name].append(value)

    feature_values = [value for values in features_by_name.values() for value in values]
    score_values = [value for values in dimensions_by_name.values() for value in values]
    datum_values = [value for values in datums_by_name.values() for value in values]
    feature_summary = _series(feature_values, epsilon)
    score_summary = _series(score_values, epsilon)
    datum_summary = _series(datum_values, epsilon)
    score_collisions = _collision_groups(
        [(track['id'], track['score_signature']) for track in tracks])
    model_collisions = _collision_groups(
        [(track['id'], track['model_signature']) for track in tracks])
    score_collision_rate = _collision_rate(score_collisions, len(tracks))
    model_collision_rate = _collision_rate(model_collisions, len(tracks))

    limits = manifest['acceptance']
    success_rate = len(tracks) / len(manifest['tracks'])
    max_single_feature = max(
        (_series(values, epsilon)['near_endpoint_rate'] for values in features_by_name.values()),
        default=0.0)
    minimum_variable_coverage = min(
        (track['variable_coverage'] for track in tracks), default=0.0)
    dependency_graph_pass_rate = (
        sum(track['dependency_status'] == 'passed' for track in tracks) / len(tracks)
        if tracks else 0.0)
    minimum_dependency_connected_rate = min(
        (track['dependency_connected_rate'] for track in tracks), default=0.0)
    minimum_structural_path_rate = min(
        (track['dependency_structural_path_rate'] for track in tracks), default=0.0)
    check_values = {
        'pipeline success rate': (success_rate, limits['pipeline_success_rate_min'], 'min'),
        'feature exact endpoint rate': (
            feature_summary['exact_endpoint_rate'], limits['feature_exact_endpoint_rate_max'], 'max'),
        'feature near-endpoint rate': (
            feature_summary['near_endpoint_rate'], limits['feature_near_endpoint_rate_max'], 'max'),
        'worst single-feature near-endpoint rate': (
            max_single_feature, limits['single_feature_near_endpoint_rate_max'], 'max'),
        'score signature collision rate': (
            score_collision_rate, limits['score_signature_collision_rate_max'], 'max'),
        'model signature collision rate': (
            model_collision_rate, limits['model_signature_collision_rate_max'], 'max'),
        'minimum variable coverage': (
            minimum_variable_coverage, limits['variable_coverage_min'], 'min'),
        # These are completeness invariants of the emitted graph. They are fixed at
        # 100% and deliberately do not depend on the calibration corpus manifest.
        'dependency graph pass rate': (dependency_graph_pass_rate, 1.0, 'min'),
        'minimum dependency connected rate': (
            minimum_dependency_connected_rate, 1.0, 'min'),
        'minimum structure-to-soil path rate': (
            minimum_structural_path_rate, 1.0, 'min'),
    }
    checks = {}
    for name, (actual, limit, direction) in check_values.items():
        passed = actual >= limit if direction == 'min' else actual <= limit
        checks[name] = {'passed': passed, 'actual': actual, 'limit': limit,
                        'direction': direction}

    serialisable_tracks = []
    for track in tracks:
        track = dict(track)
        track.pop('score_signature')
        track.pop('model_signature')
        serialisable_tracks.append(track)

    report = {
        'schema_version': 'mta.audio_saturation_report/1.0',
        'experiment_id': manifest['experiment_id'],
        'manifest_path': manifest_path.relative_to(ROOT).as_posix(),
        'excerpt': manifest['excerpt'],
        'near_endpoint_epsilon': epsilon,
        'summary': {
            'tracks_total': len(manifest['tracks']),
            'tracks_succeeded': len(tracks), 'tracks_failed': len(failures),
            'pipeline_success_rate': success_rate,
            'feature_observation_count': len(feature_values),
            'feature_exact_endpoint_rate': feature_summary['exact_endpoint_rate'],
            'feature_near_endpoint_rate': feature_summary['near_endpoint_rate'],
            'score_observation_count': len(score_values),
            'score_exact_endpoint_rate': score_summary['exact_endpoint_rate'],
            'score_near_endpoint_rate': score_summary['near_endpoint_rate'],
            'datum_observation_count': len(datum_values),
            'datum_exact_endpoint_rate': datum_summary['exact_endpoint_rate'],
            'datum_near_endpoint_rate': datum_summary['near_endpoint_rate'],
            'score_signature_collision_rate': score_collision_rate,
            'model_signature_collision_rate': model_collision_rate,
            'program_fit_rate': (sum(track['program_fits'] for track in tracks) / len(tracks)
                                 if tracks else 0.0),
            'minimum_variable_coverage': minimum_variable_coverage,
            'dependency_graph_pass_rate': dependency_graph_pass_rate,
            'minimum_dependency_connected_rate': minimum_dependency_connected_rate,
            'minimum_structural_path_rate': minimum_structural_path_rate,
            'total_dependency_relations': sum(
                track['dependency_relation_count'] for track in tracks),
            'total_runtime_seconds': sum(track['runtime_seconds'] for track in tracks),
            'blender_render_count': sum(
                len(track['render_evidence']['renders'])
                for track in tracks if track['render_evidence']),
        },
        'acceptance': {'all_passed': all(item['passed'] for item in checks.values()),
                       'checks': checks},
        'per_feature': {name: _series(values, epsilon)
                        for name, values in sorted(features_by_name.items())},
        'per_feature_raw': {name: _distribution(values)
                            for name, values in sorted(raw_features_by_name.items())},
        'per_dimension': {name: _series(values, epsilon)
                          for name, values in sorted(dimensions_by_name.items())},
        'per_datum': {name: _series(values, epsilon)
                      for name, values in sorted(datums_by_name.items())},
        'score_collision_groups': score_collisions,
        'model_collision_groups': model_collisions,
        'tracks': serialisable_tracks,
        'failures': failures,
        'limitations': [
            'Fixed 30-second centre excerpts test calibration, not whole-track sectional form.',
            'Curated style labels come from source metadata; genre_style remains a low-confidence timbral proxy.',
            'Code tables are placeholders and structural outputs require professional review.',
            'Dependency topology is checked; plates, bolts, welds, anchors, fasteners, and connection capacities remain unchecked.',
            'A corpus of fourteen recordings is a calibration probe, not a population estimate.',
        ],
    }
    _write_json(output / 'corpus_saturation_report.json', report)
    (output / 'README.md').write_text(_markdown(report), encoding='utf-8')
    with (output / 'per_track_summary.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            'id', 'title', 'style_family', 'runtime_seconds', 'element_count',
            'feature_near_count', 'score_near_count', 'datum_near_count',
            'variable_coverage', 'program_fits', 'dependency_status',
            'dependency_connected_rate', 'dependency_structural_path_rate',
            'dependency_relation_count', 'model_id'])
        writer.writeheader()
        for track in serialisable_tracks:
            writer.writerow({
                'id': track['id'], 'title': track['title'],
                'style_family': track['style_family'],
                'runtime_seconds': track['runtime_seconds'],
                'element_count': track['element_count'],
                'feature_near_count': len(track['metric_near_endpoints']),
                'score_near_count': len(track['dimension_near_endpoints']),
                'datum_near_count': len(track['datum_near_endpoints']),
                'variable_coverage': track['variable_coverage'],
                'program_fits': track['program_fits'],
                'dependency_status': track['dependency_status'],
                'dependency_connected_rate': track['dependency_connected_rate'],
                'dependency_structural_path_rate': track['dependency_structural_path_rate'],
                'dependency_relation_count': track['dependency_relation_count'],
                'model_id': track['model_id'],
            })
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--cache-dir', type=Path, default=DEFAULT_CACHE)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--render-blender', action='store_true')
    arguments = parser.parse_args()
    report = run(arguments.manifest.resolve(), arguments.cache_dir.resolve(),
                 arguments.output_dir.resolve(),
                 render_blender=arguments.render_blender)
    print(json.dumps(report['summary'], indent=2), flush=True)
    if report['failures']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
