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
