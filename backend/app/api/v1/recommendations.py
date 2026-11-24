"""Recommendation profiles, immutable calculation runs and ranked result APIs."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.recommendation_engine import (
    create_recommendation_run,
    get_latest_recommendation_run_id,
    get_recommendation_run_detail,
    list_recommendation_profiles,
    list_recommendation_runs,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

RecommendationCategory = Literal["all", "priority", "emerging", "stable"]
RecommendationDimension = Literal["all", "stars", "daily", "weekly", "monthly"]


class RecommendationRunCreate(BaseModel):
    profile_id: int | None = Field(default=None, gt=0)


def _empty_run_response() -> dict[str, Any]:
    return {
        "run": None,
        "summary": {
            "candidate_count": 0,
            "scored_count": 0,
            "priority_count": 0,
            "emerging_count": 0,
            "stable_count": 0,
            "grade_counts": {
                "priority": 0,
                "strong": 0,
                "watch": 0,
                "observe": 0,
                "low": 0,
            },
            "latest_stars_scan": None,
            "scoring_stars_scan": None,
            "stars_stale": True,
            "stars_incomplete": False,
            "stars_stale_after_days": 7,
            "stars_scan_age_days": None,
            "data_coverage": {},
            "candidate_sources": [],
        },
        "items": [],
        "pagination": {"page": 1, "page_size": 50, "total": 0, "total_pages": 0},
        "filters": {"category": "all", "category_label": "全部推荐", "query": ""},
    }


@router.get("/profiles")
def get_recommendation_profiles() -> dict[str, Any]:
    return {"items": list_recommendation_profiles()}


@router.get("/runs")
def get_recommendation_run_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    return list_recommendation_runs(page=page, page_size=page_size)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def calculate_recommendations(payload: RecommendationRunCreate) -> dict[str, Any]:
    try:
        return create_recommendation_run(profile_id=payload.profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs/latest")
def get_latest_recommendations(
    category: RecommendationCategory = Query(default="all"),
    q: str | None = Query(default=None, max_length=200),
    language: str | None = Query(default=None, max_length=80),
    dimension: RecommendationDimension = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    run_id = get_latest_recommendation_run_id()
    if run_id is None:
        return _empty_run_response()
    result = get_recommendation_run_detail(
        run_id,
        category=category,
        q=q,
        language=language,
        dimension=dimension,
        page=page,
        page_size=page_size,
    )
    return result or _empty_run_response()


@router.get("/runs/{run_id}")
def get_recommendation_run(
    run_id: int,
    category: RecommendationCategory = Query(default="all"),
    q: str | None = Query(default=None, max_length=200),
    language: str | None = Query(default=None, max_length=80),
    dimension: RecommendationDimension = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    result = get_recommendation_run_detail(
        run_id,
        category=category,
        q=q,
        language=language,
        dimension=dimension,
        page=page,
        page_size=page_size,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Recommendation run not found")
    return result
