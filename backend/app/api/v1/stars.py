"""Stars leaderboard collection, immutable scan history and query APIs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.database.connection import get_connection
from app.services.stars_collector import (
    ActiveStarsScanError,
    create_stars_scan_job,
    execute_stars_scan,
    get_stars_scan,
    list_stars_leaderboard,
    list_stars_scans,
    retry_stars_scan_job,
)

router = APIRouter(prefix="/stars", tags=["stars"])


class StarsCollectRequest(BaseModel):
    max_results: int = Field(default=5000, ge=100, le=10000)
    min_stars: int = Field(default=100, ge=1, le=10000000)
    include_forks: bool = False


@router.post("/collect", status_code=status.HTTP_202_ACCEPTED)
def start_stars_collection(
    payload: StarsCollectRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    try:
        job = create_stars_scan_job(
            trigger_type="manual",
            max_results=payload.max_results,
            min_stars=payload.min_stars,
            include_forks=payload.include_forks,
        )
    except ActiveStarsScanError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "A Stars leaderboard scan is already queued or running.",
                "active_job_id": exc.job_id,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scan_id = int(job["scan_id"])
    background_tasks.add_task(
        execute_stars_scan,
        job["id"],
        scan_id,
        payload.max_results,
        payload.min_stars,
        payload.include_forks,
    )
    return {"job": job, "scan_id": scan_id}


@router.get("/scans")
def get_stars_scans(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    return list_stars_scans(page=page, page_size=page_size)


@router.get("/scans/{scan_id}")
def get_stars_scan_detail(scan_id: int) -> dict[str, Any]:
    scan = get_stars_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Stars scan not found")
    return scan


@router.post("/scans/{scan_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_stars_collection(
    scan_id: int,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id FROM collection_jobs
            WHERE related_stars_scan_id = ? AND job_type = 'stars_scan'
            ORDER BY created_at DESC LIMIT 1
            """,
            (scan_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Stars scan job not found")

    try:
        job = retry_stars_scan_job(str(row["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActiveStarsScanError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": "A Stars scan is already active.", "active_job_id": exc.job_id},
        ) from exc

    scan_id = int(job["related_stars_scan_id"])
    scan = get_stars_scan(scan_id)
    plan = scan.get("query_plan", {}) if scan else {}
    background_tasks.add_task(
        execute_stars_scan,
        job["id"],
        scan_id,
        int(plan.get("max_results", 5000)),
        int(plan.get("min_stars", 100)),
        bool(plan.get("include_forks", False)),
    )
    return {"job": job, "scan_id": scan_id, "retry_of_job_id": job.get("retry_of_job_id")}


@router.get("/leaderboard")
def get_stars_leaderboard(
    scan_id: int | None = Query(default=None, ge=1),
    q: str | None = Query(default=None, max_length=120),
    language: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    return list_stars_leaderboard(
        scan_id=scan_id,
        q=q,
        language=language,
        page=page,
        page_size=page_size,
    )
