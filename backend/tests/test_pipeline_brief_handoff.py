from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from backend.app import pipeline, main
from backend.app.blender_export import BlenderExportError
from backend.app.project_brief import ProjectBrief
from backend.tests.test_legacy_program_layout import _brief
from backend.tests.test_preview_failure_isolation import _patch_generation


def bounded_brief():
    raw = _brief().model_dump(mode='json')
    raw['site'] = {'polygon': [(0,0),(28,0),(28,16),(0,16)]}
    return ProjectBrief.model_validate(raw)


def test_448_brief_reaches_program_volume_compiler_and_response(monkeypatch):
    _patch_generation(monkeypatch, v2_export=lambda *_: None, v3_export=lambda *_args, **_kwargs: None)
    brief = bounded_brief()
    def compile_pv(score, *, project_brief, legacy_controls, cutaway):
        assert project_brief is brief
        assert project_brief.site.area_m2 == 448
        return SimpleNamespace(model_id='bounded', model_dump_json=lambda: '{}',
                               datum_set=SimpleNamespace(coverage=0,waiting_on=[])), None
    monkeypatch.setattr(pipeline, 'compile_program_volume_candidate', compile_pv)
    response = pipeline.compile_generation(Path('test.mp3'),'test.mp3',project_brief=brief)
    assert response.project_brief['site']['polygon'] == brief.model_dump(mode='json')['site']['polygon']


def test_legacy_cannot_ignore_brief():
    with pytest.raises(ValueError,match='silently ignore'):
        pipeline.compile_generation(Path('missing.mp3'),'missing.mp3',project_brief=bounded_brief(),v3_mode='legacy')


def test_v3_dependency_failure_is_preserved(monkeypatch):
    def fail(*args,**kwargs):
        raise BlenderExportError("ModuleNotFoundError: No module named 'shapely'")
    _patch_generation(monkeypatch,v2_export=lambda *_: None,v3_export=fail)
    response = pipeline.compile_generation(Path('test.mp3'),'test.mp3')
    assert 'shapely' in response.stage_errors['v3_export']
    assert response.stage_errors['drawings'] == 'fixture'


def test_http_forwards_validated_448_brief(monkeypatch):
    captured = []
    def stop(*args,**kwargs):
        captured.append(kwargs['project_brief'])
        raise ValueError('handoff reached')
    monkeypatch.setattr(main,'compile_generation',stop)
    response = TestClient(main.app).post('/api/generate',
        files={'file':('test.mp3',b'ID3','audio/mpeg')},
        data={'project_brief':bounded_brief().model_dump_json()})
    assert response.status_code == 422
    assert response.json()['detail'] == 'handoff reached'
    assert captured[0].site.area_m2 == 448
