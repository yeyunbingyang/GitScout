"""Health and readiness endpoints."""
from fastapi import APIRouter, HTTPException

from app.database.connection import get_connection, get_schema_version

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check() -> dict[str, object]:
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        schema_version = get_schema_version()
    except Exception as exc:  # pragma: no cover - exercised by deployment failures
        raise HTTPException(status_code=503, detail="SQLite database is unavailable") from exc

    return {
        "status": "ok",
        "service": "gitscout-api",
        "database": "connected",
        "schema_version": schema_version,
    }
