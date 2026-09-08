"""Lightweight contract tests for the isolated music audit runner.

The real compiler and Blender stay mocked: these tests cover CLI routing, physical
asset discovery, run/model binding and hashing without launching a native process.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app import blender_export_v3, drawings
from backend.app.asset_lineage import SOURCE_HASH_BASIS, canonical_model_sha256
from backend.scripts import run_visual_music_audit as audit


MODEL_ID = 'building-v3-auditfixture'
RUN_ID = 'run-auditfixture'


class _Response(SimpleNamespace):
    def model_dump(self, *, mode: str):
        assert mode == 'json'
        return {'run_id': self.run_id, 'analysis': {'model_id': self.analysis.model_id}}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fake_assets() -> dict:
    web = Path(blender_export_v3.WEB_ASSET_DIRECTORY)
    blend = Path(blender_export_v3.BLEND_DIRECTORY)
    render = Path(blender_export_v3.RENDER_DIRECTORY) / MODEL_ID
    drawing = Path(drawings.DRAWING_DIRECTORY) / MODEL_ID
    for directory in (web, blend, render, drawing):
        directory.mkdir(parents=True, exist_ok=True)
    glb_path = web / f'{MODEL_ID}.glb'
    blend_path = blend / f'{MODEL_ID}.blend'
    model_path = render / 'building_model_v3.json'
    render_path = render / 'hero.png'
    glb_path.write_bytes(b'glb')
    blend_path.write_bytes(b'blend')
    model = {'model_id': MODEL_ID}
    model_path.write_text(json.dumps(model), encoding='utf-8')
    render_path.write_bytes(b'png')
    (web / f'{MODEL_ID}.manifest.json').write_text(json.dumps({
        'model_id': MODEL_ID,
        'source_hash_basis': SOURCE_HASH_BASIS,
        'source_model_sha256': canonical_model_sha256(model),
        'native_blend_sha256': _sha256(blend_path),
        'glb_sha256': _sha256(glb_path),
        'renders': [render_path.name],
        'render_sha256': {render_path.name: _sha256(render_path)},
    }), encoding='utf-8')
    sheets = [{'id': 'A-000'}, {'id': 'A-101'}]
    drawing_index = {'model_id': MODEL_ID, 'sheets': sheets}
    (drawing / 'index.json').write_text(json.dumps(drawing_index), encoding='utf-8')
    for sheet in sheets:
        (drawing / f"{sheet['id']}.svg").write_text('<svg/>', encoding='utf-8')
    return drawing_index


@pytest.mark.parametrize('program_volume', [False, True])
def test_audit_routes_mode_and_hashes_complete_isolated_evidence(
    tmp_path, monkeypatch, program_volume,
):
    output = tmp_path / ('program-volume' if program_volume else 'legacy')
    audio = tmp_path / 'track.mp3'
    audio.write_bytes(b'licensed fixture audio')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'tracks': [{
        'id': 'track', 'local_path': str(audio), 'sha256': _sha256(audio),
    }]}), encoding='utf-8')

    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(audit, 'source_hashes', lambda: {'compiler.py': 'a' * 64})

    def configure(directory: Path) -> None:
        monkeypatch.setattr(blender_export_v3, 'WEB_ASSET_DIRECTORY', directory / 'models')
        monkeypatch.setattr(blender_export_v3, 'BLEND_DIRECTORY', directory / 'native')
        monkeypatch.setattr(blender_export_v3, 'RENDER_DIRECTORY', directory / 'geometry')
        monkeypatch.setattr(drawings, 'DRAWING_DIRECTORY', directory / 'drawings')

    monkeypatch.setattr(audit, 'configure_outputs', configure)
    calls = []

    def compile_generation(audio_path, filename, **kwargs):
        calls.append((audio_path, filename, kwargs))
        drawing_index = _write_fake_assets()
        analysis = SimpleNamespace(
            model_id=MODEL_ID,
            typology='library',
            selection=SimpleNamespace(massing_id='MAS-PROGRAM-VOLUME'),
            structural_system_id='STR-SYS-FRAME',
            facade_grammar_id='FCD-05-HIGH-TECH',
            element_count=42,
        )
        return _Response(
            run_id=RUN_ID,
            model_asset_v3=SimpleNamespace(),
            analysis=analysis,
            drawing_index=drawing_index,
            audio_features=SimpleNamespace(
                provenance=SimpleNamespace(duration_seconds=12.5)),
        )

    monkeypatch.setattr(audit.pipeline, 'compile_generation', compile_generation)
    argv = [
        '--manifest', str(manifest), '--output', str(output),
        '--workspace-root', str(tmp_path),
    ]
    if program_volume:
        argv.append('--program-volume')
    audit.main(argv)

    assert len(calls) == 1
    expected_kwargs = {'render': True}
    if program_volume:
        expected_kwargs['v3_mode'] = 'program_volume'
    assert calls[0][2] == expected_kwargs

    expected_mode = 'program_volume' if program_volume else 'legacy'
    identity = json.loads((output / 'source_identity.json').read_text(encoding='utf-8'))
    result = json.loads((output / 'tracks/track/result.json').read_text(encoding='utf-8'))
    assert identity['v3_mode'] == expected_mode
    assert result['v3_mode'] == expected_mode
    assert result['status'] == 'compiled'
    assert {Path(item['path']).name for item in result['evidence']} == {
        f'{MODEL_ID}.glb', f'{MODEL_ID}.manifest.json', f'{MODEL_ID}.blend',
        'building_model_v3.json', 'index.json', 'A-000.svg', 'A-101.svg', 'hero.png',
        'response.json',
    }
    assert all(item['run_id'] == RUN_ID and item['model_id'] == MODEL_ID
               for item in result['evidence'])
    assert all(len(item['sha256']) == 64 for item in result['evidence'])


def test_evidence_inventory_rejects_a_foreign_drawing_index(tmp_path, monkeypatch):
    monkeypatch.setattr(blender_export_v3, 'WEB_ASSET_DIRECTORY', tmp_path / 'models')
    monkeypatch.setattr(blender_export_v3, 'BLEND_DIRECTORY', tmp_path / 'native')
    monkeypatch.setattr(blender_export_v3, 'RENDER_DIRECTORY', tmp_path / 'geometry')
    monkeypatch.setattr(drawings, 'DRAWING_DIRECTORY', tmp_path / 'drawings')
    expected = _write_fake_assets()
    drawing_index = tmp_path / 'drawings' / MODEL_ID / 'index.json'
    drawing_index.write_text(
        json.dumps({'model_id': 'building-v3-foreign', 'sheets': [{'id': 'A-000'}]}),
        encoding='utf-8')

    with pytest.raises(RuntimeError, match='drawing index belongs to model'):
        audit.v3_evidence_paths(MODEL_ID, expected)


def test_package_native_keeps_blend_inside_deliverable(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(blender_export_v3, 'BLEND_DIRECTORY', tmp_path / 'before-v3')
    # The v2 exporter is configured by the same audit contract; its state is restored
    # automatically by monkeypatch after this test.
    from backend.app import blender_export
    monkeypatch.setattr(blender_export, 'BLEND_DIRECTORY', tmp_path / 'before-v2')

    output = tmp_path / 'deliverable'
    audit.configure_outputs(output, package_native=True)

    assert Path(blender_export_v3.BLEND_DIRECTORY) == output / 'native'
    assert Path(blender_export.BLEND_DIRECTORY) == output / 'native'
