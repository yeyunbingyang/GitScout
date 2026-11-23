"""SQLite connection management and versioned SQL migrations."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.core.config import get_database_path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Create a configured connection. Callers own and must close it."""
    path = Path(db_path) if db_path is not None else get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        path,
        timeout=5.0,
        isolation_level="DEFERRED",
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


@contextmanager
def get_connection(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a short-lived connection and commit or roll back the unit of work."""
    connection = connect(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(db_path: str | Path | None = None) -> Path:
    """Enable WAL and apply all pending SQL migrations exactly once."""
    path = Path(db_path) if db_path is not None else get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = connect(path)
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }

        for migration_file in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            version = migration_file.name.split("_", maxsplit=1)[0]
            if version in applied:
                continue

            sql = migration_file.read_text(encoding="utf-8")
            applied_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            safe_version = version.replace("'", "''")
            safe_applied_at = applied_at.replace("'", "''")
            script = (
                "BEGIN IMMEDIATE;\n"
                + sql
                + "\nINSERT INTO schema_migrations(version, applied_at) "
                + f"VALUES ('{safe_version}', '{safe_applied_at}');\n"
                + "COMMIT;"
            )
            try:
                connection.executescript(script)
            except Exception:
                connection.rollback()
                raise

        return path
    finally:
        connection.close()


def get_schema_version(db_path: str | Path | None = None) -> str | None:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return row["version"] if row else None
