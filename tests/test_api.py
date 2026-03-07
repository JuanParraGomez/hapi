from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_invalid_action_payload():
    with TestClient(app) as client:
        res = client.post("/services/x/actions", json={"action": "invalid"})
    assert res.status_code == 422
