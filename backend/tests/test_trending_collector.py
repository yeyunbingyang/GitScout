from app.database.connection import get_connection, initialize_database
import pytest

from app.services.trending_collector import (
    ActiveTrendingJobError,
    create_trending_job,
    get_collection_job,
    parse_trending_html,
    persist_trending_snapshot,
)


HTML = """
<html><body>
<article class="Box-row">
  <h2><a href="/octo/alpha">octo / alpha</a></h2>
  <p>A fast alpha project.</p>
  <span itemprop="programmingLanguage">Python</span>
  <a href="/octo/alpha/stargazers">12,345</a>
  <a href="/octo/alpha/forks">678</a>
  <a class="topic-tag" href="/topics/ai">ai</a>
  <a class="topic-tag" href="/topics/agents">agents</a>
  <span>1,234 stars today</span>
</article>
<article class="Box-row">
  <h2><a href="/octo/beta">octo / beta</a></h2>
  <p>Another project.</p>
  <span itemprop="programmingLanguage">TypeScript</span>
  <a href="/octo/beta/stargazers">2.4k</a>
  <a href="/octo/beta/forks">91</a>
  <span>245 stars today</span>
</article>
</body></html>
"""


def test_parse_daily_trending_cards():
    parsed = parse_trending_html(HTML, "daily")

    assert parsed.card_count == 2
    assert parsed.duplicate_count == 0
    assert parsed.skipped_count == 0
    assert len(parsed.items) == 2

    first = parsed.items[0]
    assert first.rank == 1
    assert first.full_name == "octo/alpha"
    assert first.language == "Python"
    assert first.stars_count == 12345
    assert first.stars_delta == 1234
    assert first.forks_count == 678
    assert first.topics == ("ai", "agents")


def test_parse_weekly_and_monthly_delta_labels():
    weekly_html = HTML.replace("stars today", "stars this week")
    monthly_html = HTML.replace("stars today", "stars this month")

    assert parse_trending_html(weekly_html, "weekly").items[0].stars_delta == 1234
    assert parse_trending_html(monthly_html, "monthly").items[0].stars_delta == 1234


def test_parser_deduplicates_repositories_and_skips_invalid_cards():
    duplicate = HTML.replace(
        "</body>",
        """
        <article class="Box-row">
          <h2><a href="/octo/alpha">duplicate alpha</a></h2>
        </article>
        <article class="Box-row"><p>Not a repository card</p></article>
        </body>
        """,
    )
    parsed = parse_trending_html(duplicate, "daily")

    assert len(parsed.items) == 2
    assert parsed.duplicate_count == 1
    assert parsed.skipped_count == 1


def test_persist_creates_immutable_snapshot_and_upserts_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    initialize_database()

    first_job = create_trending_job("daily")
    first_parsed = parse_trending_html(HTML, "daily")
    first_result = persist_trending_snapshot(
        first_job["id"],
        "daily",
        first_parsed,
        "https://github.com/trending?since=daily",
        "2026-11-24T00:00:00Z",
        1,
    )

    second_job = create_trending_job("daily")
    second_parsed = parse_trending_html(HTML.replace("12,345", "12,346"), "daily")
    second_result = persist_trending_snapshot(
        second_job["id"],
        "daily",
        second_parsed,
        "https://github.com/trending?since=daily",
        "2026-11-24T00:01:00Z",
        1,
    )

    assert first_result["status"] == "success"
    assert second_result["status"] == "success"
    assert first_result["related_snapshot_id"] != second_result["related_snapshot_id"]

    with get_connection() as connection:
        repositories = connection.execute(
            "SELECT COUNT(*) AS count FROM repositories"
        ).fetchone()["count"]
        snapshots = connection.execute(
            "SELECT COUNT(*) AS count FROM trending_snapshots WHERE status = 'success'"
        ).fetchone()["count"]
        snapshot_items = connection.execute(
            "SELECT COUNT(*) AS count FROM trending_snapshot_items"
        ).fetchone()["count"]
        latest_stars = connection.execute(
            "SELECT stars_count FROM repositories WHERE full_name = 'octo/alpha'"
        ).fetchone()["stars_count"]
        old_snapshot_stars = connection.execute(
            """
            SELECT stars_count FROM trending_snapshot_items
            WHERE snapshot_id = ? AND rank = 1
            """,
            (first_result["related_snapshot_id"],),
        ).fetchone()["stars_count"]

    assert repositories == 2
    assert snapshots == 2
    assert snapshot_items == 4
    assert latest_stars == 12346
    assert old_snapshot_stars == 12345


def test_collection_job_records_retry_lineage(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    initialize_database()

    original = create_trending_job("weekly")
    with get_connection() as connection:
        connection.execute(
            "UPDATE collection_jobs SET status = 'failed' WHERE id = ?",
            (original["id"],),
        )

    retry = create_trending_job(
        "weekly",
        retry_count=1,
        retry_of_job_id=original["id"],
    )

    assert retry["retry_of_job_id"] == original["id"]



def test_same_period_cannot_have_two_active_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    initialize_database()

    create_trending_job("monthly")
    with pytest.raises(ActiveTrendingJobError):
        create_trending_job("monthly")
