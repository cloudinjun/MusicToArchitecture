from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app import blender_export, blender_export_v3, pipeline
from backend.app.blender_export import BlenderExportError
from backend.app.compiler import compile_building_model
from backend.app.integration import compile_facade_host_handoff
from backend.app.mapping_report import compile_mapping_report
from backend.app.models import ModelAssetV3
from backend.app.score import compile_architectural_score
from backend.tests.test_integration import features, model_asset as fixture_model_asset


def _v3_asset() -> ModelAssetV3:
    return ModelAssetV3(
        asset_url='/models/generated/fixture-v3.glb',
        manifest_url='/models/generated/fixture-v3.manifest.json',
        native_blend_path='blender/generated/fixture-v3.blend',
        model_json_path='artifacts/v3_runs/fixture-v3/building_model_v3.json',
        asset_sha256='5' * 64,
        manifest_sha256='6' * 64,
        element_count=1,
        merged_object_count=1,
        face_count=12,
        semantic_layers=['structure'],
    )


def _patch_generation(monkeypatch, *, v2_export, v3_export):
    source = features()
    score = compile_architectural_score(source)
    model = compile_building_model(source, score)
    mapping_report = compile_mapping_report(source, score, model)
    facade_handoff = compile_facade_host_handoff(score, model)
    v3_model = SimpleNamespace(
        model_id='fixture-v3',
        datum_set=SimpleNamespace(coverage=0.8, waiting_on=[]),
        model_dump_json=lambda: '{"model_id":"fixture-v3"}',
    )
    v3_calls = []

    monkeypatch.setattr(pipeline, 'extract_audio_features', lambda *_: source)
    monkeypatch.setattr(pipeline, 'compile_architectural_score', lambda *_: score)
    monkeypatch.setattr(pipeline, 'compile_building_model', lambda *_: model)
    monkeypatch.setattr(pipeline, 'compile_mapping_report', lambda *_: mapping_report)
    monkeypatch.setattr(pipeline, 'compile_facade_host_handoff', lambda *_: facade_handoff)
    monkeypatch.setattr(pipeline, 'export_blender_web_model', v2_export)

    def compile_v3(*args):
        v3_calls.append(args)
        return v3_model

    monkeypatch.setattr(pipeline, 'compile_building_model_v3', compile_v3)
    monkeypatch.setattr(pipeline, 'compile_translation_report', lambda *_: None)
    monkeypatch.setattr(pipeline, 'compile_bim_handoff_report', lambda *_: None)
    monkeypatch.setattr(pipeline, 'export_blender_web_model_v3', v3_export)
    def fail_drawings(*_args):
        raise ValueError('fixture')

    monkeypatch.setattr(pipeline, 'issue_drawings', fail_drawings)
    monkeypatch.setattr(pipeline, 'compile_analysis_bundle', lambda *args, **kwargs: None)
    return source, v3_calls


def test_v2_preview_failure_still_runs_v3_and_keeps_manifest_honest(monkeypatch) -> None:
    failure = BlenderExportError('Blender export failed: 550 objects exceed the 500 object limit')
    v3_asset = _v3_asset()

    def fail_v2(_model):
        raise failure

    def export_v3(_model, *, render=False):
        return v3_asset

    _source, v3_calls = _patch_generation(
        monkeypatch, v2_export=fail_v2, v3_export=export_v3)
    response = pipeline.compile_generation(Path('fixture.mp3'), 'fixture.mp3')

    assert v3_calls
    assert response.model_asset is None
    assert response.model_asset_v3 == v3_asset

    manifest = response.pipeline_manifest
    assert manifest.overall_status == 'preview_ready'
    assert manifest.accepted_state.status == 'blocked'
    stage = next(item for item in manifest.stages if item.id == 'blender_web_preview')
    assert stage.status == 'fail'
    assert stage.message == str(failure)

    presentation = {
        item.id: item for item in manifest.artifacts
        if item.id in {
            'blender-glb', 'blender-manifest',
            'blender-native-scene', 'blender-scene-state',
        }
    }
    assert len(presentation) == 4
    assert all(item.status == 'blocked' for item in presentation.values())
    assert all(item.sha256 is None and item.uri is None for item in presentation.values())


def test_all_preview_failures_block_manifest(monkeypatch) -> None:
    failure = BlenderExportError('Blender export failed: object budget exceeded')

    def fail_v2(_model):
        raise failure

    def fail_v3(_model, *, render=False):
        raise BlenderExportError('Blender v3 export failed: no output')

    _source, v3_calls = _patch_generation(
        monkeypatch, v2_export=fail_v2, v3_export=fail_v3)
    response = pipeline.compile_generation(Path('fixture.mp3'), 'fixture.mp3')

    assert v3_calls
    assert response.model_asset is None
    assert response.model_asset_v3 is None
    assert response.pipeline_manifest.overall_status == 'blocked'
    assert response.pipeline_manifest.accepted_state.status == 'blocked'


def test_v2_preview_success_remains_available_when_v3_fails(monkeypatch) -> None:
    v2_asset = fixture_model_asset()

    def export_v2(_model):
        return v2_asset

    def fail_v3(_model, *, render=False):
        raise BlenderExportError('Blender v3 export failed: optional fixture failure')

    _source, v3_calls = _patch_generation(
        monkeypatch, v2_export=export_v2, v3_export=fail_v3)
    response = pipeline.compile_generation(Path('fixture.mp3'), 'fixture.mp3')

    assert v3_calls
    assert response.model_asset == v2_asset
    assert response.pipeline_manifest.overall_status == 'preview_ready'
    stage = next(item for item in response.pipeline_manifest.stages
                 if item.id == 'blender_web_preview')
    assert stage.status == 'pass'
    presentation = {
        item.id: item for item in response.pipeline_manifest.artifacts
        if item.id.startswith('blender-')
    }
    assert len(presentation) == 4
    assert all(item.status == 'available' for item in presentation.values())
    assert all(item.sha256 and item.uri for item in presentation.values())


def test_source_change_during_generation_rejects_mixed_artifacts(monkeypatch) -> None:
    v2_asset = fixture_model_asset()
    v3_asset = _v3_asset()
    _patch_generation(
        monkeypatch,
        v2_export=lambda _model: v2_asset,
        v3_export=lambda _model, render=False: v3_asset,
    )
    fingerprints = iter(('source-before', 'source-after'))
    monkeypatch.setattr(pipeline, 'compiler_source_fingerprint', lambda: next(fingerprints))

    with pytest.raises(RuntimeError, match='source changed while this run'):
        pipeline.compile_generation(Path('fixture.mp3'), 'fixture.mp3')


def test_v2_wrapper_reports_command_flag_and_missing_output_tail(monkeypatch, tmp_path) -> None:
    blender_path = tmp_path / 'blender.exe'
    import_script = tmp_path / 'import_building_model.py'
    blender_path.write_text('', encoding='utf-8')
    import_script.write_text('', encoding='utf-8')
    monkeypatch.setattr(blender_export, 'find_blender_executable', lambda: blender_path)
    monkeypatch.setattr(blender_export, 'IMPORT_SCRIPT', import_script)
    monkeypatch.setattr(blender_export, 'WEB_ASSET_DIRECTORY', tmp_path / 'web')
    monkeypatch.setattr(blender_export, 'BLEND_DIRECTORY', tmp_path / 'blend')
    monkeypatch.setattr(blender_export, 'STATE_DIRECTORY', tmp_path / 'state')
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout='stdout tail', stderr='stderr tail')

    monkeypatch.setattr(blender_export.subprocess, 'run', fake_run)

    model = SimpleNamespace(
        model_id='fixture',
        model_dump=lambda mode='json': {'model_id': 'fixture'},
    )
    with pytest.raises(BlenderExportError) as raised:
        blender_export.export_blender_web_model(model)

    assert '--python-exit-code' in commands[0]
    assert commands[0][commands[0].index('--python-exit-code') + 1] == '1'
    assert 'stderr: stderr tail' in str(raised.value)
    assert 'stdout: stdout tail' in str(raised.value)


def test_v3_wrapper_reports_command_flag_and_missing_output_tail(monkeypatch, tmp_path) -> None:
    blender_path = tmp_path / 'blender.exe'
    import_script = tmp_path / 'import_building_model_v3.py'
    blender_path.write_text('', encoding='utf-8')
    import_script.write_text('', encoding='utf-8')
    monkeypatch.setattr(blender_export_v3, 'find_blender_executable', lambda: blender_path)
    monkeypatch.setattr(blender_export_v3, 'IMPORT_SCRIPT', import_script)
    monkeypatch.setattr(blender_export_v3, 'WEB_ASSET_DIRECTORY', tmp_path / 'web')
    monkeypatch.setattr(blender_export_v3, 'BLEND_DIRECTORY', tmp_path / 'blend')
    monkeypatch.setattr(blender_export_v3, 'RENDER_DIRECTORY', tmp_path / 'renders')
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout='stdout tail', stderr='stderr tail')

    monkeypatch.setattr(blender_export_v3.subprocess, 'run', fake_run)
    model = SimpleNamespace(
        model_id='fixture-v3',
        model_dump_json=lambda indent=None: '{}',
    )
    with pytest.raises(BlenderExportError) as raised:
        blender_export_v3.export_blender_web_model_v3(model)

    assert '--python-exit-code' in commands[0]
    assert commands[0][commands[0].index('--python-exit-code') + 1] == '1'
    assert 'stderr: stderr tail' in str(raised.value)
    assert 'stdout: stdout tail' in str(raised.value)
