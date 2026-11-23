"""Dashboard summary and aggregated trend analytics APIs."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query

from app.database.connection import get_connection

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
PERIODS = ("daily", "weekly", "monthly")


def _latest_snapshot(connection: Any, period_type: str, offset: int = 0) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT id, period_type, period_key, collected_at, status, source_url,
               item_count, error_summary
        FROM trending_snapshots
        WHERE period_type = ? AND status IN ('success', 'partial_success')
        ORDER BY collected_at DESC, id DESC
        LIMIT 1 OFFSET ?
        """,
        (period_type, offset),
    ).fetchone()
    return dict(row) if row else None


@router.get("/summary")
def dashboard_summary() -> dict[str, object]:
    with get_connection() as connection:
        repository_count = connection.execute(
            "SELECT COUNT(*) AS count FROM repositories"
        ).fetchone()["count"]
        trending_count = connection.execute(
            "SELECT COUNT(*) AS count FROM trending_snapshots WHERE status IN ('success', 'partial_success')"
        ).fetchone()["count"]
        interested_count = connection.execute(
            "SELECT COUNT(*) AS count FROM interested_projects"
        ).fetchone()["count"]
        research_count = connection.execute(
            "SELECT COUNT(*) AS count FROM research_projects"
        ).fetchone()["count"]
        latest_trending = connection.execute(
            "SELECT MAX(collected_at) AS value FROM trending_snapshots "
            "WHERE status IN ('success', 'partial_success')"
        ).fetchone()["value"]
        latest_stars = connection.execute(
            "SELECT MAX(finished_at) AS value FROM stars_scans "
            "WHERE status IN ('success', 'partial_success')"
        ).fetchone()["value"]

    return {
        "repositories": repository_count,
        "successful_trending_snapshots": trending_count,
        "interested_projects": interested_count,
        "research_projects": research_count,
        "latest_trending_at": latest_trending,
        "latest_stars_scan_at": latest_stars,
    }


@router.get("/analytics")
def dashboard_analytics(
    period_type: Literal["daily", "weekly", "monthly"] = "daily",
) -> dict[str, Any]:
    """Aggregate saved snapshots only; this endpoint never calls GitHub."""
    with get_connection() as connection:
        period_snapshots = {
            period: {
                "latest": _latest_snapshot(connection, period, 0),
                "previous": _latest_snapshot(connection, period, 1),
            }
            for period in PERIODS
        }

        selected = period_snapshots[period_type]
        latest = selected["latest"]
        previous = selected["previous"]

        repository_count = connection.execute(
            "SELECT COUNT(*) AS count FROM repositories"
        ).fetchone()["count"]
        interested_count = connection.execute(
            "SELECT COUNT(*) AS count FROM interested_projects"
        ).fetchone()["count"]
        research_count = connection.execute(
            "SELECT COUNT(*) AS count FROM research_projects"
        ).fetchone()["count"]
        snapshot_count = connection.execute(
            "SELECT COUNT(*) AS count FROM trending_snapshots WHERE status IN ('success', 'partial_success')"
        ).fetchone()["count"]

        new_count = 0
        if latest and previous:
            new_count = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM trending_snapshot_items current_item
                LEFT JOIN trending_snapshot_items previous_item
                  ON previous_item.snapshot_id = ?
                 AND previous_item.repository_id = current_item.repository_id
                WHERE current_item.snapshot_id = ? AND previous_item.id IS NULL
                """,
                (previous["id"], latest["id"]),
            ).fetchone()["count"]

        trend_series: list[dict[str, Any]] = []
        if latest:
            series_rows = connection.execute(
                """
                SELECT s.id, s.period_key, s.collected_at, s.item_count,
                       ROUND(AVG(i.stars_count)) AS average_stars,
                       COALESCE(SUM(i.stars_delta), 0) AS total_stars_delta
                FROM trending_snapshots s
                LEFT JOIN trending_snapshot_items i ON i.snapshot_id = s.id
                WHERE s.period_type = ? AND s.status IN ('success', 'partial_success')
                GROUP BY s.id
                ORDER BY s.collected_at DESC, s.id DESC
                LIMIT 12
                """,
                (period_type,),
            ).fetchall()
            trend_series = [dict(row) for row in reversed(series_rows)]

        language_distribution: list[dict[str, Any]] = []
        topic_distribution: list[dict[str, Any]] = []
        if latest:
            language_rows = connection.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(r.language), ''), '未标注') AS name,
                       COUNT(*) AS value
                FROM trending_snapshot_items i
                JOIN repositories r ON r.id = i.repository_id
                WHERE i.snapshot_id = ?
                GROUP BY COALESCE(NULLIF(TRIM(r.language), ''), '未标注')
                ORDER BY value DESC, name COLLATE NOCASE ASC
                LIMIT 8
                """,
                (latest["id"],),
            ).fetchall()
            language_distribution = [dict(row) for row in language_rows]

            topic_rows = connection.execute(
                """
                SELECT t.topic AS name, COUNT(DISTINCT i.repository_id) AS value
                FROM trending_snapshot_items i
                JOIN repository_topics t ON t.repository_id = i.repository_id
                WHERE i.snapshot_id = ?
                GROUP BY t.topic
                ORDER BY value DESC, name COLLATE NOCASE ASC
                LIMIT 10
                """,
                (latest["id"],),
            ).fetchall()
            topic_distribution = [dict(row) for row in topic_rows]

        cross_period: dict[int, dict[str, Any]] = {}
        for period in PERIODS:
            period_snapshot = period_snapshots[period]["latest"]
            if not period_snapshot:
                continue
            rows = connection.execute(
                """
                SELECT i.repository_id, i.rank, i.stars_count, r.full_name,
                       r.description, r.html_url, r.language
                FROM trending_snapshot_items i
                JOIN repositories r ON r.id = i.repository_id
                WHERE i.snapshot_id = ?
                ORDER BY i.rank ASC
                LIMIT 100
                """,
                (period_snapshot["id"],),
            ).fetchall()
            for row in rows:
                item = cross_period.setdefault(
                    int(row["repository_id"]),
                    {
                        "repository_id": int(row["repository_id"]),
                        "full_name": row["full_name"],
                        "description": row["description"],
                        "html_url": row["html_url"],
                        "language": row["language"],
                        "stars_count": int(row["stars_count"]),
                        "rank_daily": None,
                        "rank_weekly": None,
                        "rank_monthly": None,
                        "period_count": 0,
                        "rank_sum": 0,
                    },
                )
                rank_key = f"rank_{period}"
                item[rank_key] = int(row["rank"])
                item["period_count"] += 1
                item["rank_sum"] += int(row["rank"])
                item["stars_count"] = max(item["stars_count"], int(row["stars_count"]))

        cross_period_items = sorted(
            cross_period.values(),
            key=lambda item: (
                -item["period_count"],
                item["rank_sum"],
                -item["stars_count"],
                item["full_name"].casefold(),
            ),
        )[:20]
        for item in cross_period_items:
            item.pop("rank_sum", None)

        latest_stars_scan_row = connection.execute(
            """
            SELECT id, finished_at, status, fetched_count, total_count,
                   incomplete_results, coverage_description
            FROM stars_scans
            WHERE status IN ('success', 'partial_success')
            ORDER BY finished_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        latest_stars_scan = dict(latest_stars_scan_row) if latest_stars_scan_row else None
        latest_stars_top = None
        if latest_stars_scan:
            top_row = connection.execute(
                """
                SELECT r.full_name, i.stars_count
                FROM stars_scan_items i
                JOIN repositories r ON r.id = i.repository_id
                WHERE i.scan_id = ? AND i.rank = 1
                """,
                (latest_stars_scan["id"],),
            ).fetchone()
            latest_stars_top = dict(top_row) if top_row else None

    cross_period_count = sum(1 for item in cross_period.values() if item["period_count"] >= 2)
    return {
        "period_type": period_type,
        "summary": {
            "repositories": repository_count,
            "successful_trending_snapshots": snapshot_count,
            "latest_period_items": int(latest["item_count"]) if latest else 0,
            "new_items_vs_previous": int(new_count),
            "cross_period_hot_projects": cross_period_count,
            "interested_projects": interested_count,
            "research_projects": research_count,
        },
        "period_snapshots": period_snapshots,
        "trend_series": trend_series,
        "language_distribution": language_distribution,
        "topic_distribution": topic_distribution,
        "cross_period_items": cross_period_items,
        "latest_stars_scan": latest_stars_scan,
        "latest_stars_top": latest_stars_top,
    }
