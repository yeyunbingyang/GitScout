from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.main import app


def _seed_analytics_data():
    with get_connection() as connection:
        repositories = [
            (101, "octo/alpha", "octo", "alpha", "Python project", "Python"),
            (102, "octo/beta", "octo", "beta", "Developer toolkit", "Python"),
            (103, "octo/gamma", "octo", "gamma", "Web framework", "TypeScript"),
        ]
        for github_id, full_name, owner, name, description, language in repositories:
            connection.execute(
                """
                INSERT INTO repositories (
                    github_repo_id, full_name, owner, name, description, html_url,
                    language, stars_count, forks_count, open_issues_count, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1000, 100, 10, '2026-11-21T12:00:00Z')
                """,
                (
                    github_id,
                    full_name,
                    owner,
                    name,
                    description,
                    f"https://github.com/{full_name}",
                    language,
                ),
            )

        repo_ids = {
            row["full_name"]: row["id"]
            for row in connection.execute("SELECT id, full_name FROM repositories")
        }
        topics = {
            "octo/alpha": ["ai", "automation"],
            "octo/beta": ["ai", "devtools"],
            "octo/gamma": ["web", "typescript"],
        }
        for full_name, values in topics.items():
            connection.executemany(
                "INSERT INTO repository_topics (repository_id, topic) VALUES (?, ?)",
                [(repo_ids[full_name], value) for value in values],
            )

        snapshots = {}
        snapshot_specs = [
            ("daily", "2026-11-20", "2026-11-20T08:00:00Z", 2),
            ("daily", "2026-11-21", "2026-11-21T08:00:00Z", 2),
            ("weekly", "2026-W47", "2026-11-21T09:00:00Z", 2),
            ("monthly", "2026-11", "2026-11-21T10:00:00Z", 2),
        ]
        for period, period_key, collected_at, item_count in snapshot_specs:
            cursor = connection.execute(
                """
                INSERT INTO trending_snapshots (
                    period_type, period_key, collected_at, status, source_url, item_count
                ) VALUES (?, ?, ?, 'success', ?, ?)
                """,
                (
                    period,
                    period_key,
                    collected_at,
                    f"https://github.com/trending?since={period}",
                    item_count,
                ),
            )
            snapshots[(period, period_key)] = int(cursor.lastrowid)

        items = [
            (("daily", "2026-11-20"), "octo/alpha", 1, 900, 40),
            (("daily", "2026-11-20"), "octo/beta", 2, 800, 30),
            (("daily", "2026-11-21"), "octo/beta", 1, 1000, 80),
            (("daily", "2026-11-21"), "octo/gamma", 2, 700, 50),
            (("weekly", "2026-W47"), "octo/beta", 1, 1000, 80),
            (("weekly", "2026-W47"), "octo/gamma", 2, 700, 50),
            (("monthly", "2026-11"), "octo/alpha", 1, 900, 40),
            (("monthly", "2026-11"), "octo/beta", 2, 1000, 80),
        ]
        for (period, period_key), full_name, rank, stars, delta in items:
            connection.execute(
                """
                INSERT INTO trending_snapshot_items (
                    snapshot_id, repository_id, rank, stars_count, stars_delta, forks_count
                ) VALUES (?, ?, ?, ?, ?, 100)
                """,
                (
                    snapshots[(period, period_key)],
                    repo_ids[full_name],
                    rank,
                    stars,
                    delta,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO repository_stats (
                    repository_id, captured_at, source, stars_count, forks_count
                ) VALUES (?, ?, ?, ?, 100)
                """,
                (
                    repo_ids[full_name],
                    f"{period_key}-T08:00:00Z",
                    f"trending_{period}",
                    stars,
                ),
            )

        scan_ids = []
        for finished_at, stars in [
            ("2026-11-20T12:00:00Z", 1000),
            ("2026-11-21T12:00:00Z", 1100),
        ]:
            cursor = connection.execute(
                """
                INSERT INTO stars_scans (
                    trigger_type, started_at, finished_at, status, total_count, fetched_count,
                    coverage_description
                ) VALUES ('manual', ?, ?, 'success', 1, 1, 'Top repository fixture')
                """,
                (finished_at, finished_at),
            )
            scan_id = int(cursor.lastrowid)
            scan_ids.append(scan_id)
            connection.execute(
                """
                INSERT INTO stars_scan_items (
                    scan_id, repository_id, rank, stars_count, forks_count, language
                ) VALUES (?, ?, 1, ?, 100, 'Python')
                """,
                (scan_id, repo_ids["octo/beta"], stars),
            )
            connection.execute(
                """
                INSERT INTO repository_stats (
                    repository_id, captured_at, source, stars_count, forks_count
                ) VALUES (?, ?, 'stars_scan', ?, 100)
                """,
                (repo_ids["octo/beta"], finished_at, stars),
            )

        connection.execute(
            "INSERT INTO interested_projects (repository_id, source_page) VALUES (?, 'trending')",
            (repo_ids["octo/beta"],),
        )
        connection.execute(
            """
            INSERT INTO research_projects (repository_id, status, priority, research_goal)
            VALUES (?, 'in_progress', 'high', 'Understand the architecture')
            """,
            (repo_ids["octo/beta"],),
        )
        return {
            "repo_ids": repo_ids,
            "snapshots": snapshots,
            "scan_ids": scan_ids,
        }


def test_dashboard_analytics_uses_saved_snapshots_and_aggregates(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        seeded = _seed_analytics_data()
        response = client.get("/api/v1/dashboard/analytics", params={"period_type": "daily"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["repositories"] == 3
    assert payload["summary"]["latest_period_items"] == 2
    assert payload["summary"]["new_items_vs_previous"] == 1
    assert payload["summary"]["cross_period_hot_projects"] == 2
    assert payload["summary"]["interested_projects"] == 1
    assert payload["summary"]["research_projects"] == 1
    assert len(payload["trend_series"]) == 2
    assert {item["name"] for item in payload["language_distribution"]} == {"Python", "TypeScript"}
    assert payload["cross_period_items"][0]["full_name"] == "octo/beta"
    assert payload["latest_stars_scan"]["id"] == seeded["scan_ids"][-1]
    assert payload["latest_stars_top"]["full_name"] == "octo/beta"


def test_compare_trending_snapshots_reports_new_dropped_and_rank_movement(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        seeded = _seed_analytics_data()
        base_id = seeded["snapshots"][("daily", "2026-11-20")]
        target_id = seeded["snapshots"][("daily", "2026-11-21")]
        response = client.get(
            "/api/v1/trending/compare",
            params={
                "base_snapshot_id": base_id,
                "target_snapshot_id": target_id,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["new"] == 1
    assert payload["summary"]["dropped"] == 1
    assert payload["summary"]["up"] == 1
    assert payload["summary"]["down"] == 0
    assert payload["summary"]["unchanged"] == 0
    by_name = {item["full_name"]: item for item in payload["items"]}
    assert by_name["octo/gamma"]["change_type"] == "new"
    assert by_name["octo/alpha"]["change_type"] == "dropped"
    assert by_name["octo/beta"]["change_type"] == "up"
    assert by_name["octo/beta"]["rank_change"] == 1


def test_compare_rejects_different_periods_and_same_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        seeded = _seed_analytics_data()
        daily_id = seeded["snapshots"][("daily", "2026-11-20")]
        weekly_id = seeded["snapshots"][("weekly", "2026-W47")]
        same = client.get(
            "/api/v1/trending/compare",
            params={"base_snapshot_id": daily_id, "target_snapshot_id": daily_id},
        )
        mixed = client.get(
            "/api/v1/trending/compare",
            params={"base_snapshot_id": daily_id, "target_snapshot_id": weekly_id},
        )

    assert same.status_code == 422
    assert mixed.status_code == 422


def test_repository_detail_returns_stars_and_trending_history(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        seeded = _seed_analytics_data()
        repository_id = seeded["repo_ids"]["octo/beta"]
        response = client.get(f"/api/v1/repositories/{repository_id}")
        missing = client.get("/api/v1/repositories/99999")

    assert response.status_code == 200
    payload = response.json()
    assert payload["repository"]["full_name"] == "octo/beta"
    assert payload["repository"]["topics"] == ["ai", "devtools"]
    assert payload["repository"]["interested"]["source_page"] == "trending"
    assert payload["repository"]["research"]["status"] == "in_progress"
    assert payload["summary"]["best_rank_by_period"] == {
        "daily": 1,
        "weekly": 1,
        "monthly": 2,
    }
    assert payload["summary"]["current_appearance_streak_by_period"] == {
        "daily": 2,
        "weekly": 1,
        "monthly": 1,
    }
    assert payload["summary"]["observed_stars_growth"] == 100
    assert len(payload["stars_history"]) == 2
    assert len(payload["trending_history"]) == 4
    assert missing.status_code == 404
