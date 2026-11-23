import asyncio
import re

from app.database.connection import get_connection, initialize_database
from app.services import stars_collector
from app.services.stars_collector import (
    StarsScanResult,
    collect_stars_repositories,
    create_stars_scan_job,
    persist_stars_scan,
    validate_scan_options,
)


def _repository(repo_id: int, stars: int) -> dict:
    return {
        "id": repo_id,
        "full_name": f"owner/project-{repo_id}",
        "name": f"project-{repo_id}",
        "owner": {"login": "owner"},
        "description": f"Project {repo_id}",
        "html_url": f"https://github.com/owner/project-{repo_id}",
        "language": "Python" if repo_id % 2 else "TypeScript",
        "stargazers_count": stars,
        "forks_count": repo_id % 100,
        "open_issues_count": repo_id % 20,
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2026-11-24T00:00:00Z",
        "pushed_at": "2026-11-23T00:00:00Z",
        "license": {"spdx_id": "MIT"},
        "topics": ["ai", "automation"],
    }


def test_validate_scan_options_bounds():
    assert validate_scan_options(5000, 100) == (5000, 100)

    try:
        validate_scan_options(50, 100)
    except ValueError as exc:
        assert "max_results" in str(exc)
    else:
        raise AssertionError("Expected invalid max_results to fail")


def test_create_stars_scan_job_persists_query_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    initialize_database()

    job = create_stars_scan_job(max_results=2500, min_stars=250, include_forks=True)
    scan_id = job["related_stars_scan_id"]

    with get_connection() as connection:
        scan = connection.execute(
            "SELECT status, query_plan FROM stars_scans WHERE id = ?",
            (scan_id,),
        ).fetchone()
        stored_job = connection.execute(
            "SELECT job_type, status FROM collection_jobs WHERE id = ?",
            (job["id"],),
        ).fetchone()

    assert scan["status"] == "queued"
    assert '"max_results": 2500' in scan["query_plan"]
    assert '"include_forks": true' in scan["query_plan"]
    assert stored_job["job_type"] == "stars_scan"
    assert stored_job["status"] == "queued"


def test_stars_collector_splits_queries_beyond_search_window(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GITSCOUT_GITHUB_SEARCH_INTERVAL_SECONDS", "0")
    initialize_database()
    job = create_stars_scan_job(max_results=5000, min_stars=100)
    scan_id = int(job["related_stars_scan_id"])

    high = [_repository(index + 1, 1000 - (index % 450)) for index in range(800)]
    low = [_repository(index + 801, 550 - (index % 451)) for index in range(700)]
    high.sort(key=lambda item: -item["stargazers_count"])
    low.sort(key=lambda item: -item["stargazers_count"])

    async def fake_fetch_page(client, query, page, state):
        state.request_count += 1
        if "stars:>=100" in query:
            data = high + low
            total = len(data)
        else:
            match = re.search(r"stars:(\d+)\.\.(\d+)", query)
            assert match, query
            lower, upper = int(match.group(1)), int(match.group(2))
            data = high if lower == 551 and upper == 1000 else low
            total = len(data)
        start = (page - 1) * 100
        return {
            "total_count": total,
            "incomplete_results": False,
            "items": data[start:start + 100],
        }

    monkeypatch.setattr(stars_collector, "_fetch_page", fake_fetch_page)

    result = asyncio.run(
        collect_stars_repositories(
            scan_id=scan_id,
            job_id=job["id"],
            max_results=5000,
            min_stars=100,
        )
    )

    assert len(result.repositories) == 1500
    assert result.repositories[0]["stars_count"] == 1000
    assert result.repositories[-1]["stars_count"] >= 100
    assert result.request_count == 16
    assert result.shard_count == 3
    assert result.failed_shards == []
    assert result.incomplete_results is False


def test_persist_stars_scan_creates_immutable_ranking_and_stats(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    initialize_database()
    job = create_stars_scan_job(max_results=1000, min_stars=100)
    scan_id = int(job["related_stars_scan_id"])
    items = [
        stars_collector._normalize_repository(_repository(1001, 5000)),
        stars_collector._normalize_repository(_repository(1002, 4200)),
    ]
    assert all(item is not None for item in items)
    result = StarsScanResult(
        repositories=items,
        request_count=3,
        retry_count=0,
        total_count=2,
        deduplicated_count=0,
        incomplete_results=False,
        failed_shards=[],
        shard_count=1,
        cap_reached=False,
        coverage_description="Top 2 public repositories with at least 100 stars.",
    )

    persisted = persist_stars_scan(job["id"], scan_id, result)

    assert persisted["status"] == "success"
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT i.rank, i.stars_count, r.github_repo_id, r.full_name
            FROM stars_scan_items i
            JOIN repositories r ON r.id = i.repository_id
            WHERE i.scan_id = ? ORDER BY i.rank
            """,
            (scan_id,),
        ).fetchall()
        stats_count = connection.execute(
            "SELECT COUNT(*) AS count FROM repository_stats WHERE source = 'stars_scan'"
        ).fetchone()["count"]
        scan = connection.execute(
            "SELECT status, fetched_count FROM stars_scans WHERE id = ?",
            (scan_id,),
        ).fetchone()

    assert [(row["rank"], row["stars_count"]) for row in rows] == [(1, 5000), (2, 4200)]
    assert rows[0]["github_repo_id"] == 1001
    assert rows[0]["full_name"] == "owner/project-1001"
    assert stats_count == 2
    assert scan["status"] == "success"
    assert scan["fetched_count"] == 2
