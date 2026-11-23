"""Compare two immutable Trending snapshots."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from app.database.connection import get_connection

router = APIRouter(prefix="/trending", tags=["trending-comparison"])

CHANGE_TYPES = ("all", "new", "dropped", "up", "down", "unchanged")


def _snapshot(connection: Any, snapshot_id: int) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT id, period_type, period_key, collected_at, status, source_url,
               item_count, error_summary
        FROM trending_snapshots
        WHERE id = ? AND status IN ('success', 'partial_success')
        """,
        (snapshot_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trending snapshot {snapshot_id} not found")
    return dict(row)


def _comparison_cte() -> str:
    return """
        WITH base_items AS (
            SELECT repository_id, rank, stars_count, stars_delta, forks_count
            FROM trending_snapshot_items WHERE snapshot_id = :base_id
        ),
        target_items AS (
            SELECT repository_id, rank, stars_count, stars_delta, forks_count
            FROM trending_snapshot_items WHERE snapshot_id = :target_id
        ),
        merged AS (
            SELECT
                b.repository_id,
                b.rank AS base_rank,
                t.rank AS target_rank,
                COALESCE(t.stars_count, b.stars_count) AS stars_count,
                COALESCE(t.stars_delta, 0) AS stars_delta,
                COALESCE(t.forks_count, b.forks_count) AS forks_count
            FROM base_items b
            LEFT JOIN target_items t ON t.repository_id = b.repository_id
            UNION ALL
            SELECT
                t.repository_id,
                NULL AS base_rank,
                t.rank AS target_rank,
                t.stars_count,
                t.stars_delta,
                t.forks_count
            FROM target_items t
            LEFT JOIN base_items b ON b.repository_id = t.repository_id
            WHERE b.repository_id IS NULL
        ),
        classified AS (
            SELECT
                m.repository_id,
                r.full_name,
                r.owner,
                r.name,
                r.description,
                r.html_url,
                r.language,
                m.base_rank,
                m.target_rank,
                m.stars_count,
                m.stars_delta,
                m.forks_count,
                CASE
                    WHEN m.base_rank IS NULL THEN 'new'
                    WHEN m.target_rank IS NULL THEN 'dropped'
                    WHEN m.target_rank < m.base_rank THEN 'up'
                    WHEN m.target_rank > m.base_rank THEN 'down'
                    ELSE 'unchanged'
                END AS change_type,
                CASE
                    WHEN m.base_rank IS NOT NULL AND m.target_rank IS NOT NULL
                    THEN m.base_rank - m.target_rank
                    ELSE NULL
                END AS rank_change
            FROM merged m
            JOIN repositories r ON r.id = m.repository_id
        )
    """


@router.get("/compare")
def compare_trending_snapshots(
    base_snapshot_id: int = Query(ge=1),
    target_snapshot_id: int = Query(ge=1),
    change_type: Literal["all", "new", "dropped", "up", "down", "unchanged"] = "all",
    q: str | None = Query(default=None, max_length=120),
    language: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    if base_snapshot_id == target_snapshot_id:
        raise HTTPException(status_code=422, detail="Choose two different snapshots to compare")

    with get_connection() as connection:
        base_snapshot = _snapshot(connection, base_snapshot_id)
        target_snapshot = _snapshot(connection, target_snapshot_id)
        if base_snapshot["period_type"] != target_snapshot["period_type"]:
            raise HTTPException(
                status_code=422,
                detail="Snapshots must belong to the same Trending period",
            )

        cte = _comparison_cte()
        parameters: dict[str, Any] = {
            "base_id": base_snapshot_id,
            "target_id": target_snapshot_id,
        }
        summary_rows = connection.execute(
            cte + " SELECT change_type, COUNT(*) AS count FROM classified GROUP BY change_type",
            parameters,
        ).fetchall()
        summary = {kind: 0 for kind in CHANGE_TYPES if kind != "all"}
        for row in summary_rows:
            summary[str(row["change_type"])] = int(row["count"])
        summary["total"] = sum(summary.values())

        conditions: list[str] = []
        if change_type != "all":
            conditions.append("change_type = :change_type")
            parameters["change_type"] = change_type
        if q:
            conditions.append("(full_name LIKE :keyword OR description LIKE :keyword)")
            parameters["keyword"] = f"%{q.strip()}%"
        if language:
            conditions.append("language = :language COLLATE NOCASE")
            parameters["language"] = language.strip()
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        total = connection.execute(
            cte + f" SELECT COUNT(*) AS count FROM classified {where_clause}",
            parameters,
        ).fetchone()["count"]
        rows = connection.execute(
            cte
            + f"""
            SELECT repository_id, full_name, owner, name, description, html_url,
                   language, base_rank, target_rank, rank_change, change_type,
                   stars_count, stars_delta, forks_count
            FROM classified
            {where_clause}
            ORDER BY
                CASE change_type
                    WHEN 'new' THEN 1
                    WHEN 'up' THEN 2
                    WHEN 'down' THEN 3
                    WHEN 'dropped' THEN 4
                    ELSE 5
                END,
                ABS(COALESCE(rank_change, 0)) DESC,
                COALESCE(target_rank, base_rank) ASC,
                full_name COLLATE NOCASE ASC
            LIMIT :limit OFFSET :offset
            """,
            {**parameters, "limit": page_size, "offset": (page - 1) * page_size},
        ).fetchall()

    return {
        "base_snapshot": base_snapshot,
        "target_snapshot": target_snapshot,
        "summary": summary,
        "items": [dict(row) for row in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }
