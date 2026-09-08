from __future__ import annotations

import json

import pytest

from backend.scripts import publish_model_version as versions


def test_publication_has_one_writer(monkeypatch, tmp_path):
    monkeypatch.setattr(versions, 'VERSIONS', tmp_path)
    with versions._publication_lock():
        with pytest.raises(ValueError, match='Another publication'):
            with versions._publication_lock():
                pytest.fail('A second writer entered')
        assert (tmp_path / '.publication.lock').is_file()
    assert not (tmp_path / '.publication.lock').exists()


@pytest.fixture
def candidate(monkeypatch, tmp_path):
    monkeypatch.setattr(versions, 'ROOT', tmp_path)
    monkeypatch.setattr(versions, 'VERSIONS', tmp_path / 'versions')
    monkeypatch.setattr(versions, 'compiler_source_fingerprint', lambda: 'source-fingerprint')
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content), encoding='utf-8')
        return path
    model = write(tmp_path / 'source.json', {'model_id': 'model-a'})
    geometry = tmp_path / 'model.3dm'
    geometry.write_bytes(b'candidate file')
    payload = {'run_id': 'run-a', 'analysis': {'model_id': 'model-a'},
        'model_asset_v3': {'model_json_path': 'source.json',
            'source_model_sha256': 'model-content', 'native_blend_sha256': 'blend-content'}}
    response = write(tmp_path / 'response.json', payload)
    rhino = write(tmp_path / 'rhino.json', {
        'status': 'geometry_candidate', 'authority': 'candidate', 'representation': 'complete',
        'run_id': 'run-a', 'model_id': 'model-a', 'source_sha256': versions._sha256(model),
        'geometry_sha256': versions._sha256(geometry),
        'verification': {key: 'passed' for key in ('file_geometry', 'saved_file_reopened',
            'source_identity', 'geometry_serialization')},
    })
    binding = {'run_id': 'run-a', 'model_id': 'model-a', 'source_model_sha256': 'model-content',
        'native_blend_sha256': 'blend-content', 'run_contract_sha256': versions._sha256(response)}
    review_dir = tmp_path / 'review'
    image = write(review_dir / 'view.png', 'test image bytes')
    write(review_dir / 'views_manifest.json', {'source': binding,
        'status': 'rendered_pending_visual_review', 'views': [
            {'image': 'view.png', 'image_sha256': versions._sha256(image), 'source': binding}]})
    def collect(payload, path, stage, *args):
        blend = tmp_path / 'scene.blend'
        blend.write_bytes(b'blend-content')
        return {'version_id': 'time-v3.6.0-model-oldhash', 'run_id': 'run-a', 'v3_model_id': 'model-a',
            'compiler_source_sha256': 'source-fingerprint', 'authority': {'rhino': {}},
            'assets': [versions._asset(blend, stage, 'blender/scene_v3.blend', 'scene', 'presentation_only')]}
    monkeypatch.setattr(versions, '_collect_bundle', collect)
    latest = write(tmp_path / 'versions/latest.json', {'version_id': 'accepted-old'})
    return response, geometry, rhino, review_dir, latest


def test_candidate_keeps_pair_and_never_promotes_latest(candidate):
    response, geometry, rhino, review, latest = candidate
    before = latest.read_bytes()
    pointer = versions.archive_candidate(response, rhino_3dm=geometry,
        rhino_manifest=rhino, review_directory=review)
    folder = versions.VERSIONS / pointer['manifest']
    manifest = json.loads(folder.read_text())
    assert manifest['status'] == 'archived_candidate'
    assert manifest['authority']['rhino']['status'] == 'candidate'
    assert (folder.parent / 'rhino/model.3dm').read_bytes() == geometry.read_bytes()
    assert (folder.parent / 'blender/scene_v3.blend').is_file()
    assert (folder.parent / 'review/view.png').is_file()
    assert latest.read_bytes() == before
    # A duplicate run reuses the immutable package, with no mixed staging files.
    assert versions.archive_candidate(response, rhino_3dm=geometry,
        rhino_manifest=rhino, review_directory=review) == pointer


@pytest.mark.parametrize('changed', ['rhino', 'render'])
def test_stale_candidate_file_is_rejected(candidate, changed):
    response, geometry, rhino, review, latest = candidate
    (geometry if changed == 'rhino' else review / 'view.png').write_bytes(b'stale')
    with pytest.raises(ValueError):
        versions.archive_candidate(response, rhino_3dm=geometry,
            rhino_manifest=rhino, review_directory=review)
    assert json.loads(latest.read_text())['version_id'] == 'accepted-old'
