from fastapi.testclient import TestClient

from app.main import app


def test_system_backup_api_and_deferred_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))

    with TestClient(app) as client:
        system = client.get("/api/v1/system")
        assert system.status_code == 200
        assert system.json()["schema_version"] == "0005"
        assert system.json()["info"]["database_exists"] is True

        settings = client.patch(
            "/api/v1/system/backup-settings",
            json={
                "auto_backup_enabled": False,
                "interval_hours": 12,
                "retention_count": 5,
            },
        )
        assert settings.status_code == 200
        assert settings.json()["settings"]["auto_backup_enabled"] is False

        created = client.post("/api/v1/system/backups")
        assert created.status_code == 201
        filename = created.json()["item"]["filename"]

        verified = client.post(f"/api/v1/system/backups/{filename}/verify")
        assert verified.status_code == 200
        assert verified.json()["result"]["valid"] is True
        assert verified.json()["result"]["integrity_check"] == "ok"

        downloaded = client.get(f"/api/v1/system/backups/{filename}/download")
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"SQLite format 3")

        rejected = client.post(
            f"/api/v1/system/backups/{filename}/restore",
            json={"confirm": False},
        )
        assert rejected.status_code == 400

        queued = client.post(
            f"/api/v1/system/backups/{filename}/restore",
            json={"confirm": True},
        )
        assert queued.status_code == 202
        assert queued.json()["restore"]["restart_required"] is True

        pending = client.get("/api/v1/system")
        assert pending.json()["info"]["pending_restore"]["filename"] == filename


def test_backup_api_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))

    with TestClient(app) as client:
        response = client.post("/api/v1/system/backups/..%2Fsecret.db/verify")
        assert response.status_code in {400, 404, 422}
