from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.main import app


def _seed_recommendation_data():
    with get_connection() as connection:
        repositories = [
            (201, "octo/alpha", "octo", "alpha", "Long-term platform", "Python", 1000),
            (202, "octo/beta", "octo", "beta", "Consistent developer toolkit", "Python", 500),
            (203, "octo/gamma", "octo", "gamma", "Emerging AI utility", "TypeScript", 100),
        ]
        for github_id, full_name, owner, name, description, language, stars in repositories:
            connection.execute(
                """
                INSERT INTO repositories (
                    github_repo_id, full_name, owner, name, description, html_url,
                    language, stars_count, forks_count, open_issues_count, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 100, 5, '2026-11-22T12:00:00Z')
                """,
                (
                    github_id,
                    full_name,
                    owner,
                    name,
                    description,
                    f"https://github.com/{full_name}",
                    language,
                    stars,
                ),
            )
        repo_ids = {
            row["full_name"]: row["id"]
            for row in connection.execute("SELECT id, full_name FROM repositories")
        }

        cursor = connection.execute(
            """
            INSERT INTO stars_scans (
                trigger_type, started_at, finished_at, status, total_count, fetched_count,
                incomplete_results, coverage_description
            ) VALUES (
                'manual', '2026-11-22T11:00:00Z', '2026-11-22T12:00:00Z',
                'success', 2, 2, 0, 'Top 2 repositories'
            )
            """
        )
        successful_scan_id = int(cursor.lastrowid)
        for rank, full_name in enumerate(("octo/alpha", "octo/beta"), start=1):
            connection.execute(
                """
                INSERT INTO stars_scan_items (
                    scan_id, repository_id, rank, stars_count, forks_count, language
                ) VALUES (?, ?, ?, ?, 100, 'Python')
                """,
                (
                    successful_scan_id,
                    repo_ids[full_name],
                    rank,
                    1000 if full_name == "octo/alpha" else 500,
                ),
            )

        cursor = connection.execute(
            """
            INSERT INTO stars_scans (
                trigger_type, started_at, finished_at, status, total_count, fetched_count,
                incomplete_results, coverage_description, error_summary
            ) VALUES (
                'manual', '2026-11-23T11:00:00Z', '2026-11-23T12:00:00Z',
                'partial_success', 2, 1, 1, 'Partial scan', 'One shard failed'
            )
            """
        )
        latest_partial_scan_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO stars_scan_items (
                scan_id, repository_id, rank, stars_count, forks_count, language
            ) VALUES (?, ?, 1, 500, 100, 'Python')
            """,
            (latest_partial_scan_id, repo_ids["octo/beta"]),
        )

        snapshot_ids = {"daily": [], "weekly": [], "monthly": []}
        for period, count in (("daily", 10), ("weekly", 4), ("monthly", 3)):
            for index in range(count):
                collected_at = f"2026-11-{index + 1:02d}T08:00:00Z"
                cursor = connection.execute(
                    """
                    INSERT INTO trending_snapshots (
                        period_type, period_key, collected_at, status, source_url, item_count
                    ) VALUES (?, ?, ?, 'success', ?, 3)
                    """,
                    (
                        period,
                        f"{period}-{index + 1}",
                        collected_at,
                        f"https://github.com/trending?since={period}",
                    ),
                )
                snapshot_id = int(cursor.lastrowid)
                snapshot_ids[period].append(snapshot_id)

                if period == "daily":
                    included = []
                    if index < 6:
                        included.append("octo/alpha")
                    if index < 2:
                        included.append("octo/beta")
                    if index < 8:
                        included.append("octo/gamma")
                elif period == "weekly":
                    included = ["octo/beta"]
                    if index < 2:
                        included.append("octo/alpha")
                    if index == 0:
                        included.append("octo/gamma")
                else:
                    included = ["octo/beta"]
                    if index == 0:
                        included.append("octo/alpha")
                    if index < 2:
                        included.append("octo/gamma")

                for rank, full_name in enumerate(included, start=1):
                    connection.execute(
                        """
                        INSERT INTO trending_snapshot_items (
                            snapshot_id, repository_id, rank, stars_count, stars_delta, forks_count
                        ) VALUES (?, ?, ?, ?, 10, 100)
                        """,
                        (
                            snapshot_id,
                            repo_ids[full_name],
                            rank,
                            repositories[{"octo/alpha": 0, "octo/beta": 1, "octo/gamma": 2}[full_name]][6],
                        ),
                    )

        # A partial snapshot is deliberately newer; it must not enter the sample denominator.
        connection.execute(
            """
            INSERT INTO trending_snapshots (
                period_type, period_key, collected_at, status, source_url, item_count
            ) VALUES (
                'daily', 'daily-partial', '2026-11-24T08:00:00Z',
                'partial_success', 'https://github.com/trending?since=daily', 1
            )
            """
        )
        return {
            "repo_ids": repo_ids,
            "successful_scan_id": successful_scan_id,
            "latest_partial_scan_id": latest_partial_scan_id,
            "snapshot_ids": snapshot_ids,
        }


def test_recommendation_profiles_expose_prd_weight_presets(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/v1/recommendations/profiles")

    assert response.status_code == 200
    profiles = response.json()["items"]
    assert [item["name"] for item in profiles] == [
        "综合平衡（默认）",
        "趋势发现优先",
        "长期价值优先",
    ]
    assert profiles[0]["is_default"] is True
    assert profiles[0]["weights_percent"] == {
        "stars": 30,
        "daily": 15,
        "weekly": 30,
        "monthly": 25,
    }
    assert profiles[1]["weights_percent"] == {
        "stars": 20,
        "daily": 25,
        "weekly": 35,
        "monthly": 20,
    }
    assert profiles[2]["weights_percent"] == {
        "stars": 40,
        "daily": 10,
        "weekly": 25,
        "monthly": 25,
    }


def test_recommendation_run_scores_candidate_union_and_explains_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        seeded = _seed_recommendation_data()
        response = client.post("/api/v1/recommendations/runs", json={})
        latest = client.get("/api/v1/recommendations/runs/latest")

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["status"] == "success"
    assert payload["run"]["algorithm_version"] == "1.0.0"
    assert payload["run"]["candidate_count"] == 3
    assert payload["summary"]["scored_count"] == 3
    assert payload["summary"]["stars_incomplete"] is True
    assert payload["summary"]["latest_stars_scan"]["id"] == seeded["latest_partial_scan_id"]
    assert payload["summary"]["scoring_stars_scan"]["id"] == seeded["successful_scan_id"]
    assert payload["run"]["weights"] == {
        "stars": 0.3,
        "daily": 0.15,
        "weekly": 0.3,
        "monthly": 0.25,
    }

    by_name = {item["full_name"]: item for item in payload["items"]}
    alpha = by_name["octo/alpha"]
    beta = by_name["octo/beta"]
    gamma = by_name["octo/gamma"]
    assert alpha["stars_score"] == 100.0
    assert alpha["daily_score"] == 60.0
    assert alpha["weekly_score"] == 50.0
    assert alpha["monthly_score"] == 33.3
    assert alpha["total_score"] == 62.3
    assert beta["daily_score"] == 20.0
    assert beta["weekly_score"] == 100.0
    assert beta["monthly_score"] == 100.0
    assert beta["total_score"] == 78.0
    assert gamma["stars_score"] == 33.3
    assert gamma["daily_score"] == 80.0
    assert gamma["categories"] == ["emerging"]
    assert beta["categories"] == ["stable"]
    assert beta["rank"] == 1
    assert alpha["rank"] == 2
    assert gamma["rank"] == 3
    assert alpha["coverage"]["periods"]["daily"]["sample_count"] == 10
    assert alpha["coverage"]["periods"]["daily"]["minimum_samples"] == 10
    assert alpha["coverage"]["stars"]["latest_scan_status"] == "partial_success"
    assert alpha["coverage"]["stars"]["incomplete"] is True
    assert latest.status_code == 200
    assert latest.json()["run"]["id"] == payload["run"]["id"]


def test_recommendation_marks_insufficient_period_samples_as_na_and_renormalizes(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO repositories (
                    github_repo_id, full_name, owner, name, html_url, stars_count, last_synced_at
                ) VALUES (301, 'octo/only', 'octo', 'only', 'https://github.com/octo/only',
                          123, '2026-11-22T12:00:00Z')
                """
            )
            repository_id = int(cursor.lastrowid)
            cursor = connection.execute(
                """
                INSERT INTO trending_snapshots (
                    period_type, period_key, collected_at, status, source_url, item_count
                ) VALUES ('daily', 'one-day', '2026-11-22T08:00:00Z', 'success', 'test', 1)
                """
            )
            snapshot_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO trending_snapshot_items (
                    snapshot_id, repository_id, rank, stars_count
                ) VALUES (?, ?, 1, 123)
                """,
                (snapshot_id, repository_id),
            )
        response = client.post("/api/v1/recommendations/runs", json={})

    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["stars_score"] == 100.0
    assert item["daily_score"] is None
    assert item["weekly_score"] is None
    assert item["monthly_score"] is None
    assert item["total_score"] == 100.0
    assert item["coverage"]["effective_weight"] == 0.3
    assert item["coverage"]["available_dimensions"] == ["stars"]
    assert item["coverage"]["periods"]["daily"]["sample_count"] == 1
    assert item["coverage"]["periods"]["daily"]["available"] is False


def test_recommendation_profiles_are_reproducible_and_runs_are_immutable(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        _seed_recommendation_data()
        profiles = client.get("/api/v1/recommendations/profiles").json()["items"]
        balanced = client.post("/api/v1/recommendations/runs", json={"profile_id": profiles[0]["id"]})
        long_term = client.post("/api/v1/recommendations/runs", json={"profile_id": profiles[2]["id"]})
        history = client.get("/api/v1/recommendations/runs")
        old_run = client.get(f"/api/v1/recommendations/runs/{balanced.json()['run']['id']}")

    assert balanced.status_code == 201
    assert long_term.status_code == 201
    assert history.json()["pagination"]["total"] == 2
    assert old_run.json()["run"]["weights"]["stars"] == 0.3
    assert old_run.json()["run"]["weights"]["monthly"] == 0.25
    assert long_term.json()["run"]["weights"]["stars"] == 0.4
    assert long_term.json()["run"]["weights"]["monthly"] == 0.25
    assert len(old_run.json()["items"]) == 3


def test_recommendation_filters_and_pagination_are_applied_to_saved_scores(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        _seed_recommendation_data()
        created = client.post("/api/v1/recommendations/runs", json={}).json()
        run_id = created["run"]["id"]
        emerging = client.get(
            f"/api/v1/recommendations/runs/{run_id}",
            params={"category": "emerging"},
        )
        stable = client.get(
            f"/api/v1/recommendations/runs/{run_id}",
            params={"category": "stable"},
        )
        searched = client.get(
            f"/api/v1/recommendations/runs/{run_id}",
            params={"q": "gamma", "page_size": 1},
        )
        language_filtered = client.get(
            f"/api/v1/recommendations/runs/{run_id}",
            params={"language": "TypeScript"},
        )
        dimension_filtered = client.get(
            f"/api/v1/recommendations/runs/{run_id}",
            params={"dimension": "daily"},
        )

    assert [item["full_name"] for item in emerging.json()["items"]] == ["octo/gamma"]
    assert [item["full_name"] for item in stable.json()["items"]] == ["octo/beta"]
    assert [item["full_name"] for item in searched.json()["items"]] == ["octo/gamma"]
    assert searched.json()["pagination"]["total"] == 1
    assert [item["full_name"] for item in language_filtered.json()["items"]] == ["octo/gamma"]
    assert language_filtered.json()["filters"]["language"] == "TypeScript"
    assert [item["full_name"] for item in dimension_filtered.json()["items"]] == ["octo/gamma"]
    assert dimension_filtered.json()["filters"]["dimension"] == "daily"


def test_latest_recommendations_returns_empty_state_before_first_run(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/v1/recommendations/runs/latest")

    assert response.status_code == 200
    assert response.json()["run"] is None
    assert response.json()["items"] == []
