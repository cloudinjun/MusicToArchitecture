"""Run the real API pipeline on a licensed corpus, preserving each evidence state.

This driver changes output destinations only. Audio analysis, selection, geometry,
reports, Blender export and drawings all belong to ``compile_generation``.
Visual judgments are recorded separately; a successful compile is not a visual pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import traceback
from pathlib import Path

from backend.app import blender_export, blender_export_v3, drawings, pipeline
from backend.app.asset_lineage import validate_blender_lineage, validate_render_lineage
from backend.app.version import COMPILER_VERSION

ROOT = Path(__file__).resolve().parents[2]
CODE_ROOT = ROOT


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f'.{os.getpid()}.partial')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def file_hash(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def source_hashes() -> dict[str, str]:
    paths = [*CODE_ROOT.glob('backend/app/**/*.py'), *CODE_ROOT.glob('blender/**/*.py'),
             *CODE_ROOT.glob('rhino/**/*.py')]
    return {p.relative_to(CODE_ROOT).as_posix(): file_hash(p) for p in sorted(paths)}


def configure_outputs(output: Path, *, package_native: bool = False) -> None:
    # Exporters require paths relative to the repository for their API contracts.
    # Ordinary audit scenes are disposable.  A requested native delivery belongs
    # beside the run so its hash and model identity travel with the evidence pack.
    native = (output / 'native' if package_native else
              ROOT / '.codex_tmp' / 'visual-music-audit-20260903' / output.name)
    for exporter in (blender_export, blender_export_v3):
        exporter.ROOT = ROOT
        exporter.WEB_ASSET_DIRECTORY = output / 'models'
        exporter.BLEND_DIRECTORY = native
    blender_export.STATE_DIRECTORY = output / 'v2_states'
    blender_export_v3.RENDER_DIRECTORY = output / 'geometry'
    pipeline.RENDER_DIRECTORY = output / 'geometry'
    drawings.DRAWING_DIRECTORY = output / 'drawings'


def _read_bound_model_id(path: Path, expected: str, label: str) -> dict:
    """Read a JSON artifact and require it to belong to this model identity."""
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f'{label} is unreadable: {path}') from error
    if not isinstance(payload, dict) or payload.get('model_id') != expected:
        observed = payload.get('model_id') if isinstance(payload, dict) else None
        raise RuntimeError(
            f'{label} belongs to model {observed!r}, expected {expected!r}: {path}')
    return payload


def v3_evidence_paths(model_id: str, expected_drawing_index: dict | None) -> list[Path]:
    """Inventory one isolated v3 export from its configured physical directories.

    ``ModelAssetV3.asset_url`` remains a browser route even when an audit redirects
    the exporter into an isolated directory.  The exporter constants are the physical
    contract; deriving a local file from that public URL silently pointed audits back
    at ``web/public``.  The drawing directory follows the same rule.
    """
    web_directory = Path(blender_export_v3.WEB_ASSET_DIRECTORY)
    blend_directory = Path(blender_export_v3.BLEND_DIRECTORY)
    render_directory = Path(blender_export_v3.RENDER_DIRECTORY) / model_id
    drawing_directory = Path(drawings.DRAWING_DIRECTORY) / model_id
    glb_path = web_directory / f'{model_id}.glb'
    manifest_path = web_directory / f'{model_id}.manifest.json'
    blend_path = blend_directory / f'{model_id}.blend'
    model_path = render_directory / 'building_model_v3.json'
    drawing_index_path = drawing_directory / 'index.json'
    required = [glb_path, manifest_path, blend_path, model_path, drawing_index_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError('Required v3 evidence is missing: ' + ', '.join(missing))

    manifest = _read_bound_model_id(manifest_path, model_id, 'Blender manifest')
    model = _read_bound_model_id(model_path, model_id, 'building_model_v3.json')
    try:
        validate_blender_lineage(model, manifest, blend_path, glb_path)
    except ValueError as error:
        raise RuntimeError(f'Blender evidence lineage failed for {model_id}: {error}') from error
    drawing_index = _read_bound_model_id(
        drawing_index_path, model_id, 'drawing index')
    if expected_drawing_index is None or drawing_index != expected_drawing_index:
        raise RuntimeError(
            'Drawing index on disk does not match the index returned by this pipeline run')
    expected_svg_names = {
        f"{sheet['id']}.svg"
        for sheet in drawing_index.get('sheets', [])
        if isinstance(sheet, dict) and isinstance(sheet.get('id'), str)
    }
    svg_paths = sorted(drawing_directory.glob('*.svg'))
    actual_svg_names = {path.name for path in svg_paths}
    if not expected_svg_names or actual_svg_names != expected_svg_names:
        raise RuntimeError(
            'Drawing SVG inventory does not match its index: '
            f'missing={sorted(expected_svg_names - actual_svg_names)}, '
            f'unexpected={sorted(actual_svg_names - expected_svg_names)}')
    render_paths = sorted(render_directory.glob('*.png'))
    expected_render_names = set(manifest.get('renders', []))
    actual_render_names = {path.name for path in render_paths}
    if actual_render_names != expected_render_names:
        raise RuntimeError(
            'Render inventory does not match its Blender manifest: '
            f'missing={sorted(expected_render_names - actual_render_names)}, '
            f'unexpected={sorted(actual_render_names - expected_render_names)}')
    try:
        for path in render_paths:
            validate_render_lineage(manifest, path)
    except ValueError as error:
        raise RuntimeError(f'Render evidence lineage failed for {model_id}: {error}') from error
    return [
        glb_path,
        manifest_path,
        blend_path,
        model_path,
        drawing_index_path,
        *svg_paths,
        *render_paths,
    ]


def evidence_records(paths: list[Path], *, run_id: str, model_id: str) -> list[dict]:
    """Hash each distinct artifact and bind it to the run/model that emitted it."""
    root = ROOT.resolve()
    records = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.is_file():
            raise RuntimeError(f'Evidence artifact is missing: {resolved}')
        try:
            relative = resolved.relative_to(root)
        except ValueError as error:
            raise RuntimeError(f'Evidence artifact escaped the audit workspace: {resolved}') from error
        records.append({
            'path': relative.as_posix(),
            'sha256': file_hash(resolved),
            'run_id': run_id,
            'model_id': model_id,
        })
    return records


def main(argv: list[str] | None = None) -> None:
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workspace-root', type=Path, default=ROOT,
                        help='Artifact workspace when executing a frozen source copy')
    parser.add_argument('--track', action='append', help='Select ids; default all tracks')
    parser.add_argument('--fixed-snapshot', action='store_true',
                        help='Use verified snapshot inputs and preserve native files in the normal model directories')
    parser.add_argument('--review', action='store_true', help='Render bound diagnostic views')
    parser.add_argument('--rhino', action='store_true', help='Save and read back a paired native Rhino candidate')
    parser.add_argument('--program-volume', action='store_true',
                        help='Compile v3 through the score-authored Program Volume protocol')
    parser.add_argument('--project-brief', type=Path,
                        help='Validated site/area brief; selects bounded Program Volume mode')
    parser.add_argument('--layout-controls', type=Path,
                        help='Optional LegacyLayoutControls JSON for the bounded brief')
    parser.add_argument('--package-native', action='store_true',
                        help='Keep the generated .blend inside this audit deliverable')
    args = parser.parse_args(argv)
    bounded_inputs = {}
    if args.project_brief:
        from backend.app.project_brief import ProjectBrief
        bounded_inputs['project_brief'] = ProjectBrief.model_validate_json(args.project_brief.read_text(encoding='utf-8'))
        args.program_volume = True
    if args.layout_controls:
        from backend.app.legacy_program_layout import LegacyLayoutControls
        if not args.project_brief:
            parser.error('--layout-controls requires --project-brief')
        raw_controls = json.loads(args.layout_controls.read_text(encoding='utf-8'))
        bounded_inputs['legacy_controls'] = LegacyLayoutControls.model_validate(raw_controls.get('controls', raw_controls))
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
    snapshot = None
    if args.fixed_snapshot:
        from backend.scripts.freeze_generation_source import verify
        if ROOT != CODE_ROOT.resolve():
            raise ValueError('A fixed run must execute its own snapshot source')
        snapshot = verify(ROOT)
    else:
        if args.package_native:
            configure_outputs(output, package_native=True)
        else:
            # Preserve the one-argument call for existing audit integrations.
            configure_outputs(output)
    hashes = source_hashes()
    v3_mode = 'program_volume' if args.program_volume else 'legacy'
    identity = {'compiler_version': COMPILER_VERSION, 'source_sha256': hashes,
                'input_policy': 'full_downloaded_recording',
                'authority': 'presentation_only',
                'pipeline': 'backend.app.pipeline.compile_generation',
                'v3_mode': v3_mode,
                'native_delivery': bool(args.package_native or args.fixed_snapshot)}
    if bounded_inputs:
        identity['bounded_inputs'] = {
            name: value.model_dump(mode='json') for name,value in bounded_inputs.items()}
    if snapshot:
        identity.update(source_inventory_sha256=snapshot['inventory_sha256'],
                        diagnostic_views=args.review, native_rhino=args.rhino)
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
        audio = (ROOT / snapshot['corpus_inputs'][track['id']]
                 if snapshot else Path(track['local_path']))
        if not audio.is_file() or file_hash(audio) != track['sha256']:
            raise SystemExit(f"Source missing or hash changed: {track['id']}")
        print(f"START {track['id']} ({audio.stat().st_size / 1048576:.1f} MB)", flush=True)
        start = time.perf_counter()
        result = {'track_id': track['id'], 'audio_sha256': track['sha256'],
                  'source': track, 'manifest_sha256': file_hash(args.manifest),
                  'visual_review': 'pending', 'v3_mode': v3_mode,
                  'native_delivery': bool(args.package_native or args.fixed_snapshot)}
        try:
            # Preserve the historical call shape unless the new protocol was selected.
            # This also leaves the pinned-candidate wrapper's legacy interception intact.
            if args.program_volume:
                response = pipeline.compile_generation(
                    audio, audio.name, render=True, v3_mode='program_volume', **bounded_inputs)
            else:
                response = pipeline.compile_generation(audio, audio.name, render=True)
            write_json(track_dir / 'response.json', response.model_dump(mode='json'))
            asset = response.model_asset_v3
            analysis = response.analysis
            if asset is None or analysis is None:
                raise RuntimeError('Pipeline returned without the v3 asset or analysis: '
                                   + str(getattr(response, 'stage_errors', {})))
            geometry_dir = Path(blender_export_v3.RENDER_DIRECTORY) / analysis.model_id
            manifest_path = (Path(blender_export_v3.WEB_ASSET_DIRECTORY)
                             / f'{analysis.model_id}.manifest.json')
            blend_path = Path(blender_export_v3.BLEND_DIRECTORY) / f'{analysis.model_id}.blend'
            evidence_paths = [
                *v3_evidence_paths(analysis.model_id, response.drawing_index),
                track_dir / 'response.json',
            ]
            if args.review:
                command = [str(blender_export.find_blender_executable()), '--background',
                    '--factory-startup', '--python-exit-code', '1', '--python',
                    str(CODE_ROOT / 'blender/render_model_review.py'), '--',
                    '--model', str(geometry_dir / 'building_model_v3.json'),
                    '--blend', str(blend_path),
                    '--manifest', str(manifest_path),
                    '--run-id', response.run_id, '--run-contract', str(track_dir / 'response.json'),
                    '--output', str(track_dir / 'review'), '--max-portals', '4']
                checked = subprocess.run(command, cwd=CODE_ROOT, capture_output=True, text=True,
                                         timeout=300, check=False)
                (track_dir / 'review-render.log').write_text(checked.stdout+checked.stderr,encoding='utf-8')
                if checked.returncode:
                    raise RuntimeError('Diagnostic rendering failed; see review-render.log')
                evidence_paths.extend([track_dir / 'review/views_manifest.json',
                                       *sorted((track_dir / 'review').glob('*.png'))])
            if args.rhino:
                from rhino.export_file import export_file
                export_file(geometry_dir / 'building_model_v3.json', track_dir / 'rhino',
                            run_id=response.run_id)
                evidence_paths.extend([track_dir/'rhino/model.3dm', track_dir/'rhino/candidate_manifest.json'])
            result.update(status='compiled', run_id=response.run_id, model_id=analysis.model_id,
                          typology=analysis.typology,
                          massing=analysis.selection.massing_id if analysis.selection else None,
                          structural_system=analysis.structural_system_id,
                          facade_grammar=analysis.facade_grammar_id,
                          duration_seconds=response.audio_features.provenance.duration_seconds,
                          elements=analysis.element_count,
                          evidence=evidence_records(
                              evidence_paths, run_id=response.run_id,
                              model_id=analysis.model_id))
        except Exception as error:
            result.update(status='failed', error=f'{type(error).__name__}: {error}')
            track_dir.mkdir(parents=True, exist_ok=True)
            (track_dir / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        result['elapsed_seconds'] = round(time.perf_counter() - start, 2)
        result['source_unchanged'] = hashes == source_hashes()
        if snapshot:
            verify(ROOT)
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
