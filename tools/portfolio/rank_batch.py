"""Read a batch's own reports and put the twenty rows side by side.

This ranks nothing about architecture. It reports what each run's verdicts already say
-- compliance rollup, spatial rules, dependency graph, unplaced program -- so a
selection for the portfolio can be made against the record rather than against a
render. A missing report stays missing; no field is filled in with a zero.

    python tools/portfolio/rank_batch.py artifacts/visual_audit/<batch> --csv out.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'docs' / 'experiments' / 'visual_music_corpus_20.json'


def corpus_index(path: Path = CORPUS) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    auxiliary = set(payload.get('auxiliary_tracks', []))
    return {row['id']: row for row in payload['tracks'] if row['id'] not in auxiliary}


def read_row(batch: Path, result: dict) -> dict:
    track = result['track_id']
    row = {
        'track_id': track,
        'status': result.get('status'),
        'typology': result.get('typology'),
        'structural_system': result.get('structural_system'),
        'facade_grammar': result.get('facade_grammar'),
        'elements': result.get('elements'),
        'model_id': result.get('model_id'),
        'seconds': result.get('elapsed_seconds'),
    }
    response_path = batch / 'tracks' / track / 'response.json'
    if result.get('status') != 'compiled' or not response_path.is_file():
        return row
    response = json.loads(response_path.read_text(encoding='utf-8'))
    analysis = response.get('analysis') or {}

    compliance = analysis.get('compliance') or {}
    row.update(passed=compliance.get('passed_total'),
               failed=compliance.get('failed_total'),
               unevaluated=compliance.get('unevaluated_total'))

    spatial = analysis.get('spatial') or {}
    findings = spatial.get('findings') or []
    row.update(spatial_status=spatial.get('status'), spatial_findings=len(findings))

    dependency = analysis.get('dependency_graph') or {}
    row['dependency_status'] = dependency.get('status')

    allocation = analysis.get('program_allocation') or {}
    unplaced = allocation.get('unplaced') or []
    row.update(unplaced=len(unplaced),
               required_m2=allocation.get('required_area_m2'),
               delivered_m2=allocation.get('delivered_area_m2'))

    gates = analysis.get('facade_gates') or {}
    row['facade_gates'] = gates.get('status') if isinstance(gates, dict) else None

    lattice = analysis.get('lattice') or {}
    levels = lattice.get('levels') or lattice.get('level_lines') or []
    row['levels'] = len(levels) if isinstance(levels, list) else None

    volumes = analysis.get('program_volume_model') or {}
    row['program_volumes'] = len(volumes.get('volumes') or []) if volumes else None

    row['sized_elements'] = analysis.get('sized_element_count')
    return row


def cleanliness(row: dict) -> tuple:
    """Sort key: fewest open questions first, then most of the brief actually placed.

    Every term is a verdict the run already published. `False` sorts before `True`,
    so each boolean is written as the failure it is testing for.
    """
    return (
        row.get('status') != 'compiled',
        (row.get('failed') or 0) > 0,
        row.get('dependency_status') != 'passed',
        row.get('spatial_status') == 'failed',
        row.get('unplaced') or 0,
        row.get('spatial_findings') or 0,
        row.get('unevaluated') or 0,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('batch', type=Path)
    parser.add_argument('--csv', type=Path)
    parser.add_argument('--json', type=Path)
    parser.add_argument('--corpus', type=Path, default=CORPUS)
    args = parser.parse_args()

    batch = args.batch.resolve()
    results = json.loads((batch / 'batch_results.json').read_text(encoding='utf-8'))
    corpus = corpus_index(args.corpus)
    # The manifest names the set being reported on. A batch directory can accumulate
    # runs outside that set, and a roll-up that quietly widened to whatever the folder
    # held would stop matching the plate it is meant to document.
    results = [result for result in results if result['track_id'] in corpus]
    missing = set(corpus) - {result['track_id'] for result in results}
    if missing:
        raise SystemExit('the batch has no result for: ' + ', '.join(sorted(missing)))
    rows = [read_row(batch, result) for result in results]
    for row in rows:
        entry = corpus.get(row['track_id'], {})
        row['title'] = entry.get('title', row['track_id'])
        row['style'] = entry.get('style', '')
    rows.sort(key=cleanliness)

    header = (f'{"#":>2}  {"track":24s} {"typology":9s} {"elem":>6s} {"lvl":>3s} '
              f'{"pass":>4s} {"fail":>4s} {"uneval":>6s} {"spatial":10s} {"deps":8s} '
              f'{"unplaced":>8s}  facade')
    print(header)
    print('-' * len(header))
    for index, row in enumerate(rows, 1):
        print(f'{index:2d}  {row["track_id"]:24.24s} '
              f'{str(row.get("typology") or "-"):9.9s} '
              f'{row.get("elements") or 0:6d} {row.get("levels") or 0:3d} '
              f'{row.get("passed") or 0:4d} {row.get("failed") or 0:4d} '
              f'{row.get("unevaluated") or 0:6d} '
              f'{str(row.get("spatial_status") or "-"):10.10s} '
              f'{str(row.get("dependency_status") or "-"):8.8s} '
              f'{row.get("unplaced") if row.get("unplaced") is not None else "-":>8} '
              f' {str(row.get("facade_grammar") or "-")}')

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        fields = sorted({key for row in rows for key in row})
        with args.csv.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f'\ncsv  -> {args.csv}')
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, indent=1), encoding='utf-8')
        print(f'json -> {args.json}')


if __name__ == '__main__':
    main()
