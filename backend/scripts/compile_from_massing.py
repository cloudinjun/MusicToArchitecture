"""Build a model and its drawing set from a program massing alone (decision 0022).

    .venv/Scripts/python.exe backend/scripts/compile_from_massing.py \
        --massing docs/contracts/program_massing.v1.example.json \
        --out artifacts/massing_runs/example [--glb]

Or write the massing a compiled model stands on, to edit and feed back:

    .venv/Scripts/python.exe backend/scripts/compile_from_massing.py \
        --export-of artifacts/v3_demo/building_model_v3.json --out artifacts/massing_runs/demo

Or print what a zone writer needs -- the brief with its numbers and each storey's
usable floor after cores and carve -- without compiling (decision 0023); with
--export-of, --with-zones also writes every room the run placed as a single-room zone:

    .venv/Scripts/python.exe backend/scripts/compile_from_massing.py         --massing docs/contracts/program_massing.v1.example.json --brief --out artifacts/massing_runs/example

No recording is involved. The massing's plates, grid, cores and datum values are
the input; the compiler tail that a music run uses after its plate is settled runs
unchanged on them, and the same drawing issue follows.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.drawings import issue_drawings, write_drawing_set  # noqa: E402
from backend.app.models_v3 import BuildingModelV3  # noqa: E402
from backend.app.program_massing import (  # noqa: E402
    brief_for_massing, compile_from_massing, load_program_massing, program_massing_of,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--massing', type=Path, help='ProgramMassing JSON to build from')
    parser.add_argument('--export-of', type=Path,
                        help='A building_model_v3.json whose massing to write instead')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--glb', action='store_true',
                        help='Also export the web model through the existing Blender chain')
    parser.add_argument('--with-zones', action='store_true',
                        help='With --export-of: write every placed room as a single-room zone')
    parser.add_argument('--brief', action='store_true',
                        help='With --massing: write brief.json (brief and usable floor per '
                             'storey) and stop; no compile')
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    if args.export_of:
        model = BuildingModelV3.model_validate_json(
            args.export_of.read_text(encoding='utf-8'))
        massing = program_massing_of(model, with_zones=args.with_zones)
        target = out / 'program_massing.json'
        target.write_text(massing.model_dump_json(indent=2), encoding='utf-8')
        print(f'wrote {target}: {len(massing.levels)} levels, {len(massing.cores)} cores, '
              f'grid {len(massing.grid.x_lines)}x{len(massing.grid.y_lines)}')
        if not args.massing:
            return

    if not args.massing:
        raise SystemExit('give --massing or --export-of')
    massing = load_program_massing(args.massing)
    if args.brief:
        brief = brief_for_massing(massing)
        target = out / 'brief.json'
        target.write_text(json.dumps(brief, indent=2), encoding='utf-8')
        print(f'wrote {target}')
        for level in brief['levels']:
            print(f"{level['id']} {level['kind']} bbox {level['bbox']} plate {level['plate_m2']} m2 "
                  f"usable {level['usable_m2']} m2 carved {len(level['carved'])}")
        for space in brief['brief']:
            flag = ' (archetype)' if space['settled_by_archetype'] else ''
            print(f"{space['id']:<18} {space['area_m2']:>7.0f} m2  min {space['min_dimension_m']:>4.1f} m  "
                  f"{space['level_preference']:<6} {space['daylight']:<9} {space['label']}{flag}")
        return
    started = time.perf_counter()
    model = compile_from_massing(massing)
    (out / 'building_model_v3.json').write_text(model.model_dump_json(), encoding='utf-8')
    issued = issue_drawings(model)
    drawings = write_drawing_set(issued, model, directory=out / 'drawings')
    summary = {
        'model_id': model.model_id, 'massing_digest': massing.digest(),
        'typology': model.typology, 'elements': sum(model.element_counts.values()),
        'levels': [level.id for level in model.lattice.levels],
        'cores': [core.model_dump() for core in model.lattice.given_cores],
        'openings': next((note for note in model.limitations
                          if note.startswith('Stair and lift openings')), ''),
        'program': next((note for note in model.limitations
                         if note.startswith('Program:')), ''),
        'unplaced': [{'space_id': u.space_id, 'label': u.label,
                      'area_required_m2': u.area_required_m2, 'reason': u.reason}
                     for u in model.program_allocation.unplaced],
        'zones': [report.model_dump() for report in model.program_allocation.zone_reports],
        'fulfilment': model.program_allocation.fulfilment,
        'spatial_status': model.spatial.status if model.spatial else None,
        'dependency_status': model.dependency_graph.status,
        'drawings': len(issued.sheets) or len(issued.all),
        'drawing_directory': str(drawings),
        'seconds': round(time.perf_counter() - started, 1),
    }
    if args.glb:
        from backend.app.blender_export_v3 import export_blender_web_model_v3
        asset = export_blender_web_model_v3(model, render=False)
        summary['web_asset'] = asset.model_dump(mode='json')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    for key, value in summary.items():
        if key not in ('cores', 'zones', 'unplaced'):
            print(f'{key}: {value}')
    for report in summary['zones']:
        print(f"zone '{report['label']}' on {report['level_id']}: usable {report['area_usable_m2']:.0f} m2, "
              f"rows {report['area_rows_m2']:.0f} m2, asked {report['area_required_m2']:.0f} m2, "
              f"delivered {report['area_delivered_m2']:.0f} m2"
              + (f", not fitted: {', '.join(report['unplaced'])}" if report['unplaced'] else ''))
    for u in summary['unplaced']:
        print(f"unplaced {u['space_id']} ({u['area_required_m2']:.0f} m2): {u['reason']}")


if __name__ == '__main__':
    main()
