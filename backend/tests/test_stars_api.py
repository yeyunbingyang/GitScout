from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.main import app
from app.services import stars_collector
from app.services.stars_collector import StarsScanResult


def _repo():
    return {
        "github_repo_id": 88001,
        "full_name": "octo/stars-sample",
        "owner": "octo",
        "name": "stars-sample",
        "description": "Stars API integration test",
        "html_url": "https://github.com/octo/stars-sample",
        "language": "Python",
        "stars_count": 12345,
        "forks_count": 321,
        "open_issues_count": 12,
        "github_created_at": "2020-01-01T00:00:00Z",
        "github_updated_at": "2026-11-24T00:00:00Z",
        "pushed_at": "2026-11-23T00:00:00Z",
        "license_spdx_id": "MIT",
        "topics": ["ai"],
    }


def test_stars_collection_and_leaderboard_apis(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))

    async def fake_collect(scan_id, job_id, max_results, min_stars, include_forks=False):
        return StarsScanResult(
            repositories=[_repo()],
            request_count=2,
            retry_count=0,
            total_count=1,
            deduplicated_count=0,
            incomplete_results=False,
            failed_shards=[],
            shard_count=1,
            cap_reached=False,
            coverage_description="Top 1 public repository with at least 100 stars.",
        )

    monkeypatch.setattr(stars_collector, "collect_stars_repositories", fake_collect)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/stars/collect",
            json={"max_results": 1000, "min_stars": 100, "include_forks": False},
        )
        assert response.status_code == 202
        scan_id = response.json()["scan_id"]
        job_id = response.json()["job"]["id"]

        detail = client.get(f"/api/v1/stars/scans/{scan_id}")
        assert detail.status_code == 200
        assert detail.json()["status"] == "success"

        leaderboard = client.get("/api/v1/stars/leaderboard")
        assert leaderboard.status_code == 200
        assert leaderboard.json()["scan"]["id"] == scan_id
        assert leaderboard.json()["items"][0]["full_name"] == "octo/stars-sample"

        jobs = client.get("/api/v1/collections/jobs")
        assert jobs.status_code == 200
        assert any(item["id"] == job_id and item["job_type"] == "stars_scan" for item in jobs.json()["items"])

        job_detail = client.get(f"/api/v1/collections/jobs/{job_id}")
        assert job_detail.status_code == 200
        assert job_detail.json()["stars_scan"]["id"] == scan_id


def test_stars_schedule_api_is_not_shadowed_by_dynamic_trending_route(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/collections/schedules/stars",
            json={
                "enabled": True,
                "time": "07:30",
                "timezone": "Asia/Tokyo",
                "max_results": 3000,
                "min_stars": 250,
                "include_forks": True,
            },
        )
    assert response.status_code == 200
    assert response.json()["schedule"]["job_type"] == "stars_daily"
    assert response.json()["schedule"]["settings"]["max_results"] == 3000
