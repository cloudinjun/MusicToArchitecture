"""Export one saved study model without recompiling or promoting its authority.

python -m backend.scripts.package_candidate_study --study STUDY --output NEW_DIR
Add --blender only when the existing background Blender adapter is authorised.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from time import perf_counter

from backend.app.models_v3 import BuildingModelV3
from backend.app.version import compiler_source_fingerprint


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def read_study(study: Path):
    source = study / 'building_model_v3.json'
    evidence_path = study / 'building_result.json'
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    model = BuildingModelV3.model_validate_json(source.read_text(encoding='utf-8'))
    if (evidence['status'] != 'building_compiled_pending_review' or
            not evidence['source_unchanged'] or evidence['model_id'] != model.model_id):
        raise ValueError('Study compilation evidence does not identify this model')
    fingerprint = compiler_source_fingerprint()
    if evidence['compiler_source_fingerprint'] != fingerprint:
        raise ValueError('Saved study uses different compiler/exporter source; recompile explicitly')
    if model.lattice.cutaway or model.program_volume_model is None:
        raise ValueError('A complete Program Volume model is required')
    sources = {source: digest(source), evidence_path: digest(evidence_path)}
    return model, fingerprint, sources


def export_drawings(model, output: Path, run_id: str):
    from backend.app.drawings import issue_drawings, write_drawing_set
    issued = issue_drawings(model)
    target = write_drawing_set(issued, model, directory=output / 'drawings')
    index = issued.manifest(model)
    return {
        'index': str((target / 'index.json').relative_to(output)),
        'sheet_count': len(index['sheets']),
        'paper': index['paper'],
        'accounted_for': index['accounted_for'],
        'details': [
            {'id': drawing.id,
             'readiness': drawing.detail_readiness.model_dump(mode='json')}
            for drawing in issued.details],
        'authority': 'model_projected_candidate_drawings',
        'visual_review': 'pending',
        'rhino_issued': False,
    }


def export_rhino(model, output: Path, run_id: str):
    from rhino.export_file import export_file
    report = export_file(output / 'source' / 'building_model_v3.json',
                         output / 'rhino', run_id=run_id)
    return {key: report[key] for key in (
        'status', 'authority', 'object_count', 'program_volume_reference_count',
        'native_types', 'verification')}


def export_blender(model, output: Path, run_id: str):
    from backend.app import blender_export_v3 as adapter
    names = ('WEB_ASSET_DIRECTORY', 'BLEND_DIRECTORY', 'RENDER_DIRECTORY')
    previous = {name: getattr(adapter, name) for name in names}
    try:
        for name, folder in zip(names, ('glb', 'blend', 'renders')):
            setattr(adapter, name, output / 'blender' / folder)
        asset = adapter.export_blender_web_model_v3(model, render=True)
        return {'authority': 'presentation_only', 'asset': asset.model_dump(mode='json'),
                'visual_review': 'pending'}
    finally:
        for name, value in previous.items():
            setattr(adapter, name, value)


EXPORTERS = {'drawings': export_drawings, 'rhino': export_rhino, 'blender': export_blender}


def package(study: Path, output: Path, *, blender: bool = False) -> dict:
    study, output = study.resolve(), output.resolve()
    model, fingerprint, sources = read_study(study)
    # This is a delivery identity, not an invented audio-pipeline run identity.
    source_sha = sources[study / 'building_model_v3.json']
    run_id = 'delivery-' + hashlib.sha256(
        f'{model.model_id}|{source_sha}|{fingerprint}'.encode()).hexdigest()[:12]
    output.mkdir(parents=True, exist_ok=False)
    (output / 'source').mkdir()
    for path in sources:
        shutil.copyfile(path, output / 'source' / path.name)
    write_json(output / 'source' / 'program_volumes.json',
               model.program_volume_model.model_dump(mode='json'))
    report = {
        'schema_version': 'mta.candidate_delivery/1.0',
        'status': 'exporting', 'run_id': run_id, 'identity_scope': 'saved_model_delivery',
        'model_id': model.model_id, 'study_directory': str(study),
        'source_model_sha256': source_sha, 'compiler_source_fingerprint': fingerprint,
        'packager_sha256': digest(Path(__file__)),
        'source_unchanged': True, 'authority': 'diagnostic_candidate',
        'source_findings': {
            'spatial': model.spatial.model_dump(mode='json'),
            'dependency_graph': model.dependency_graph.model_dump(mode='json'),
            'limitations': model.limitations,
        },
        'stages': {name: {'status': 'pending'} for name in ('drawings', 'rhino')},
        'rhino_acceptance': 'not_recorded', 'candidate_selection': 'not_performed',
        'professional_review_required': True,
    }
    report['stages']['blender'] = {'status': 'pending' if blender else 'not_requested'}
    manifest = output / 'delivery.json'

    def save():
        report['artifacts'] = [
            {'path': path.relative_to(output).as_posix(), 'sha256': digest(path),
             'bytes': path.stat().st_size}
            for path in sorted(output.rglob('*')) if path.is_file() and path != manifest]
        write_json(manifest, report)

    save()
    for name, exporter in EXPORTERS.items():
        if report['stages'][name]['status'] != 'pending':
            continue
        started = perf_counter()
        report['stages'][name] = {'status': 'running'}
        save()
        try:
            result = exporter(model, output, run_id)
            report['stages'][name] = {'status': 'exported', 'result': result}
        except Exception as error:
            # Independent delivery branches retain exact errors, not a single success flag.
            report['stages'][name] = {
                'status': 'failed', 'error_type': type(error).__name__, 'error': str(error)}
        report['stages'][name]['seconds'] = round(perf_counter() - started, 2)
        report['source_unchanged'] = (
            fingerprint == compiler_source_fingerprint() and
            all(digest(path) == value for path, value in sources.items()) and
            report['packager_sha256'] == digest(Path(__file__)))
        if not report['source_unchanged']:
            report['status'] = 'invalidated_source_changed'
            save()
            raise RuntimeError('Source changed during delivery; stop and retain invalidated artifacts')
        save()
        print(json.dumps({'stage': name, **report['stages'][name]}, ensure_ascii=False), flush=True)
    report['status'] = ('export_failed' if any(
        row['status'] == 'failed' for row in report['stages'].values())
        else 'exported_pending_review')
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--blender', action='store_true',
                        help='Run the existing headless Blender Python adapter; requires user authorisation')
    args = parser.parse_args()
    report = package(args.study, args.output, blender=args.blender)
    return 2 if report['status'] == 'export_failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
