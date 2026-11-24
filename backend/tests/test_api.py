from fastapi.testclient import TestClient

from app.main import app


def test_health_and_empty_dashboard_use_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))

    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        summary = client.get("/api/v1/dashboard/summary")
        repositories = client.get("/api/v1/repositories")

    assert health.status_code == 200
    assert health.json()["database"] == "connected"
    assert health.json()["schema_version"] == "0004"

    assert summary.status_code == 200
    assert summary.json()["repositories"] == 0
    assert summary.json()["successful_trending_snapshots"] == 0

    assert repositories.status_code == 200
    assert repositories.json()["items"] == []
    assert repositories.json()["pagination"]["total"] == 0
