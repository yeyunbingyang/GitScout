from fastapi.testclient import TestClient

from app.main import app
from app.services import trending_collector

HTML = """
<article class="Box-row">
  <h2><a href="/sample/project">sample / project</a></h2>
  <p>A project collected by the integration test.</p>
  <span itemprop="programmingLanguage">Python</span>
  <a href="/sample/project/stargazers">987</a>
  <a href="/sample/project/forks">65</a>
  <span>123 stars today</span>
</article>
"""


def test_trending_collection_history_and_job_apis(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))

    async def fake_fetch(period_type):
        return HTML, f"https://github.com/trending?since={period_type}", 1

    monkeypatch.setattr(trending_collector, "fetch_trending_html", fake_fetch)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/trending/collect",
            json={"period_type": "daily"},
        )
        assert response.status_code == 202
        job = response.json()["job"]
        assert job["status"] in {"queued", "success"}

        job_response = client.get(f"/api/v1/collections/jobs/{job['id']}")
        assert job_response.status_code == 200
        assert job_response.json()["status"] == "success"

        snapshots = client.get(
            "/api/v1/trending/snapshots",
            params={"period_type": "daily"},
        )
        assert snapshots.status_code == 200
        assert snapshots.json()["pagination"]["total"] == 1

        leaderboard = client.get(
            "/api/v1/trending",
            params={"period_type": "daily"},
        )
        assert leaderboard.status_code == 200
        assert leaderboard.json()["snapshot"]["status"] == "success"
        assert leaderboard.json()["items"][0]["full_name"] == "sample/project"
        assert leaderboard.json()["items"][0]["stars_delta"] == 123

        filtered = client.get(
            "/api/v1/trending",
            params={"period_type": "daily", "language": "Python", "q": "sample"},
        )
        assert filtered.status_code == 200
        assert filtered.json()["pagination"]["total"] == 1


def test_trending_collection_rejects_unknown_period(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/trending/collect",
            json={"period_type": "yearly"},
        )
    assert response.status_code == 422



def test_schedule_configuration_api(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))

    with TestClient(app) as client:
        current = client.get("/api/v1/collections/schedules")
        assert current.status_code == 200
        assert len(current.json()["items"]) == 3

        saved = client.put(
            "/api/v1/collections/schedules/daily",
            json={
                "enabled": True,
                "time": "08:30",
                "timezone": "Asia/Tokyo",
                "weekday": 0,
                "day_of_month": 1,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["schedule"]["enabled"] is True
        assert saved.json()["schedule"]["settings"]["time"] == "08:30"

        invalid = client.put(
            "/api/v1/collections/schedules/daily",
            json={"enabled": True, "time": "25:99", "timezone": "UTC"},
        )
        assert invalid.status_code == 422
