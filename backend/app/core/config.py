"""Environment-backed settings for the local GitScout application."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def get_data_dir() -> Path:
    configured = os.getenv("GITSCOUT_DATA_DIR", "").strip()
    if not configured:
        return PROJECT_ROOT / "data"

    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def get_database_path() -> Path:
    return get_data_dir() / "gitscout.db"


def get_cors_origins() -> list[str]:
    raw = os.getenv(
        "GITSCOUT_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


APP_NAME = "GitScout"
APP_VERSION = "0.1.0"
LOG_LEVEL = os.getenv("GITSCOUT_LOG_LEVEL", "INFO").upper()
