"""Put one already-compiled run in front of the workbench, temporarily.

The published demo (`web/public/reports/demo_run.json`) belongs to whatever
`publish_model_version` last promoted, and promotion is a project decision. Portfolio
screenshots only need the browser to read a different payload for a few minutes, so
this stages a batch run beside the published assets, keeps a backup of the two report
files it overwrites, and restores them on `--restore`.

Nothing is recompiled: the payload, the GLB, the sheets and the stills all come from
the batch that already produced them.

    python tools/portfolio/stage_web_demo.py <batch> --track carefree
    python tools/portfolio/stage_web_demo.py --restore
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web' / 'public'
REPORTS = WEB / 'reports'
BACKUP = ROOT / 'artifacts' / 'portfolio_plates' / '_web_demo_backup'
CORPUS = ROOT / 'docs' / 'experiments' / 'visual_music_corpus_20.json'
STAGED = BACKUP / 'staged.json'


def backup_reports() -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    for name in ('demo_run.json', 'translation_report.json'):
        source = REPORTS / name
        target = BACKUP / name
        if source.is_file() and not target.is_file():
            shutil.copy2(source, target)
            print(f'  backed up {name}')


def restore() -> None:
    if not (BACKUP / 'demo_run.json').is_file():
        raise SystemExit(f'No backup to restore in {BACKUP}')
    for name in ('demo_run.json', 'translation_report.json'):
        source = BACKUP / name
        if source.is_file():
            shutil.copy2(source, REPORTS / name)
            print(f'  restored {name}')
    if STAGED.is_file():
        staged = json.loads(STAGED.read_text(encoding='utf-8'))
        for relative in staged.get('copied_dirs', []):
            path = WEB / relative
            if path.is_dir():
                shutil.rmtree(path)
                print(f'  removed {relative}')
        for relative in staged.get('copied_files', []):
            path = WEB / relative
            if path.is_file():
                path.unlink()
        STAGED.unlink()
    print('the published demo is back in place')


def copy_into(source_dir: Path, target_dir: Path, pattern: str) -> int:
    if not source_dir.is_dir():
        return 0
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(source_dir.glob(pattern)):
        shutil.copy2(path, target_dir / path.name)
        count += 1
    return count


def audio_for(track: str) -> Path | None:
    payload = json.loads(CORPUS.read_text(encoding='utf-8-sig'))
    for row in payload['tracks']:
        if row['id'] == track:
            path = Path(row['local_path'])
            return path if path.is_file() else None
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('batch', type=Path, nargs='?')
    parser.add_argument('--track')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()

    if args.restore:
        restore()
        return
    if not args.batch or not args.track:
        raise SystemExit('Pass a batch directory and --track, or --restore')

    batch = args.batch.resolve()
    response_path = batch / 'tracks' / args.track / 'response.json'
    response = json.loads(response_path.read_text(encoding='utf-8'))
    model_id = response['analysis']['model_id']

    backup_reports()
    copied_dirs, copied_files = [], []

    glb = batch / 'models' / f'{model_id}.glb'
    manifest = batch / 'models' / f'{model_id}.manifest.json'
    generated = WEB / 'models' / 'generated'
    generated.mkdir(parents=True, exist_ok=True)
    for path in (glb, manifest):
        if not path.is_file():
            raise SystemExit(f'The batch has no {path.name}')
        shutil.copy2(path, generated / path.name)
        copied_files.append(f'models/generated/{path.name}')
    asset = response.get('model_asset_v3') or {}
    asset['asset_url'] = f'/models/generated/{model_id}.glb'
    asset['manifest_url'] = f'/models/generated/{model_id}.manifest.json'
    response['model_asset_v3'] = asset

    sheets = copy_into(batch / 'drawings' / model_id,
                       WEB / 'drawings' / model_id, '*.svg')
    if sheets:
        copied_dirs.append(f'drawings/{model_id}')
    for sheet in response.get('drawing_sheets') or []:
        sheet['url'] = f'/drawings/{model_id}/{sheet["id"]}.svg'

    stills = copy_into(batch / 'geometry' / model_id,
                       WEB / 'renders' / model_id, '*.png')
    if stills:
        copied_dirs.append(f'renders/{model_id}')
    for render in response.get('renders') or []:
        render['url'] = f'/renders/{model_id}/{render["filename"]}'

    recording = audio_for(args.track)
    if recording is not None:
        (WEB / 'audio').mkdir(parents=True, exist_ok=True)
        shutil.copy2(recording, WEB / 'audio' / recording.name)
        copied_files.append(f'audio/{recording.name}')
        response['audio_url'] = f'/audio/{recording.name}'

    # The v2 preview is a separate asset; the workbench only needs it not to 404.
    v2 = response.get('model_asset') or {}
    v2_name = Path((v2.get('asset_url') or '')).name
    if v2_name:
        v2_source = batch / 'models' / v2_name
        if v2_source.is_file():
            shutil.copy2(v2_source, generated / v2_name)
            copied_files.append(f'models/generated/{v2_name}')
            v2['asset_url'] = f'/models/generated/{v2_name}'
            manifest_name = v2_name.replace('.glb', '.manifest.json')
            if (batch / 'models' / manifest_name).is_file():
                shutil.copy2(batch / 'models' / manifest_name, generated / manifest_name)
                copied_files.append(f'models/generated/{manifest_name}')
                v2['manifest_url'] = f'/models/generated/{manifest_name}'
            response['model_asset'] = v2

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / 'demo_run.json').write_text(
        json.dumps(response, ensure_ascii=False), encoding='utf-8')
    report = response.get('translation_report')
    if report is not None:
        (REPORTS / 'translation_report.json').write_text(
            json.dumps(report, ensure_ascii=False), encoding='utf-8')

    STAGED.parent.mkdir(parents=True, exist_ok=True)
    STAGED.write_text(json.dumps({'track': args.track, 'model_id': model_id,
                                  'batch': str(batch), 'copied_dirs': copied_dirs,
                                  'copied_files': copied_files}, indent=1),
                      encoding='utf-8')
    print(f'staged {args.track} ({model_id}): {sheets} sheets, {stills} stills')
    print(f'restore with: python tools/portfolio/stage_web_demo.py --restore')


if __name__ == '__main__':
    main()
