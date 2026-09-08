from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_non_mp3() -> None:
    response = client.post("/api/generate", files={"file": ("sample.wav", b"data", "audio/wav")})
    assert response.status_code == 415



def test_a_pipeline_refusal_reaches_the_client_with_its_reason(monkeypatch) -> None:
    from backend.app import main

    def refuse(*_args, **_kwargs):
        raise RuntimeError('compiler source changed while this run was being generated; '
                           'discard the mixed-source artifacts and run again')

    monkeypatch.setattr(main, 'compile_generation', refuse)
    response = client.post('/api/generate', files={'file': ('a.mp3', b'ID3', 'audio/mpeg')})
    assert response.status_code == 409
    assert 'run again' in response.json()['detail']
