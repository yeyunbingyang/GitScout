"""Collection job history and retry APIs."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field
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
from app.services.scheduler import list_schedules, save_schedule, save_stars_schedule
from app.services.stars_collector import (
    execute_stars_scan,
    get_stars_scan,
    retry_stars_scan_job,
)

router = APIRouter(prefix="/collections", tags=["collections"])


class ScheduleUpdate(BaseModel):
    enabled: bool = False
    time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Asia/Shanghai"
    weekday: int = Field(default=0, ge=0, le=6)
    day_of_month: int = Field(default=1, ge=1, le=28)


class StarsScheduleUpdate(BaseModel):
    enabled: bool = False
    time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Asia/Shanghai"
    max_results: int = Field(default=5000, ge=100, le=10000)
    min_stars: int = Field(default=100, ge=1, le=10000000)
    include_forks: bool = False


@router.get("/schedules")
def get_collection_schedules() -> dict[str, Any]:
    return {"items": list_schedules()}


@router.put("/schedules/stars")
def update_stars_collection_schedule(payload: StarsScheduleUpdate) -> dict[str, Any]:
    settings = {
        "time": payload.time,
        "max_results": payload.max_results,
        "min_stars": payload.min_stars,
        "include_forks": payload.include_forks,
    }
    try:
        schedule = save_stars_schedule(
            enabled=payload.enabled,
            settings=settings,
            timezone_name=payload.timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"schedule": schedule}


@router.put("/schedules/{period_type}")
def update_collection_schedule(
    period_type: Literal["daily", "weekly", "monthly"],
    payload: ScheduleUpdate,
) -> dict[str, Any]:
    settings = {
        "time": payload.time,
        "weekday": payload.weekday,
        "day_of_month": payload.day_of_month,
    }
    try:
        schedule = save_schedule(
            period_type,
            enabled=payload.enabled,
            settings=settings,
            timezone_name=payload.timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"schedule": schedule}


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
    if job is None or not (
        str(job.get("job_type", "")).startswith("trending_")
        or job.get("job_type") == "stars_scan"
    ):
        raise HTTPException(status_code=404, detail="Collection job not found")
    for log in job.get("logs", []):
        try:
            log["details"] = json.loads(log.pop("details_json") or "{}")
        except json.JSONDecodeError:
            log["details"] = {}
    if job.get("job_type") == "stars_scan" and job.get("related_stars_scan_id"):
        job["stars_scan"] = get_stars_scan(int(job["related_stars_scan_id"]))
    return job


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_failed_collection(
    job_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    original = get_collection_job(job_id)
    if original is None or not (
        str(original.get("job_type", "")).startswith("trending_")
        or original.get("job_type") == "stars_scan"
    ):
        raise HTTPException(status_code=404, detail="Collection job not found")
    if original["status"] not in {"failed", "partial_success", "interrupted"}:
        raise HTTPException(
            status_code=409,
            detail="Only failed, partial-success or interrupted collection jobs can be retried.",
        )

    if original.get("job_type") == "stars_scan":
        try:
            retry_job = retry_stars_scan_job(job_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        scan_id = int(retry_job["related_stars_scan_id"])
        scan = get_stars_scan(scan_id)
        plan = scan.get("query_plan", {}) if scan else {}
        background_tasks.add_task(
            execute_stars_scan,
            retry_job["id"],
            scan_id,
            int(plan.get("max_results", 5000)),
            int(plan.get("min_stars", 100)),
            bool(plan.get("include_forks", False)),
        )
        return {"job": retry_job, "retry_of_job_id": job_id, "scan_id": scan_id}

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
