"""Render portfolio views for every compiled track in an audit batch.

The batch's own `.blend` files are the input, so what gets photographed is the model the
run actually shipped rather than a re-import of it. Tracks that failed to compile are
skipped and named in the summary; a missing `.blend` is reported, never silently
replaced by an older one.

    python tools/portfolio/render_batch.py artifacts/visual_audit/<batch> \
        --out artifacts/portfolio_plates/<batch> --views hero,elevation
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RENDER_SCRIPT = ROOT / 'tools' / 'portfolio' / 'render_portfolio_views.py'
BLENDER_CANDIDATES = (
    r'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe',
    r'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe',
    r'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe',
)


def find_blender() -> Path:
    for candidate in BLENDER_CANDIDATES:
        if Path(candidate).is_file():
            return Path(candidate)
    found = shutil.which('blender')
    if found:
        return Path(found)
    raise SystemExit('Blender was not found; pass --blender')


def track_rows(batch: Path) -> list[dict]:
    results = batch / 'batch_results.json'
    if results.is_file():
        return json.loads(results.read_text(encoding='utf-8'))
    return [json.loads(path.read_text(encoding='utf-8'))
            for path in sorted((batch / 'tracks').glob('*/result.json'))]


def blend_for(batch: Path, model_id: str) -> Path | None:
    for candidate in (batch / 'native' / f'{model_id}.blend',
                      ROOT / '.codex_tmp' / 'visual-music-audit-20260903' / batch.name
                      / f'{model_id}.blend',
                      ROOT / 'blender' / 'generated' / f'{model_id}.blend'):
        if candidate.is_file():
            return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('batch', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--views', default='hero,aerial,elevation,plan')
    parser.add_argument('--layer-views', default='')
    parser.add_argument('--width', type=int, default=1800)
    parser.add_argument('--height', type=int, default=1200)
    parser.add_argument('--samples', type=int, default=96)
    parser.add_argument('--blender', type=Path)
    parser.add_argument('--only', default='', help='Comma-separated track ids')
    parser.add_argument('--force', action='store_true',
                        help='Re-render tracks that already have a views manifest')
    args = parser.parse_args()

    blender = args.blender or find_blender()
    batch = args.batch.resolve()
    out_root = args.out.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    only = {t.strip() for t in args.only.split(',') if t.strip()}

    rendered, skipped = [], []
    for row in track_rows(batch):
        track = row['track_id']
        if only and track not in only:
            continue
        if row.get('status') != 'compiled':
            skipped.append({'track_id': track, 'reason': row.get('status', 'unknown')})
            print(f'SKIP {track}: {row.get("status")}')
            continue
        blend = blend_for(batch, row['model_id'])
        if blend is None:
            skipped.append({'track_id': track, 'reason': 'blend missing'})
            print(f'SKIP {track}: no .blend for {row["model_id"]}')
            continue
        destination = out_root / track
        if (destination / 'views_manifest.json').is_file() and not args.force:
            print(f'HAVE {track}')
            rendered.append({'track_id': track, 'model_id': row['model_id'],
                             'out': str(destination), 'reused': True})
            continue
        command = [
            str(blender), '--background', str(blend), '--factory-startup',
            '--python-exit-code', '1', '--python', str(RENDER_SCRIPT), '--',
            '--out', str(destination), '--label', track,
            '--views', args.views, '--width', str(args.width),
            '--height', str(args.height), '--samples', str(args.samples),
        ]
        if args.layer_views:
            command += ['--layer-views', args.layer_views]
        start = time.perf_counter()
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                timeout=1800)
        elapsed = time.perf_counter() - start
        if result.returncode != 0 or not (destination / 'views_manifest.json').is_file():
            (destination).mkdir(parents=True, exist_ok=True)
            (destination / 'render.log').write_text(result.stdout + result.stderr,
                                                    encoding='utf-8')
            skipped.append({'track_id': track, 'reason': 'render failed'})
            print(f'FAIL {track} ({elapsed:.0f}s); see {destination / "render.log"}')
            continue
        rendered.append({'track_id': track, 'model_id': row['model_id'],
                         'typology': row.get('typology'),
                         'structural_system': row.get('structural_system'),
                         'facade_grammar': row.get('facade_grammar'),
                         'massing': row.get('massing'), 'elements': row.get('elements'),
                         'blend': str(blend), 'out': str(destination),
                         'seconds': round(elapsed, 1), 'reused': False})
        print(f'OK   {track} {elapsed:.0f}s -> {destination.name}')

    (out_root / 'batch_render_manifest.json').write_text(
        json.dumps({'batch': str(batch), 'views': args.views,
                    'layer_views': args.layer_views,
                    'rendered': rendered, 'skipped': skipped}, indent=1),
        encoding='utf-8')
    print(f'\n{len(rendered)} rendered, {len(skipped)} skipped -> {out_root}')


if __name__ == '__main__':
    sys.exit(main())
