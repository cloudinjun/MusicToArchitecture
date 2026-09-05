"""Run the real API pipeline on a licensed corpus, preserving each evidence state.

This driver changes output destinations only. Audio analysis, selection, geometry,
reports, Blender export and drawings all belong to ``compile_generation``.
Visual judgments are recorded separately; a successful compile is not a visual pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import traceback
from pathlib import Path

from backend.app import blender_export, blender_export_v3, drawings, pipeline
from backend.app.version import COMPILER_VERSION

ROOT = Path(__file__).resolve().parents[2]
CODE_ROOT = ROOT


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def file_hash(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def source_hashes() -> dict[str, str]:
    paths = [*CODE_ROOT.glob('backend/app/*.py'), *CODE_ROOT.glob('blender/*.py')]
    return {p.relative_to(CODE_ROOT).as_posix(): file_hash(p) for p in sorted(paths)}


def configure_outputs(output: Path) -> None:
    # Exporters require paths relative to the repository for their API contracts.
    # Keep disposable native scenes in a narrowly scoped .codex_tmp directory.
    native = ROOT / '.codex_tmp' / 'visual-music-audit-20260903' / output.name
    for exporter in (blender_export, blender_export_v3):
        exporter.ROOT = ROOT
        exporter.WEB_ASSET_DIRECTORY = output / 'models'
        exporter.BLEND_DIRECTORY = native
    blender_export.STATE_DIRECTORY = output / 'v2_states'
    blender_export_v3.RENDER_DIRECTORY = output / 'geometry'
    pipeline.RENDER_DIRECTORY = output / 'geometry'
    drawings.DRAWING_DIRECTORY = output / 'drawings'


def main() -> None:
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workspace-root', type=Path, default=ROOT,
                        help='Artifact workspace when executing a frozen source copy')
    parser.add_argument('--track', action='append', help='Select ids; default all tracks')
    args = parser.parse_args()
    ROOT = args.workspace_root.resolve()
    output = args.output.resolve()
    output.relative_to(ROOT)
    corpus = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    tracks = corpus['tracks'] if isinstance(corpus, dict) else corpus
    if isinstance(corpus, dict):
        auxiliary = set(corpus.get('auxiliary_tracks', []))
        tracks = [t for t in tracks if t['id'] not in auxiliary]
    if args.track:
        tracks = [t for t in tracks if t['id'] in args.track]
    if not tracks:
        raise SystemExit('No matching tracks')
    configure_outputs(output)
    hashes = source_hashes()
    identity = {'compiler_version': COMPILER_VERSION, 'source_sha256': hashes,
                'input_policy': 'full_downloaded_recording',
                'authority': 'presentation_only', 'pipeline': 'backend.app.pipeline.compile_generation'}
    identity_path = output / 'source_identity.json'
    if identity_path.exists() and json.loads(identity_path.read_text(encoding='utf-8')) != identity:
        raise SystemExit('Output belongs to a different compiler; use a new directory')
    write_json(identity_path, identity)
    results = []
    for track in tracks:
        track = dict(track, sha256=track['sha256'].lower())
        track_dir = output / 'tracks' / track['id']
        result_path = track_dir / 'result.json'
        if result_path.exists():
            previous = json.loads(result_path.read_text(encoding='utf-8'))
            if previous['audio_sha256'] != track['sha256']:
                raise SystemExit(f"A different recording already owns {track['id']}")
            results.append(previous)
            print(f"PRESERVED {track['id']}", flush=True)
            continue
        audio = Path(track['local_path'])
        if not audio.is_file() or file_hash(audio) != track['sha256']:
            raise SystemExit(f"Source missing or hash changed: {track['id']}")
        print(f"START {track['id']} ({audio.stat().st_size / 1048576:.1f} MB)", flush=True)
        start = time.perf_counter()
        result = {'track_id': track['id'], 'audio_sha256': track['sha256'],
                  'source': track, 'manifest_sha256': file_hash(args.manifest),
                  'visual_review': 'pending'}
        try:
            response = pipeline.compile_generation(audio, audio.name, render=True)
            write_json(track_dir / 'response.json', response.model_dump(mode='json'))
            asset = response.model_asset_v3
            analysis = response.analysis
            if asset is None or analysis is None:
                raise RuntimeError('Pipeline returned without the v3 asset or analysis')
            geometry_dir = output / 'geometry' / analysis.model_id
            evidence_paths = [*geometry_dir.glob('*.png'), geometry_dir / 'building_model_v3.json',
                              output / 'models' / f'{analysis.model_id}.glb']
            result.update(status='compiled', run_id=response.run_id, model_id=analysis.model_id,
                          typology=analysis.typology,
                          massing=analysis.selection.massing_id if analysis.selection else None,
                          structural_system=analysis.structural_system_id,
                          facade_grammar=analysis.facade_grammar_id,
                          duration_seconds=response.audio_features.provenance.duration_seconds,
                          elements=analysis.element_count,
                          evidence=[{'path': p.relative_to(ROOT).as_posix(), 'sha256': file_hash(p)}
                                    for p in evidence_paths])
        except Exception as error:
            result.update(status='failed', error=f'{type(error).__name__}: {error}')
            track_dir.mkdir(parents=True, exist_ok=True)
            (track_dir / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        result['elapsed_seconds'] = round(time.perf_counter() - start, 2)
        result['source_unchanged'] = hashes == source_hashes()
        write_json(result_path, result)
        results.append(result)
        write_json(output / 'batch_results.json', results)
        print(f"{result['status'].upper()} {track['id']} {result['elapsed_seconds']}s "
              f"{result.get('massing', result.get('error', ''))}", flush=True)
        if not result['source_unchanged']:
            raise SystemExit('Compiler files changed during the experiment; preserved evidence and stopped')
    # A manifest can arrive in batches while licensing/download work proceeds. Every
    # track retains the exact source metadata and manifest hash it actually used.
    all_results = [json.loads(p.read_text(encoding='utf-8'))
                   for p in sorted((output / 'tracks').glob('*/result.json'))]
    write_json(output / 'batch_results.json', all_results)


if __name__ == '__main__':
    main()
