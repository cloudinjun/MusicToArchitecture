"""The recording travels with the run, and the route that serves it stays in its lane."""

from fastapi.testclient import TestClient

from backend.app import run_store
from backend.app.main import app
from backend.app.run_store import audio_path, store_audio


def test_the_recording_is_keyed_by_the_run_and_refuses_foreign_ids(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_store, 'RUN_DIRECTORY', tmp_path)
    assert store_audio('run-b7ad95fa45a6', b'ID3demo') == tmp_path / 'run-b7ad95fa45a6.mp3'
    assert (tmp_path / 'run-b7ad95fa45a6.mp3').read_bytes() == b'ID3demo'
    for bad in ('../../etc/passwd', 'run-../../x', 'nope'):
        assert audio_path(bad) is None
        assert store_audio(bad, b'x') is None
    assert not (tmp_path / 'passwd').exists()


def test_the_audio_route_serves_a_stored_recording_and_nothing_else(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_store, 'RUN_DIRECTORY', tmp_path)
    store_audio('run-b7ad95fa45a6', b'ID3demo')
    client = TestClient(app)
    served = client.get('/api/runs/run-b7ad95fa45a6/audio')
    assert served.status_code == 200
    assert served.headers['content-type'].startswith('audio/mpeg')
    assert served.content == b'ID3demo'
    assert client.get('/api/runs/run-000000000000/audio').status_code == 404
    assert client.get('/api/runs/..%2F..%2Fx/audio').status_code in (400, 404)
