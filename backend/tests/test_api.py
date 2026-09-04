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

