"""Dashboard summary endpoint."""
from fastapi import APIRouter

from app.database.connection import get_connection

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary() -> dict[str, object]:
    with get_connection() as connection:
        repository_count = connection.execute(
            "SELECT COUNT(*) AS count FROM repositories"
        ).fetchone()["count"]
        trending_count = connection.execute(
            "SELECT COUNT(*) AS count FROM trending_snapshots WHERE status = 'success'"
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
