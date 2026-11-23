"""GitScout FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import collections, dashboard, health, repositories, stars, trending
from app.core.config import APP_NAME, APP_VERSION, LOG_LEVEL, PROJECT_ROOT, get_cors_origins
from app.database.connection import initialize_database
from app.services.scheduler import (
    ensure_default_schedules,
    recover_interrupted_jobs,
    scheduler_loop,
    stop_scheduler_tasks,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("gitscout")


@asynccontextmanager
async def lifespan(_: FastAPI):
    database_path = initialize_database()
    interrupted = recover_interrupted_jobs()
    ensure_default_schedules()
    logger.info("SQLite initialized at %s", database_path)
    if interrupted:
        logger.warning("Marked %s interrupted collection job(s) after restart", interrupted)
    scheduler_task = asyncio.create_task(scheduler_loop(), name="gitscout-collection-scheduler")
    try:
        yield
    finally:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
        await stop_scheduler_tasks()
        recover_interrupted_jobs()
        logger.info("GitScout API stopped")


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Local GitHub project discovery and research workspace.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(repositories.router, prefix="/api/v1")
app.include_router(trending.router, prefix="/api/v1")
app.include_router(stars.router, prefix="/api/v1")
app.include_router(collections.router, prefix="/api/v1")

frontend_dist = PROJECT_ROOT / "frontend" / "dist"
assets_dir = frontend_dist / "assets"

if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")


@app.get("/", include_in_schema=False)
def frontend_root():
    index_file = frontend_dist / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "message": "GitScout API is running. Start the React dev server or build frontend/dist.",
        "api_docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_fallback(full_path: str):
    if full_path.startswith("api/") or full_path in {"docs", "redoc", "openapi.json"}:
        raise HTTPException(status_code=404, detail="Not found")

    candidate = (frontend_dist / full_path).resolve()
    if frontend_dist.resolve() in candidate.parents and candidate.is_file():
        return FileResponse(candidate)

    index_file = frontend_dist / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend build not found")
