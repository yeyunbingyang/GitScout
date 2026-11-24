"""Local system status and SQLite backup management endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import APP_VERSION
from app.database.connection import get_schema_version
from app.services.backup_manager import (
    _safe_backup_path,
    create_backup,
    get_backup_settings,
    get_pending_restore,
    get_system_info,
    list_backups,
    queue_restore,
    save_backup_settings,
    verify_backup,
)

router = APIRouter(prefix="/system", tags=["system"])


class BackupSettingsUpdate(BaseModel):
    auto_backup_enabled: bool
    interval_hours: int = Field(ge=1, le=168)
    retention_count: int = Field(ge=3, le=90)


class RestoreRequest(BaseModel):
    confirm: bool = False


@router.get("")
def system_status() -> dict[str, Any]:
    try:
        schema_version = get_schema_version()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Unable to read SQLite schema version") from exc
    return {
        "app_version": APP_VERSION,
        "schema_version": schema_version,
        "info": get_system_info(),
        "backup_settings": get_backup_settings(),
        "backups": list_backups(),
    }


@router.get("/backup-settings")
def read_backup_settings() -> dict[str, Any]:
    return {"settings": get_backup_settings()}


@router.patch("/backup-settings")
def update_backup_settings(payload: BackupSettingsUpdate) -> dict[str, Any]:
    return {"settings": save_backup_settings(payload.model_dump())}


@router.get("/backups")
def get_backups() -> dict[str, Any]:
    return {"items": list_backups()}


@router.post("/backups", status_code=status.HTTP_201_CREATED)
def create_manual_backup() -> dict[str, Any]:
    try:
        return {"item": create_backup("manual")}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}") from exc


@router.post("/backups/{filename}/verify")
def verify_database_backup(filename: str) -> dict[str, Any]:
    try:
        return {"result": verify_backup(filename)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/backups/{filename}/download")
def download_database_backup(filename: str) -> FileResponse:
    try:
        path = _safe_backup_path(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/vnd.sqlite3",
        filename=filename,
    )


@router.delete("/backups/{filename}")
def delete_database_backup(filename: str) -> dict[str, Any]:
    pending = get_pending_restore()
    if pending and pending.get("filename") == filename:
        raise HTTPException(status_code=409, detail="Cannot delete the backup queued for restore")
    try:
        path = _safe_backup_path(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path.unlink()
    return {"deleted": True, "filename": filename}


@router.post("/backups/{filename}/restore", status_code=status.HTTP_202_ACCEPTED)
def queue_database_restore(filename: str, payload: RestoreRequest) -> dict[str, Any]:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Explicit restore confirmation is required")
    try:
        return {"restore": queue_restore(filename)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to queue restore: {exc}") from exc
