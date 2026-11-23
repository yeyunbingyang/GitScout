"""Environment-backed settings for the local GitScout application."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_local_env_file() -> None:
    """Load a small UTF-8 .env file without overriding process environment values."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


_load_local_env_file()


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
APP_VERSION = "0.4.0"
LOG_LEVEL = os.getenv("GITSCOUT_LOG_LEVEL", "INFO").upper()
