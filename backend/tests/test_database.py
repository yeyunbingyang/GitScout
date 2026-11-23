import sqlite3

import pytest

from app.database.connection import get_connection, get_schema_version, initialize_database


def test_initial_migration_creates_core_tables(tmp_path):
    database_path = tmp_path / "gitscout.db"

    initialize_database(database_path)

    with get_connection(database_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "repositories" in tables
    assert "trending_snapshots" in tables
    assert "stars_scans" in tables
    assert "recommendation_runs" in tables
    assert "research_projects" in tables
    assert "collection_jobs" in tables
    assert get_schema_version(database_path) == "0002"
    with get_connection(database_path) as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(collection_jobs)")}
    assert "retry_of_job_id" in columns


def test_migration_is_idempotent(tmp_path):
    database_path = tmp_path / "gitscout.db"

    initialize_database(database_path)
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations"
        ).fetchone()["count"]

    assert count == 1


def test_repository_unique_constraints_and_foreign_keys(tmp_path):
    database_path = tmp_path / "gitscout.db"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO repositories (github_repo_id, full_name, owner, name, html_url)
            VALUES (123, 'octo/demo', 'octo', 'demo', 'https://github.com/octo/demo')
            """
        )

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path) as connection:
            connection.execute(
                """
                INSERT INTO repositories (github_repo_id, full_name, owner, name, html_url)
                VALUES (123, 'octo/another', 'octo', 'another', 'https://github.com/octo/another')
                """
            )

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path) as connection:
            connection.execute(
                "INSERT INTO interested_projects (repository_id) VALUES (9999)"
            )


def test_wal_mode_is_enabled(tmp_path):
    database_path = tmp_path / "gitscout.db"
    initialize_database(database_path)

    with get_connection(database_path) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0].lower()

    assert journal_mode == "wal"
