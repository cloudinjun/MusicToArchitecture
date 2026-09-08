"""Measure geometric diversity across Program Volume study outputs.

This command compares the geometry stored by ``run_program_volume_study``.  It
keeps the measurement deliberately separate from selection: the report contains
no ``pass`` threshold and never promotes a response, study, or candidate to
current or accepted geometry.

Example::

    python -m backend.scripts.evaluate_program_volume_diversity \
      --study run-a/study.json --study run-b/study.json \
      --out diversity-report.json

The level-union polygons are normalised against the candidate's complete XY
envelope.  Translation and independent global X/Y scaling therefore do not
create a false shape difference.  Relative changes between levels remain
visible in the per-level symmetric-difference measurements.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from shapely.geometry import Polygon


SCHEMA_VERSION = 'mta.program_volume_diversity/1.0'
GEOMETRY_TOLERANCE = 1.0e-9
PROFILE_TOLERANCE = 1.0e-9
SIGNATURE_DECIMALS = 9


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f'JSON artifact not found: {path}') from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid JSON artifact {path}: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError(f'Expected a JSON object at {path}')
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_reference(reference: str | Path, study_path: Path) -> Path:
    """Resolve a study's model reference without changing the study payload."""
    raw = Path(reference)
    candidates = [raw] if raw.is_absolute() else [raw, study_path.parent / raw]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    attempted = ', '.join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(
        f'Program Volume model referenced by {study_path} was not found; '
        f'attempted: {attempted}')


def _polygon(record: Mapping[str, Any], *, source: str) -> Polygon:
    boundary = record.get('boundary')
    voids = record.get('voids', [])
    if not isinstance(boundary, list) or len(boundary) < 3:
        raise ValueError(f'Invalid level-union boundary in {source}')
    try:
        shape = Polygon(
            [(float(point[0]), float(point[1])) for point in boundary],
            [[(float(point[0]), float(point[1])) for point in ring]
             for ring in voids],
        )
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid level-union coordinates in {source}') from exc
    if shape.is_empty or shape.geom_type != 'Polygon':
        raise ValueError(f'Level union in {source} is not a Polygon')
    if not shape.is_valid:
        raise ValueError(f'Invalid level-union polygon topology in {source}')
    return shape


def _normalise(value: float, lower: float, span: float) -> float:
    # A degenerate axis has no measurable extent.  Centre it so that the
    # normalisation remains deterministic without inventing an orientation.
    if span <= GEOMETRY_TOLERANCE:
        return 0.5
    return (value - lower) / span


def _normalise_polygon(
    shape: Polygon,
    *,
    min_x: float,
    min_y: float,
    span_x: float,
    span_y: float,
) -> Polygon:
    # Keep full-precision coordinates for distance/area measurements.  The
    # reproducible signature rounds separately in ``_canonical_polygon``.
    def transform(point: tuple[float, float]) -> tuple[float, float]:
        return (
            _normalise(point[0], min_x, span_x),
            _normalise(point[1], min_y, span_y),
        )

    return Polygon(
        [transform((float(x), float(y))) for x, y in shape.exterior.coords],
        [[transform((float(x), float(y))) for x, y in ring.coords]
         for ring in shape.interiors],
    )


def _canonical_polygon(shape: Polygon) -> dict[str, Any]:
    """Return a JSON-safe, winding/start-point-independent polygon record."""
    def canonical_ring(ring) -> list[list[float]]:
        points = [(float(x), float(y)) for x, y in ring.coords]
        if points and points[0] == points[-1]:
            points.pop()
        if not points:
            return []
        candidates: list[tuple[tuple[float, float], ...]] = []
        for sequence in (points, list(reversed(points))):
            for index in range(len(sequence)):
                candidates.append(tuple(sequence[index:] + sequence[:index]))
        return [[round(x, SIGNATURE_DECIMALS), round(y, SIGNATURE_DECIMALS)]
                for x, y in min(candidates)]

    return {
        'boundary': canonical_ring(shape.exterior),
        'voids': sorted(canonical_ring(ring) for ring in shape.interiors),
    }


def _shape_signature(shapes: Mapping[str, Polygon]) -> str:
    payload = {
        level_id: _canonical_polygon(shapes[level_id])
        for level_id in sorted(shapes)
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _envelope(shapes: Mapping[str, Polygon]) -> tuple[float, float, float, float]:
    if not shapes:
        raise ValueError('A Program Volume model must contain level_unions')
    min_x = min(shape.bounds[0] for shape in shapes.values())
    min_y = min(shape.bounds[1] for shape in shapes.values())
    max_x = max(shape.bounds[2] for shape in shapes.values())
    max_y = max(shape.bounds[3] for shape in shapes.values())
    return min_x, min_y, max_x, max_y


def _candidate_from_model(
    *,
    row: Mapping[str, Any],
    model: Mapping[str, Any],
    candidate_id: str,
    source_study: Path,
    model_path: Path | None,
) -> dict[str, Any]:
    unions = model.get('level_unions')
    if not isinstance(unions, list) or not unions:
        raise ValueError(f'Candidate {candidate_id} has no level_unions')

    shapes: dict[str, Polygon] = {}
    level_order: list[str] = []
    for index, union in enumerate(unions):
        if not isinstance(union, Mapping):
            raise ValueError(f'Candidate {candidate_id} has an invalid level union')
        level_id = str(union.get('level_id', f'level-{index + 1}'))
        if level_id in shapes:
            raise ValueError(f'Candidate {candidate_id} repeats level_id {level_id}')
        shapes[level_id] = _polygon(
            union, source=f'{model_path or source_study} ({level_id})')
        level_order.append(level_id)

    min_x, min_y, max_x, max_y = _envelope(shapes)
    span_x = max_x - min_x
    span_y = max_y - min_y
    normalised = {
        level_id: _normalise_polygon(
            shape, min_x=min_x, min_y=min_y,
            span_x=span_x, span_y=span_y)
        for level_id, shape in shapes.items()
    }
    areas = {level_id: float(shape.area) for level_id, shape in normalised.items()}
    total_area = sum(areas.values())
    if total_area <= GEOMETRY_TOLERANCE:
        raise ValueError(f'Candidate {candidate_id} has zero normalised area')

    return {
        'candidate_id': candidate_id,
        'grammar_id': str(row.get('grammar_id') or model.get('grammar_id') or 'unknown'),
        'source_study': str(source_study),
        'program_volume_model': str(model_path) if model_path else None,
        'program_volume_model_sha256': _sha256(model_path) if model_path else None,
        'topology_signature': row.get('topology_signature'),
        'program_volume_digest': row.get('program_volume_digest'),
        'level_ids': level_order,
        'normalized_shapes': normalised,
        'normalized_shape_signature': _shape_signature(normalised),
        'normalized_level_area_profile': {
            level_id: areas[level_id] / total_area for level_id in level_order
        },
        'normalization': {
            'source_xy_envelope': [min_x, min_y, max_x, max_y],
            'axis_spans': [span_x, span_y],
            'target': '[0,1] x [0,1]',
            'basis': 'Complete candidate level-union XY envelope; X and Y are normalized independently.',
        },
    }


def _load_study(path: Path, study_index: int) -> list[dict[str, Any]]:
    payload = _read_json(path)
    candidates = payload.get('candidates')
    if not isinstance(candidates, list):
        raise ValueError(f'Study {path} must contain a candidates list')
    loaded: list[dict[str, Any]] = []
    for index, row in enumerate(candidates):
        if not isinstance(row, Mapping):
            raise ValueError(f'Study {path} candidate {index} is not an object')
        reference = row.get('program_volume_model')
        model_path: Path | None = None
        if reference:
            model_path = _resolve_reference(str(reference), path)
            model = _read_json(model_path)
        elif isinstance(row.get('level_unions'), list):
            # Inline models make small protocol fixtures easy to inspect while
            # retaining the exact same measurement path as file-backed studies.
            model = {'level_unions': row['level_unions'],
                     'grammar_id': row.get('grammar_id')}
        else:
            raise ValueError(
                f'Study {path} candidate {index} has no program_volume_model')
        candidate_id = f'study-{study_index + 1}:candidate-{index + 1}'
        loaded.append(_candidate_from_model(
            row=row, model=model, candidate_id=candidate_id,
            source_study=path, model_path=model_path))
    return loaded


def _collision_groups(values: Mapping[str, Any]) -> list[list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for candidate_id, value in values.items():
        if value is None:
            continue
        grouped[str(value)].append(candidate_id)
    return [sorted(group) for group in grouped.values() if len(group) > 1]


def _stats(values: Iterable[float]) -> dict[str, float | None]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {'min': None, 'mean': None, 'max': None}
    return {
        'min': min(numbers),
        'mean': sum(numbers) / len(numbers),
        'max': max(numbers),
    }


def _pair_count(groups: Iterable[Iterable[str]]) -> int:
    return sum(
        count * (count - 1) // 2
        for count in (len(list(group)) for group in groups)
    )


def _profile_distance(
    first: Mapping[str, float], second: Mapping[str, float]
) -> float:
    level_ids = sorted(set(first) | set(second))
    return sum(
        (float(first.get(level_id, 0.0)) - float(second.get(level_id, 0.0))) ** 2
        for level_id in level_ids
    ) ** 0.5


def _pair_measurement(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    first_shapes: Mapping[str, Polygon] = first['normalized_shapes']
    second_shapes: Mapping[str, Polygon] = second['normalized_shapes']
    level_ids = sorted(set(first_shapes) | set(second_shapes))
    empty = Polygon()
    level_rows: list[dict[str, Any]] = []
    ratios: list[float] = []
    for level_id in level_ids:
        first_shape = first_shapes.get(level_id, empty)
        second_shape = second_shapes.get(level_id, empty)
        union_area = float(first_shape.union(second_shape).area)
        difference_area = float(first_shape.symmetric_difference(second_shape).area)
        ratio = difference_area / union_area if union_area > GEOMETRY_TOLERANCE else 0.0
        ratios.append(ratio)
        level_rows.append({
            'level_id': level_id,
            'normalized_symmetric_difference_area': difference_area,
            'normalized_union_area': union_area,
            'normalized_symmetric_difference_over_union': ratio,
        })
    profile_distance = _profile_distance(
        first['normalized_level_area_profile'],
        second['normalized_level_area_profile'])
    shape_collision = all(value <= GEOMETRY_TOLERANCE for value in ratios)
    profile_collision = profile_distance <= PROFILE_TOLERANCE
    return {
        'candidate_a': first['candidate_id'],
        'candidate_b': second['candidate_id'],
        'levels': level_rows,
        'shape_distance_summary': _stats(ratios),
        'profile_distance_l2': profile_distance,
        'collision': bool(shape_collision and profile_collision),
        'collision_basis': {
            'shape_tolerance': GEOMETRY_TOLERANCE,
            'profile_tolerance': PROFILE_TOLERANCE,
            'requires_all_level_shapes_and_profile': True,
        },
    }


def _tolerance_collision_groups(
    candidates: list[Mapping[str, Any]], pairs: list[Mapping[str, Any]]
) -> list[list[str]]:
    parent = {candidate['candidate_id']: candidate['candidate_id'] for candidate in candidates}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(first: str, second: str) -> None:
        root_first, root_second = find(first), find(second)
        if root_first != root_second:
            parent[root_second] = root_first

    for pair in pairs:
        if pair['collision']:
            union(pair['candidate_a'], pair['candidate_b'])
    groups: dict[str, list[str]] = defaultdict(list)
    for candidate_id in parent:
        groups[find(candidate_id)].append(candidate_id)
    return [sorted(group) for group in groups.values() if len(group) > 1]


def _grammar_report(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    topology = {candidate['candidate_id']: candidate['topology_signature']
                for candidate in candidates}
    digest = {candidate['candidate_id']: candidate['program_volume_digest']
              for candidate in candidates}
    normalized = {candidate['candidate_id']: candidate['normalized_shape_signature']
                  for candidate in candidates}
    topology_groups = _collision_groups(topology)
    digest_groups = _collision_groups(digest)
    normalized_groups = _collision_groups(normalized)
    pairs = [
        _pair_measurement(first, second)
        for first, second in itertools.combinations(candidates, 2)
    ]
    shape_pair_summaries = [
        pair['shape_distance_summary']['mean']
        for pair in pairs
        if pair['shape_distance_summary']['mean'] is not None
    ]
    profile_distances = [pair['profile_distance_l2'] for pair in pairs]
    return {
        'candidate_count': len(candidates),
        'candidate_ids': [candidate['candidate_id'] for candidate in candidates],
        'candidates': [
            {
                'candidate_id': candidate['candidate_id'],
                'source_study': candidate['source_study'],
                'program_volume_model': candidate['program_volume_model'],
                'program_volume_model_sha256':
                    candidate['program_volume_model_sha256'],
                'topology_signature': candidate['topology_signature'],
                'program_volume_digest': candidate['program_volume_digest'],
                'normalized_shape_signature': candidate['normalized_shape_signature'],
                'normalized_level_area_profile': candidate['normalized_level_area_profile'],
                'normalization': candidate['normalization'],
            }
            for candidate in candidates
        ],
        'raw': {
            'topology_signature_unique_count': len({value for value in topology.values() if value is not None}),
            'topology_signature_missing_count': sum(value is None for value in topology.values()),
            'topology_signature_collision_groups': topology_groups,
            'topology_signature_collision_pair_count': _pair_count(topology_groups),
            'program_volume_digest_unique_count': len({value for value in digest.values() if value is not None}),
            'program_volume_digest_missing_count': sum(value is None for value in digest.values()),
            'program_volume_digest_collision_groups': digest_groups,
            'program_volume_digest_collision_pair_count': _pair_count(digest_groups),
        },
        'normalized': {
            'normalized_shape_signature_unique_count': len(set(normalized.values())),
            'normalized_shape_signature_collision_groups': normalized_groups,
            'normalized_shape_signature_collision_pair_count': _pair_count(normalized_groups),
            'tolerance_collision_groups': _tolerance_collision_groups(candidates, pairs),
            'tolerance_collision_pair_count': sum(pair['collision'] for pair in pairs),
            'geometry_tolerance': GEOMETRY_TOLERANCE,
            'profile_tolerance': PROFILE_TOLERANCE,
        },
        'pairwise': {
            'pair_count': len(pairs),
            'pairs': pairs,
            'shape_distance_summary_over_pair_means': _stats(shape_pair_summaries),
            'profile_distance_summary': _stats(profile_distances),
        },
    }


def measure_studies(study_paths: Iterable[Path]) -> dict[str, Any]:
    paths = [Path(path) for path in study_paths]
    if not paths:
        raise ValueError('At least one --study path is required')
    candidates = [
        candidate
        for index, path in enumerate(paths)
        for candidate in _load_study(path, index)
    ]
    by_grammar: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_grammar[candidate['grammar_id']].append(candidate)
    return {
        'schema_version': SCHEMA_VERSION,
        'measurement_only': True,
        'authority': {
            'geometry_status': 'not_promoted',
            'current_geometry': False,
            'accepted_geometry': False,
            'statement': (
                'This report measures supplied study artifacts only. It does not '
                'promote a response, study, or candidate to current or accepted geometry.'),
        },
        'input_study_count': len(paths),
        'input_studies': [str(path) for path in paths],
        'input_study_sha256': {
            str(path): _sha256(path) for path in paths
        },
        'candidate_count': len(candidates),
        'grammar_count': len(by_grammar),
        'grammars': {
            grammar_id: _grammar_report(rows)
            for grammar_id, rows in sorted(by_grammar.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--study', action='append', type=Path, required=True,
        help='Path to a run_program_volume_study study.json; repeat for multiple inputs.')
    parser.add_argument(
        '--out', type=Path, required=True,
        help='JSON report path to write.')
    args = parser.parse_args()
    report = measure_studies(args.study)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8')


if __name__ == '__main__':
    main()
