"""Read-only repository list API for the first development milestone."""
from fastapi import APIRouter, Query

from app.database.connection import get_connection

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("")
def list_repositories(
    q: str | None = Query(default=None, max_length=120),
    language: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    conditions: list[str] = []
    parameters: list[object] = []

    if q:
        conditions.append("(full_name LIKE ? OR description LIKE ?)")
        keyword = f"%{q.strip()}%"
        parameters.extend([keyword, keyword])
    if language:
        conditions.append("language = ?")
        parameters.append(language.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * page_size

    with get_connection() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) AS count FROM repositories {where_clause}",
            parameters,
        ).fetchone()["count"]
        rows = connection.execute(
            f"""
            SELECT id, github_repo_id, full_name, owner, name, description,
                   html_url, language, stars_count, forks_count, open_issues_count,
                   last_synced_at
            FROM repositories
            {where_clause}
            ORDER BY stars_count DESC, full_name COLLATE NOCASE ASC
            LIMIT ? OFFSET ?
            """,
            [*parameters, page_size, offset],
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



@router.get("/{repository_id}")
def get_repository_detail(repository_id: int) -> dict[str, object]:
    """Return the repository profile and its saved historical observations."""
    with get_connection() as connection:
        repository_row = connection.execute(
            """
            SELECT id, github_repo_id, full_name, owner, name, description,
                   html_url, language, license_spdx_id, stars_count, forks_count,
                   open_issues_count, github_created_at, github_updated_at,
                   pushed_at, last_synced_at, created_at, updated_at
            FROM repositories WHERE id = ?
            """,
            (repository_id,),
        ).fetchone()
        if repository_row is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Repository not found")

        repository = dict(repository_row)
        topics = [
            row["topic"]
            for row in connection.execute(
                """
                SELECT topic FROM repository_topics
                WHERE repository_id = ? ORDER BY topic COLLATE NOCASE
                """,
                (repository_id,),
            ).fetchall()
        ]
        trending_rows = connection.execute(
            """
            SELECT s.id AS snapshot_id, s.period_type, s.period_key, s.collected_at,
                   s.status AS snapshot_status, i.rank, i.stars_count,
                   i.stars_delta, i.forks_count
            FROM trending_snapshot_items i
            JOIN trending_snapshots s ON s.id = i.snapshot_id
            WHERE i.repository_id = ? AND s.status IN ('success', 'partial_success')
            ORDER BY s.collected_at DESC, s.id DESC
            LIMIT 300
            """,
            (repository_id,),
        ).fetchall()
        stars_rows = connection.execute(
            """
            SELECT s.id AS scan_id, s.finished_at AS captured_at, s.status AS scan_status,
                   s.incomplete_results, i.rank, i.stars_count, i.forks_count
            FROM stars_scan_items i
            JOIN stars_scans s ON s.id = i.scan_id
            WHERE i.repository_id = ? AND s.status IN ('success', 'partial_success')
            ORDER BY s.finished_at DESC, s.id DESC
            LIMIT 200
            """,
            (repository_id,),
        ).fetchall()
        stats_rows = connection.execute(
            """
            SELECT captured_at, source, stars_count, forks_count, open_issues_count
            FROM repository_stats
            WHERE repository_id = ?
            ORDER BY captured_at DESC, id DESC
            LIMIT 200
            """,
            (repository_id,),
        ).fetchall()
        interested_row = connection.execute(
            """
            SELECT marked_at, source_page, tags_json, notes
            FROM interested_projects WHERE repository_id = ?
            """,
            (repository_id,),
        ).fetchone()
        research_row = connection.execute(
            """
            SELECT id, status, priority, research_goal, next_action, conclusion,
                   added_at, started_at, completed_at, updated_at
            FROM research_projects WHERE repository_id = ?
            """,
            (repository_id,),
        ).fetchone()

    trending_history = [dict(row) for row in trending_rows]
    stars_history = [dict(row) for row in stars_rows]
    stats_history = [dict(row) for row in stats_rows]
    best_rank_by_period: dict[str, int] = {}
    for item in trending_history:
        period = str(item["period_type"])
        rank = int(item["rank"])
        best_rank_by_period[period] = min(best_rank_by_period.get(period, rank), rank)

    chronological_stars = list(reversed(stars_history))
    first_stars = int(chronological_stars[0]["stars_count"]) if chronological_stars else None
    latest_stars = int(stars_history[0]["stars_count"]) if stars_history else None
    stars_growth = (
        latest_stars - first_stars
        if first_stars is not None and latest_stars is not None and len(stars_history) > 1
        else None
    )

    repository["topics"] = topics
    repository["interested"] = dict(interested_row) if interested_row else None
    repository["research"] = dict(research_row) if research_row else None
    return {
        "repository": repository,
        "summary": {
            "trending_appearances": len(trending_history),
            "stars_scan_observations": len(stars_history),
            "best_rank_by_period": best_rank_by_period,
            "first_observed_stars": first_stars,
            "latest_observed_stars": latest_stars,
            "observed_stars_growth": stars_growth,
            "first_trending_at": (
                trending_history[-1]["collected_at"] if trending_history else None
            ),
            "last_trending_at": (
                trending_history[0]["collected_at"] if trending_history else None
            ),
        },
        "trending_history": trending_history,
        "stars_history": stars_history,
        "stats_history": stats_history,
    }
