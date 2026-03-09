from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from tests.conftest import seed_monorepo


def test_health():
    with TestClient(app) as client:
        res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_invalid_action_payload():
    with TestClient(app) as client:
        res = client.post("/services/x/actions", json={"action": "invalid"})
    assert res.status_code == 422


def test_create_project_endpoint(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "coolify-server"
    seed_monorepo(repo_root)
    monkeypatch.setenv("COOLIFY_SERVER_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "hapi.db"))
    monkeypatch.setenv("AUTO_REFRESH_INVENTORY_ON_STARTUP", "false")
    monkeypatch.setenv("RAG_SYNC_ENABLED", "false")
    get_settings.cache_clear()

    with TestClient(app) as client:
        res = client.post(
            "/projects/create",
            json={"name": "CRM Portal", "lifetime": "long_lived", "template": "nextjs-starter"},
        )
        registry = client.get("/registry")

    assert res.status_code == 200
    payload = res.json()
    assert payload["project"]["slug"] == "crm-portal"
    assert registry.status_code == 200
    assert registry.json()["count"] >= 1
    get_settings.cache_clear()


def test_public_registry_endpoints(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "coolify-server"
    seed_monorepo(repo_root)
    monkeypatch.setenv("COOLIFY_SERVER_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "hapi.db"))
    monkeypatch.setenv("AUTO_REFRESH_INVENTORY_ON_STARTUP", "false")
    monkeypatch.setenv("RAG_SYNC_ENABLED", "false")
    get_settings.cache_clear()

    with TestClient(app) as client:
        registered = client.post(
            "/public/apps/register",
            json={
                "slug": "sales-ui",
                "name": "Sales UI",
                "app_type": "nextjs",
                "project_slug": "sales-ui",
                "domain": "sales-ui.apps.uniflexa.cloud",
                "status": "draft",
            },
        )
        app_id = registered.json()["app_id"]
        deployment = client.post(
            f"/public/apps/{app_id}/deployment",
            json={"deployment_status": "ready_for_coolify", "provider": "coolify"},
        )
        sync = client.post(f"/public/apps/{app_id}/sync", json={"target": "rag", "status": "synced"})
        summary = client.get("/infra/public-summary")

    assert registered.status_code == 200
    assert deployment.status_code == 200
    assert sync.status_code == 200
    assert summary.status_code == 200
    assert summary.json()["total_apps"] == 1
    get_settings.cache_clear()
