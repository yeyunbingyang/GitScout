from datetime import datetime, timezone

from app.database.connection import initialize_database
from app.services.scheduler import (
    calculate_next_run,
    ensure_default_schedules,
    list_schedules,
    save_schedule,
    save_stars_schedule,
)


def test_calculate_daily_weekly_and_monthly_next_run():
    after = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)

    daily = calculate_next_run("daily", {"time": "09:00"}, "UTC", after)
    weekly = calculate_next_run(
        "weekly", {"time": "09:00", "weekday": 0}, "UTC", after
    )
    monthly = calculate_next_run(
        "monthly", {"time": "09:00", "day_of_month": 1}, "UTC", after
    )

    assert daily == "2026-11-25T09:00:00Z"
    assert weekly == "2026-11-30T09:00:00Z"
    assert monthly == "2026-12-01T09:00:00Z"


def test_default_schedules_are_disabled_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    initialize_database()

    ensure_default_schedules()
    ensure_default_schedules()
    schedules = list_schedules()

    assert len(schedules) == 4
    assert {item["job_type"] for item in schedules} == {
        "trending_daily", "trending_weekly", "trending_monthly", "stars_daily"
    }
    assert all(item["enabled"] is False for item in schedules)


def test_save_schedule_persists_enabled_state_and_next_run(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    initialize_database()
    ensure_default_schedules()

    saved = save_schedule(
        "daily",
        enabled=True,
        settings={"time": "08:30", "weekday": 0, "day_of_month": 1},
        timezone_name="Asia/Tokyo",
    )

    assert saved["enabled"] is True
    assert saved["timezone"] == "Asia/Tokyo"
    assert saved["settings"]["time"] == "08:30"
    assert saved["next_run_at"]



def test_save_stars_schedule_persists_daily_scan_options(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    initialize_database()
    ensure_default_schedules()

    saved = save_stars_schedule(
        enabled=True,
        settings={
            "time": "07:30",
            "max_results": 3000,
            "min_stars": 250,
            "include_forks": True,
        },
        timezone_name="Asia/Tokyo",
    )

    assert saved["job_type"] == "stars_daily"
    assert saved["enabled"] is True
    assert saved["timezone"] == "Asia/Tokyo"
    assert saved["settings"]["max_results"] == 3000
    assert saved["settings"]["include_forks"] is True
    assert saved["next_run_at"]
