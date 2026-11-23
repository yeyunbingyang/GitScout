"""Trending leaderboard, immutable history and collection trigger APIs."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.database.connection import get_connection
from app.services.trending_collector import (
    ActiveTrendingJobError,
    create_trending_job,
    execute_trending_job,
    validate_period,
)

router = APIRouter(prefix="/trending", tags=["trending"])


class TrendingCollectRequest(BaseModel):
    period_type: Literal["daily", "weekly", "monthly"] = Field(
        description="Trending period to collect"
    )


def _snapshot_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


@router.post("/collect", status_code=status.HTTP_202_ACCEPTED)
def start_trending_collection(
    payload: TrendingCollectRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Queue a manual collection and execute it after returning the job response."""
    try:
        job = create_trending_job(payload.period_type, trigger_type="manual")
    except ActiveTrendingJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This period already has a queued or running collection.",
                "active_job_id": exc.job_id,
            },
        ) from exc
    background_tasks.add_task(execute_trending_job, job["id"], payload.period_type)
    return {"job": job}


@router.get("/snapshots")
def list_trending_snapshots(
    period_type: Literal["daily", "weekly", "monthly"] = "daily",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List successful historical snapshots; failed attempts remain in collection logs."""
    offset = (page - 1) * page_size
    with get_connection() as connection:
        total = connection.execute(
            """
            SELECT COUNT(*) AS count FROM trending_snapshots
            WHERE period_type = ? AND status IN ('success', 'partial_success')
            """,
            (period_type,),
        ).fetchone()["count"]
        rows = connection.execute(
            """
            SELECT id, period_type, period_key, collected_at, status, source_url, item_count,
                   error_summary
            FROM trending_snapshots
            WHERE period_type = ? AND status IN ('success', 'partial_success')
            ORDER BY collected_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (period_type, page_size, offset),
        ).fetchall()

    return {
        "items": [dict(row) for row in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.get("/snapshots/{snapshot_id}")
def get_trending_snapshot(snapshot_id: int) -> dict[str, Any]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, period_type, period_key, collected_at, status, source_url, item_count,
                   error_summary
            FROM trending_snapshots WHERE id = ?
            """,
            (snapshot_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Trending snapshot not found")
    return _snapshot_dict(row)


@router.get("")
def list_trending_items(
    period_type: Literal["daily", "weekly", "monthly"] = "daily",
    snapshot_id: int | None = Query(default=None, ge=1),
    q: str | None = Query(default=None, max_length=120),
    language: str | None = Query(default=None, max_length=80),
    topic: str | None = Query(default=None, max_length=80),
    rank_min: int | None = Query(default=None, ge=1),
    rank_max: int | None = Query(default=None, ge=1),
    sort_by: Literal["rank", "stars", "delta", "forks"] = "rank",
    sort_order: Literal["asc", "desc"] = "asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict[str, Any]:
    """Read one saved snapshot. This endpoint never requests GitHub."""
    period_type = validate_period(period_type)
    if rank_min is not None and rank_max is not None and rank_min > rank_max:
        raise HTTPException(status_code=422, detail="rank_min cannot exceed rank_max")

    with get_connection() as connection:
        if snapshot_id is not None:
            snapshot_row = connection.execute(
                """
                SELECT id, period_type, period_key, collected_at, status, source_url, item_count,
                       error_summary
                FROM trending_snapshots
                WHERE id = ? AND period_type = ? AND status IN ('success', 'partial_success')
                """,
                (snapshot_id, period_type),
            ).fetchone()
        else:
            snapshot_row = connection.execute(
                """
                SELECT id, period_type, period_key, collected_at, status, source_url, item_count,
                       error_summary
                FROM trending_snapshots
                WHERE period_type = ? AND status IN ('success', 'partial_success')
                ORDER BY collected_at DESC, id DESC LIMIT 1
                """,
                (period_type,),
            ).fetchone()

        if snapshot_row is None:
            if snapshot_id is not None:
                raise HTTPException(status_code=404, detail="Snapshot not found for this period")
            return {
                "snapshot": None,
                "items": [],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": 0,
                    "total_pages": 0,
                },
            }

        snapshot = dict(snapshot_row)
        conditions = ["i.snapshot_id = ?"]
        parameters: list[Any] = [snapshot["id"]]

        if q:
            conditions.append("(r.full_name LIKE ? OR r.description LIKE ?)")
            keyword = f"%{q.strip()}%"
            parameters.extend([keyword, keyword])
        if language:
            conditions.append("r.language = ? COLLATE NOCASE")
            parameters.append(language.strip())
        if topic:
            conditions.append(
                """
                EXISTS (
                    SELECT 1 FROM repository_topics filter_topic
                    WHERE filter_topic.repository_id = r.id AND filter_topic.topic = ? COLLATE NOCASE
                )
                """
            )
            parameters.append(topic.strip())
        if rank_min is not None:
            conditions.append("i.rank >= ?")
            parameters.append(rank_min)
        if rank_max is not None:
            conditions.append("i.rank <= ?")
            parameters.append(rank_max)

        where_clause = "WHERE " + " AND ".join(conditions)
        sort_columns = {
            "rank": "i.rank",
            "stars": "i.stars_count",
            "delta": "i.stars_delta",
            "forks": "i.forks_count",
        }
        sort_column = sort_columns[sort_by]
        order_clause = "ASC" if sort_order == "asc" else "DESC"
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM trending_snapshot_items i
            JOIN repositories r ON r.id = i.repository_id
            {where_clause}
            """,
            parameters,
        ).fetchone()["count"]
        offset = (page - 1) * page_size
        rows = connection.execute(
            f"""
            SELECT i.rank, i.stars_count, i.stars_delta, i.forks_count,
                   r.id AS repository_id, r.github_repo_id, r.full_name, r.owner, r.name,
                   r.description, r.html_url, r.language,
                   GROUP_CONCAT(DISTINCT t.topic) AS topics
            FROM trending_snapshot_items i
            JOIN repositories r ON r.id = i.repository_id
            LEFT JOIN repository_topics t ON t.repository_id = r.id
            {where_clause}
            GROUP BY i.id, r.id
            ORDER BY {sort_column} {order_clause}, i.rank ASC
            LIMIT ? OFFSET ?
            """,
            [*parameters, page_size, offset],
        ).fetchall()

    items = []
    for row in rows:
        item = dict(row)
        item["topics"] = [value for value in (item.pop("topics") or "").split(",") if value]
        items.append(item)

    return {
        "snapshot": snapshot,
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }
