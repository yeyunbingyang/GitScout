"""Local asyncio scheduler for daily, weekly and monthly Trending collection."""
from __future__ import annotations

import asyncio
import json
import logging
from calendar import monthrange
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.database.connection import get_connection
from app.services.trending_collector import (
    ActiveTrendingJobError,
    create_trending_job,
    execute_trending_job,
    utc_now,
)

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, dict[str, Any]] = {
    "daily": {"time": "09:00", "weekday": 0, "day_of_month": 1},
    "weekly": {"time": "09:00", "weekday": 0, "day_of_month": 1},
    "monthly": {"time": "09:00", "weekday": 0, "day_of_month": 1},
}
DEFAULT_TIMEZONE = "Asia/Shanghai"
_scheduler_tasks: set[asyncio.Task[Any]] = set()


def _local_time(value: str) -> time:
    hour_text, minute_text = value.split(":", maxsplit=1)
    return time(hour=int(hour_text), minute=int(minute_text))


def calculate_next_run(
    period_type: str,
    settings: dict[str, Any],
    timezone_name: str,
    after: datetime | None = None,
) -> str:
    """Calculate the next scheduled wall-clock occurrence and return UTC ISO-8601."""
    if period_type not in DEFAULTS:
        raise ValueError("Unsupported schedule period")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc

    now_utc = after or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_local = now_utc.astimezone(zone)
    target_time = _local_time(str(settings.get("time", "09:00")))

    if period_type == "daily":
        candidate_date = now_local.date()
        candidate = datetime.combine(candidate_date, target_time, tzinfo=zone)
        if candidate <= now_local:
            candidate = datetime.combine(candidate_date + timedelta(days=1), target_time, tzinfo=zone)
    elif period_type == "weekly":
        weekday = int(settings.get("weekday", 0))
        if not 0 <= weekday <= 6:
            raise ValueError("weekday must be between 0 and 6")
        days_ahead = (weekday - now_local.weekday()) % 7
        candidate_date = now_local.date() + timedelta(days=days_ahead)
        candidate = datetime.combine(candidate_date, target_time, tzinfo=zone)
        if candidate <= now_local:
            candidate += timedelta(days=7)
    else:
        day = int(settings.get("day_of_month", 1))
        if not 1 <= day <= 28:
            raise ValueError("day_of_month must be between 1 and 28")
        candidate_date = now_local.date().replace(day=day)
        candidate = datetime.combine(candidate_date, target_time, tzinfo=zone)
        if candidate <= now_local:
            year = now_local.year + (1 if now_local.month == 12 else 0)
            month = 1 if now_local.month == 12 else now_local.month + 1
            last_day = monthrange(year, month)[1]
            candidate_date = candidate_date.replace(year=year, month=month, day=min(day, last_day))
            candidate = datetime.combine(candidate_date, target_time, tzinfo=zone)

    return candidate.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_default_schedules() -> None:
    now = datetime.now(timezone.utc)
    with get_connection() as connection:
        for period_type, settings in DEFAULTS.items():
            connection.execute(
                """
                INSERT OR IGNORE INTO collection_schedules (
                    name, job_type, enabled, timezone, next_run_at, settings_json
                ) VALUES (?, ?, 0, ?, ?, ?)
                """,
                (
                    f"Trending {period_type.title()}",
                    f"trending_{period_type}",
                    DEFAULT_TIMEZONE,
                    calculate_next_run(period_type, settings, DEFAULT_TIMEZONE, now),
                    json.dumps(settings),
                ),
            )


def list_schedules() -> list[dict[str, Any]]:
    ensure_default_schedules()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, job_type, enabled, interval_seconds, cron_expression,
                   timezone, next_run_at, last_run_at, settings_json
            FROM collection_schedules
            WHERE job_type IN ('trending_daily', 'trending_weekly', 'trending_monthly')
            ORDER BY CASE job_type
                WHEN 'trending_daily' THEN 1
                WHEN 'trending_weekly' THEN 2
                ELSE 3 END
            """
        ).fetchall()

    schedules = []
    for row in rows:
        item = dict(row)
        try:
            item["settings"] = json.loads(item.pop("settings_json") or "{}")
        except json.JSONDecodeError:
            item["settings"] = {}
        item["enabled"] = bool(item["enabled"])
        schedules.append(item)
    return schedules


def save_schedule(
    period_type: str,
    enabled: bool,
    settings: dict[str, Any],
    timezone_name: str,
) -> dict[str, Any]:
    if period_type not in DEFAULTS:
        raise ValueError("period_type must be daily, weekly, or monthly")
    next_run = (
        calculate_next_run(period_type, settings, timezone_name)
        if enabled
        else None
    )
    name = f"Trending {period_type.title()}"
    now = utc_now()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO collection_schedules (
                name, job_type, enabled, cron_expression, timezone, next_run_at,
                settings_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_type) DO UPDATE SET
                name = excluded.name,
                enabled = excluded.enabled,
                cron_expression = excluded.cron_expression,
                timezone = excluded.timezone,
                next_run_at = excluded.next_run_at,
                settings_json = excluded.settings_json,
                updated_at = excluded.updated_at
            """,
            (
                name,
                f"trending_{period_type}",
                1 if enabled else 0,
                f"{period_type}@{settings.get('time', '09:00')}",
                timezone_name,
                next_run,
                json.dumps(settings),
                now,
            ),
        )
    return next(item for item in list_schedules() if item["job_type"] == f"trending_{period_type}")


def recover_interrupted_jobs() -> int:
    """Mark jobs left queued/running by a previous process as interrupted."""
    now = utc_now()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id FROM collection_jobs
            WHERE job_type LIKE 'trending_%' AND status IN ('queued', 'running')
            """
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                UPDATE collection_jobs
                SET status = 'interrupted', progress = 100, finished_at = ?,
                    error_code = 'PROCESS_RESTARTED',
                    error_message = 'The local GitScout process stopped before this job completed.'
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            connection.execute(
                """
                INSERT INTO collection_job_logs (job_id, level, message, details_json, created_at)
                VALUES (?, 'WARNING', 'Job marked interrupted after process restart', '{}', ?)
                """,
                (row["id"], now),
            )
    return len(rows)


def _keep_task(task: asyncio.Task[Any]) -> None:
    _scheduler_tasks.add(task)
    task.add_done_callback(_scheduler_tasks.discard)


async def scheduler_loop(poll_seconds: int = 15) -> None:
    """Poll enabled schedules and dispatch due collection jobs in this process."""
    ensure_default_schedules()
    while True:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        with get_connection() as connection:
            due = connection.execute(
                """
                SELECT id, job_type, timezone, settings_json
                FROM collection_schedules
                WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (now_text,),
            ).fetchall()

        for schedule in due:
            job_type = schedule["job_type"]
            period_type = job_type.removeprefix("trending_")
            try:
                settings = json.loads(schedule["settings_json"] or "{}")
                job = create_trending_job(
                    period_type,
                    trigger_type="scheduled",
                    schedule_id=int(schedule["id"]),
                )
                task = asyncio.create_task(execute_trending_job(job["id"], period_type))
                _keep_task(task)
                logger.info("Scheduled %s collection job %s", period_type, job["id"])
            except ActiveTrendingJobError:
                logger.info("Skipped scheduled %s collection because another job is active", period_type)
            except Exception:
                logger.exception("Could not dispatch scheduled %s collection", period_type)
                settings = json.loads(schedule["settings_json"] or "{}")

            try:
                next_run = calculate_next_run(period_type, settings, schedule["timezone"], after=now)
            except Exception:
                logger.exception("Invalid schedule settings for %s; disabling schedule", job_type)
                with get_connection() as connection:
                    connection.execute(
                        "UPDATE collection_schedules SET enabled = 0, next_run_at = NULL, updated_at = ? WHERE id = ?",
                        (now_text, schedule["id"]),
                    )
                continue

            with get_connection() as connection:
                connection.execute(
                    """
                    UPDATE collection_schedules
                    SET last_run_at = ?, next_run_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now_text, next_run, now_text, schedule["id"]),
                )

        await asyncio.sleep(poll_seconds)


async def stop_scheduler_tasks() -> None:
    for task in list(_scheduler_tasks):
        task.cancel()
    if _scheduler_tasks:
        await asyncio.gather(*_scheduler_tasks, return_exceptions=True)
    _scheduler_tasks.clear()
