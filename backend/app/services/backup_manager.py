"""Local SQLite backup, verification and deferred restore utilities."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_data_dir, get_database_path

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_SETTINGS: dict[str, Any] = {
    "auto_backup_enabled": True,
    "interval_hours": 24,
    "retention_count": 14,
}
BACKUP_PREFIX = "gitscout-"
PENDING_RESTORE_FILENAME = "restore_pending.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def get_backup_dir() -> Path:
    return get_data_dir() / "backups"


def _settings_path() -> Path:
    return get_data_dir() / "system_settings.json"


def _pending_restore_path() -> Path:
    return get_data_dir() / PENDING_RESTORE_FILENAME


def get_backup_settings() -> dict[str, Any]:
    path = _settings_path()
    settings = dict(DEFAULT_BACKUP_SETTINGS)
    if path.is_file():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                settings["auto_backup_enabled"] = bool(saved.get("auto_backup_enabled", settings["auto_backup_enabled"]))
                settings["interval_hours"] = max(1, min(168, int(saved.get("interval_hours", settings["interval_hours"]))))
                settings["retention_count"] = max(3, min(90, int(saved.get("retention_count", settings["retention_count"]))))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            logger.warning("Unable to read local backup settings; defaults are active")
    return settings


def save_backup_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = {
        "auto_backup_enabled": bool(payload["auto_backup_enabled"]),
        "interval_hours": max(1, min(168, int(payload["interval_hours"]))),
        "retention_count": max(3, min(90, int(payload["retention_count"]))),
    }
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return settings


def _safe_backup_path(filename: str) -> Path:
    if (
        not filename
        or Path(filename).name != filename
        or not filename.startswith(BACKUP_PREFIX)
        or not filename.endswith(".db")
        or any(character in filename for character in ("/", "\\", "\0"))
    ):
        raise ValueError("Invalid backup filename")
    path = get_backup_dir() / filename
    if not path.is_file():
        raise FileNotFoundError("Backup file not found")
    return path


def _integrity_check(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Backup database is missing or empty")
    connection = sqlite3.connect(str(path), timeout=30)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        integrity = str(result[0]) if result else "no result"
        if integrity.lower() != "ok":
            raise ValueError(f"SQLite integrity check failed: {integrity}")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if "schema_migrations" not in tables:
            raise ValueError("Backup does not contain a GitScout schema")
        schema_row = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return {
            "integrity_check": integrity,
            "schema_version": str(schema_row[0]) if schema_row else None,
            "repositories": (
                int(connection.execute("SELECT COUNT(*) FROM repositories").fetchone()[0])
                if "repositories" in tables else 0
            ),
        }
    finally:
        connection.close()


def verify_backup(filename: str) -> dict[str, Any]:
    path = _safe_backup_path(filename)
    details = _integrity_check(path)
    return {
        "filename": filename,
        "valid": True,
        **details,
        "size_bytes": path.stat().st_size,
    }


def _backup_filename(kind: str) -> str:
    if kind not in {"manual", "auto", "pre-restore"}:
        raise ValueError("Unsupported backup type")
    stamp = _utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    return f"{BACKUP_PREFIX}{kind}-{stamp}.db"


def create_backup(kind: str = "manual") -> dict[str, Any]:
    database_path = get_database_path()
    if not database_path.is_file():
        raise FileNotFoundError("GitScout database has not been initialized")

    backup_dir = get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    filename = _backup_filename(kind)
    target = backup_dir / filename
    temporary = backup_dir / (filename + ".tmp")

    source = sqlite3.connect(str(database_path), timeout=30)
    destination = sqlite3.connect(str(temporary), timeout=30)
    try:
        source.execute("PRAGMA busy_timeout = 30000")
        destination.execute("PRAGMA busy_timeout = 30000")
        source.backup(destination, pages=256, sleep=0.05)
        destination.commit()
    except Exception:
        destination.close()
        source.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        destination.close()
        source.close()

    try:
        details = _integrity_check(temporary)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    item = {
        "filename": filename,
        "kind": kind,
        "created_at": _iso(_utc_now()),
        "size_bytes": target.stat().st_size,
        "valid": True,
        "schema_version": details["schema_version"],
        "repositories": details["repositories"],
    }
    logger.info("Created %s SQLite backup: %s", kind, target)
    if kind in {"auto", "manual"}:
        prune_automatic_backups(int(get_backup_settings()["retention_count"]))
    return item


def list_backups() -> list[dict[str, Any]]:
    backup_dir = get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in backup_dir.glob(f"{BACKUP_PREFIX}*.db"):
        if not path.is_file():
            continue
        name = path.name
        kind = "auto" if "-auto-" in name else "pre-restore" if "-pre-restore-" in name else "manual"
        created = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        items.append({
            "filename": name,
            "kind": kind,
            "created_at": _iso(created),
            "size_bytes": path.stat().st_size,
            "valid": None,
            "schema_version": None,
            "repositories": None,
        })
    return sorted(items, key=lambda item: item["created_at"], reverse=True)


def prune_automatic_backups(retention_count: int | None = None) -> int:
    keep = int(retention_count if retention_count is not None else get_backup_settings()["retention_count"])
    automatic = [item for item in list_backups() if item["kind"] == "auto"]
    removed = 0
    for item in automatic[max(3, keep):]:
        try:
            _safe_backup_path(item["filename"]).unlink()
            removed += 1
        except FileNotFoundError:
            continue
    return removed


def maybe_create_automatic_backup() -> dict[str, Any] | None:
    settings = get_backup_settings()
    if not settings["auto_backup_enabled"]:
        return None
    database_path = get_database_path()
    if not database_path.is_file():
        return None

    automatic = [item for item in list_backups() if item["kind"] == "auto"]
    if automatic:
        latest = datetime.fromisoformat(automatic[0]["created_at"].replace("Z", "+00:00"))
        elapsed = (_utc_now() - latest).total_seconds()
        if elapsed < int(settings["interval_hours"]) * 3600:
            return None
    return create_backup("auto")


def get_pending_restore() -> dict[str, Any] | None:
    path = _pending_restore_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "filename": str(payload["filename"]),
            "queued_at": str(payload["queued_at"]),
            "safety_backup": str(payload["safety_backup"]),
        }
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return {"filename": None, "queued_at": None, "safety_backup": None, "invalid": True}


def queue_restore(filename: str) -> dict[str, Any]:
    if _pending_restore_path().exists():
        raise RuntimeError("A restore is already pending. Restart GitScout before queuing another one.")
    details = verify_backup(filename)
    safety_backup = create_backup("pre-restore")
    payload = {
        "filename": filename,
        "queued_at": _iso(_utc_now()),
        "safety_backup": safety_backup["filename"],
    }
    path = _pending_restore_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    logger.warning("Restore queued for next GitScout startup: %s", filename)
    return {
        **payload,
        "verified": details,
        "restart_required": True,
    }


def apply_pending_restore() -> dict[str, Any] | None:
    pending_path = _pending_restore_path()
    if not pending_path.is_file():
        return None

    pending = get_pending_restore()
    if not pending or pending.get("invalid"):
        raise RuntimeError("Pending restore marker is invalid; inspect data/restore_pending.json")
    filename = str(pending["filename"])
    source_path = _safe_backup_path(filename)
    _integrity_check(source_path)

    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = database_path.with_name(database_path.name + ".restore.tmp")
    temporary.unlink(missing_ok=True)

    source = sqlite3.connect(str(source_path), timeout=30)
    destination = sqlite3.connect(str(temporary), timeout=30)
    try:
        source.backup(destination, pages=256, sleep=0.05)
        destination.commit()
    except Exception:
        destination.close()
        source.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        destination.close()
        source.close()

    try:
        details = _integrity_check(temporary)
        for suffix in ("-wal", "-shm", "-journal"):
            Path(str(database_path) + suffix).unlink(missing_ok=True)
        os.replace(temporary, database_path)
        pending_path.unlink(missing_ok=True)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    result = {"filename": filename, "schema_version": details["schema_version"]}
    logger.warning("Applied deferred GitScout database restore: %s", filename)
    return result


def get_system_info() -> dict[str, Any]:
    database_path = get_database_path()
    size = 0
    if database_path.is_file():
        size += database_path.stat().st_size
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(database_path) + suffix)
            if sidecar.is_file():
                size += sidecar.stat().st_size
    return {
        "data_dir": str(get_data_dir().resolve()),
        "database_path": str(database_path.resolve()),
        "database_exists": database_path.is_file(),
        "database_size_bytes": size,
        "backup_dir": str(get_backup_dir().resolve()),
        "github_token_configured": bool(os.getenv("GITHUB_TOKEN", "").strip()),
        "pending_restore": get_pending_restore(),
    }
