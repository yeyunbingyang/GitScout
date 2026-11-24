import os
from datetime import datetime, timedelta, timezone

from app.database.connection import get_connection, initialize_database
from app.services.backup_manager import (
    apply_pending_restore,
    create_backup,
    get_backup_settings,
    get_pending_restore,
    list_backups,
    maybe_create_automatic_backup,
    queue_restore,
    save_backup_settings,
    verify_backup,
)


def _prepare_database(monkeypatch, tmp_path, repository_names=("octo/first",)):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    database_path = initialize_database()
    with get_connection(database_path) as connection:
        for index, full_name in enumerate(repository_names, start=1):
            owner, name = full_name.split("/", maxsplit=1)
            connection.execute(
                """
                INSERT INTO repositories (github_repo_id, full_name, owner, name, html_url)
                VALUES (?, ?, ?, ?, ?)
                """,
                (1000 + index, full_name, owner, name, f"https://github.com/{full_name}"),
            )
    return database_path


def test_online_backup_is_integrity_checked_and_restorable(monkeypatch, tmp_path):
    database_path = _prepare_database(monkeypatch, tmp_path)

    backup = create_backup("manual")
    assert backup["valid"] is True
    assert backup["repositories"] == 1
    assert verify_backup(backup["filename"])["integrity_check"] == "ok"

    with get_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO repositories (github_repo_id, full_name, owner, name, html_url)
            VALUES (2002, 'octo/second', 'octo', 'second', 'https://github.com/octo/second')
            """
        )

    queued = queue_restore(backup["filename"])
    assert queued["restart_required"] is True
    assert queued["safety_backup"].startswith("gitscout-pre-restore-")
    assert get_pending_restore()["filename"] == backup["filename"]

    restored = apply_pending_restore()
    assert restored["filename"] == backup["filename"]
    assert get_pending_restore() is None

    with get_connection(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
    assert count == 1
    assert any(item["kind"] == "pre-restore" for item in list_backups())


def test_automatic_backup_interval_and_retention(monkeypatch, tmp_path):
    _prepare_database(monkeypatch, tmp_path)
    save_backup_settings({
        "auto_backup_enabled": True,
        "interval_hours": 24,
        "retention_count": 3,
    })

    first = maybe_create_automatic_backup()
    assert first is not None
    assert maybe_create_automatic_backup() is None

    old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).timestamp()
    os.utime(tmp_path / "backups" / first["filename"], (old_time, old_time))
    second = maybe_create_automatic_backup()
    assert second is not None

    for _ in range(4):
        create_backup("auto")
    automatic = [item for item in list_backups() if item["kind"] == "auto"]
    assert len(automatic) == 3


def test_backup_settings_are_persisted_and_normalized(monkeypatch, tmp_path):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    settings = save_backup_settings({
        "auto_backup_enabled": False,
        "interval_hours": 999,
        "retention_count": 1,
    })

    assert settings == {
        "auto_backup_enabled": False,
        "interval_hours": 168,
        "retention_count": 3,
    }
    assert get_backup_settings() == settings


def test_corrupt_backup_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)
    corrupt = backup_dir / "gitscout-manual-corrupt.db"
    corrupt.write_bytes(b"this is not a SQLite database")

    import pytest

    with pytest.raises(ValueError, match="valid SQLite database"):
        verify_backup(corrupt.name)
