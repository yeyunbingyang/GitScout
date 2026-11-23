"""Collection job history and retry APIs."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.database.connection import get_connection
from app.services.trending_collector import (
    ActiveTrendingJobError,
    create_trending_job,
    execute_trending_job,
    get_collection_job,
    list_collection_jobs,
    utc_now,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("/jobs")
def get_collection_jobs(
    job_type: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    return list_collection_jobs(job_type=job_type, page=page, page_size=page_size)


@router.get("/jobs/{job_id}")
def get_collection_job_detail(job_id: str) -> dict[str, Any]:
    job = get_collection_job(job_id)
    if job is None or not str(job.get("job_type", "")).startswith("trending_"):
        raise HTTPException(status_code=404, detail="Collection job not found")
    for log in job.get("logs", []):
        try:
            log["details"] = json.loads(log.pop("details_json") or "{}")
        except json.JSONDecodeError:
            log["details"] = {}
    return job


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_failed_collection(
    job_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    original = get_collection_job(job_id)
    if original is None or not str(original.get("job_type", "")).startswith("trending_"):
        raise HTTPException(status_code=404, detail="Trending collection job not found")
    if original["status"] not in {"failed", "partial_success"}:
        raise HTTPException(
            status_code=409,
            detail="Only failed or partial-success collection jobs can be retried.",
        )

    period_type = str(original["job_type"]).removeprefix("trending_")
    try:
        retry_job = create_trending_job(
            period_type,
            trigger_type="manual",
            retry_count=int(original.get("retry_count", 0)) + 1,
            retry_of_job_id=job_id,
        )
    except ActiveTrendingJobError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": "This period already has an active collection.", "active_job_id": exc.job_id},
        ) from exc

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO collection_job_logs (job_id, level, message, details_json, created_at)
            VALUES (?, 'INFO', ?, ?, ?)
            """,
            (
                retry_job["id"],
                f"Retry created from previous job {job_id}",
                json.dumps({"retry_of_job_id": job_id}),
                utc_now(),
            ),
        )

    background_tasks.add_task(execute_trending_job, retry_job["id"], period_type)
    return {"job": get_collection_job(retry_job["id"]), "retry_of_job_id": job_id}
