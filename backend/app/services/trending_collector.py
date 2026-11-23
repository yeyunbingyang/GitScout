"""GitHub Trending HTML collector and immutable snapshot persistence."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.database.connection import get_connection

logger = logging.getLogger(__name__)

PERIODS = {"daily", "weekly", "monthly"}
PERIOD_LABELS = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}
DEFAULT_TRENDING_URL = "https://github.com/trending"


class TrendingCollectionError(RuntimeError):
    """A collection or parsing failure that should be visible in the job history."""

    def __init__(self, message: str, attempts: int = 1):
        super().__init__(message)
        self.attempts = attempts


class ActiveTrendingJobError(RuntimeError):
    def __init__(self, job_id: str):
        super().__init__(f"A {job_id} job is already queued or running for this period.")
        self.job_id = job_id


@dataclass(frozen=True)
class TrendingRepository:
    rank: int
    full_name: str
    owner: str
    name: str
    description: str | None
    html_url: str
    language: str | None
    stars_count: int
    stars_delta: int
    forks_count: int
    topics: tuple[str, ...]


@dataclass(frozen=True)
class ParsedTrending:
    items: tuple[TrendingRepository, ...]
    duplicate_count: int
    skipped_count: int
    card_count: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_period(period_type: str) -> str:
    normalized = period_type.strip().lower()
    if normalized not in PERIODS:
        raise ValueError("period_type must be daily, weekly, or monthly")
    return normalized


def period_key(period_type: str, at: datetime | None = None) -> str:
    period_type = validate_period(period_type)
    value = at or datetime.now(timezone.utc)
    value = value.astimezone(timezone.utc)
    if period_type == "daily":
        return value.strftime("%Y-%m-%d")
    if period_type == "weekly":
        iso = value.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return value.strftime("%Y-%m")


def build_trending_url(period_type: str) -> str:
    period_type = validate_period(period_type)
    base_url = os.getenv("GITSCOUT_TRENDING_URL", DEFAULT_TRENDING_URL).strip().rstrip("/")
    return f"{base_url}?since={period_type}"


def parse_count(value: str | None) -> int:
    if not value:
        return 0
    normalized = value.strip().replace(",", "").replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)([kKmMbB]?)", normalized)
    if not match:
        return 0
    number = float(match.group(1))
    suffix = match.group(2).lower()
    multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(suffix, 1)
    return int(number * multiplier)


def _anchor_count(card: Any, suffixes: tuple[str, ...]) -> int:
    for anchor in card.select("a[href]"):
        href = anchor.get("href", "").rstrip("/")
        if any(href.endswith(suffix) for suffix in suffixes):
            count = parse_count(anchor.get_text(" ", strip=True))
            if count:
                return count
    return 0


def parse_trending_html(html: str, period_type: str) -> ParsedTrending:
    """Parse GitHub Trending repository cards without relying on fixed CSS hashes."""
    period_type = validate_period(period_type)
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("article.Box-row")
    if not cards:
        cards = soup.select("article")

    parsed: list[TrendingRepository] = []
    seen: set[str] = set()
    duplicate_count = 0
    skipped_count = 0

    for card in cards:
        heading_link = card.select_one("h2 a[href]")
        if heading_link is None:
            skipped_count += 1
            continue

        href = heading_link.get("href", "").strip()
        parts = [part for part in href.split("/") if part]
        if len(parts) < 2:
            skipped_count += 1
            continue

        owner, name = parts[0], parts[1]
        if owner.lower() in {"topics", "collections", "sponsors"}:
            skipped_count += 1
            continue

        full_name = f"{owner}/{name}"
        normalized_name = full_name.casefold()
        if normalized_name in seen:
            duplicate_count += 1
            continue
        seen.add(normalized_name)

        description_node = card.select_one("p")
        description = (
            description_node.get_text(" ", strip=True)
            if description_node is not None
            else None
        )
        language_node = card.select_one('[itemprop="programmingLanguage"]')
        language = (
            language_node.get_text(" ", strip=True)
            if language_node is not None
            else None
        )

        star_anchor = next(
            (
                anchor for anchor in card.select("a[href]")
                if anchor.get("href", "").rstrip("/").endswith("/stargazers")
            ),
            None,
        )
        if star_anchor is None:
            skipped_count += 1
            continue

        card_text = card.get_text(" ", strip=True)
        period_phrase = {
            "daily": r"stars?\s+today",
            "weekly": r"stars?\s+this\s+week",
            "monthly": r"stars?\s+this\s+month",
        }[period_type]
        delta_match = re.search(
            rf"(\d[\d,.]*\s*[kKmMbB]?)\s+{period_phrase}",
            card_text,
            flags=re.IGNORECASE,
        )
        stars_delta = parse_count(delta_match.group(1)) if delta_match else 0

        topics = tuple(
            dict.fromkeys(
                node.get_text(" ", strip=True)
                for node in card.select("a.topic-tag")
                if node.get_text(" ", strip=True)
            )
        )
        if not topics:
            topics = tuple(
                dict.fromkeys(
                    node.get_text(" ", strip=True)
                    for node in card.select('a[href*="/topics/"]')
                    if node.get_text(" ", strip=True)
                )
            )

        parsed.append(
            TrendingRepository(
                rank=len(parsed) + 1,
                full_name=full_name,
                owner=owner,
                name=name,
                description=description or None,
                html_url=f"https://github.com/{owner}/{name}",
                language=language or None,
                stars_count=parse_count(star_anchor.get_text(" ", strip=True)),
                stars_delta=stars_delta,
                forks_count=_anchor_count(card, ("/forks", "/network/members")),
                topics=topics,
            )
        )

    if not parsed:
        raise TrendingCollectionError(
            "No GitHub repository cards could be parsed. The page may have changed or returned a challenge page."
        )

    return ParsedTrending(
        items=tuple(parsed),
        duplicate_count=duplicate_count,
        skipped_count=skipped_count,
        card_count=len(cards),
    )


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.5), 8.0)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    return min(max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.5), 8.0)
                except (TypeError, ValueError, OverflowError):
                    pass
    return min(0.8 * (2 ** (attempt - 1)), 5.0)


async def fetch_trending_html(period_type: str) -> tuple[str, str, int]:
    """Fetch one Trending page, retrying transient network, rate-limit and server errors."""
    url = build_trending_url(period_type)
    headers = {
        "User-Agent": "GitScout/0.1.0 (local GitHub Trending research workspace)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    last_error: Exception | None = None

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(25.0, connect=10.0),
        follow_redirects=True,
        headers=headers,
    ) as client:
        for attempt in range(1, 4):
            response: httpx.Response | None = None
            try:
                response = await client.get(url)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        await asyncio.sleep(_retry_delay(response, attempt))
                        continue
                response.raise_for_status()
                return response.text, str(response.url), attempt
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError):
                    status = exc.response.status_code
                    if status < 500 and status != 429:
                        break
                if attempt < 3:
                    await asyncio.sleep(_retry_delay(response, attempt))
                    continue
                break

    detail = str(last_error) if last_error else "Unknown HTTP request failure"
    raise TrendingCollectionError(f"Failed to fetch GitHub Trending after retries: {detail}", attempts=attempt) from last_error


def create_trending_job(
    period_type: str,
    trigger_type: str = "manual",
    retry_count: int = 0,
    retry_of_job_id: str | None = None,
    schedule_id: int | None = None,
) -> dict[str, Any]:
    period_type = validate_period(period_type)
    if trigger_type not in {"manual", "scheduled", "startup"}:
        raise ValueError("Unsupported trigger_type")

    job_type = f"trending_{period_type}"
    job_id = uuid.uuid4().hex
    created_at = utc_now()

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        active = connection.execute(
            """
            SELECT id FROM collection_jobs
            WHERE job_type = ? AND status IN ('queued', 'running')
            ORDER BY created_at DESC LIMIT 1
            """,
            (job_type,),
        ).fetchone()
        if active:
            raise ActiveTrendingJobError(active["id"])

        connection.execute(
            """
            INSERT INTO collection_jobs (
                id, job_type, trigger_type, schedule_id, status, progress,
                retry_count, retry_of_job_id, created_at
            ) VALUES (?, ?, ?, ?, 'queued', 0, ?, ?, ?)
            """,
            (job_id, job_type, trigger_type, schedule_id, retry_count, retry_of_job_id, created_at),
        )
        connection.execute(
            """
            INSERT INTO collection_job_logs (job_id, level, message, details_json, created_at)
            VALUES (?, 'INFO', ?, ?, ?)
            """,
            (
                job_id,
                f"{PERIOD_LABELS[period_type]} Trending collection queued",
                json.dumps({"period_type": period_type, "trigger_type": trigger_type}),
                created_at,
            ),
        )

    return get_collection_job(job_id) or {"id": job_id, "status": "queued"}


def get_collection_job(job_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM collection_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["logs"] = [
            dict(log)
            for log in connection.execute(
                """
                SELECT id, level, message, details_json, created_at
                FROM collection_job_logs WHERE job_id = ? ORDER BY id ASC
                """,
                (job_id,),
            ).fetchall()
        ]
        return result


def list_collection_jobs(
    job_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    where = "WHERE job_type LIKE 'trending_%'"
    parameters: list[Any] = []
    if job_type:
        where += " AND job_type = ?"
        parameters.append(job_type)

    offset = (page - 1) * page_size
    with get_connection() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) AS count FROM collection_jobs {where}", parameters
        ).fetchone()["count"]
        rows = connection.execute(
            f"""
            SELECT id, job_type, trigger_type, status, progress, started_at, finished_at,
                   retry_count, request_count, fetched_count, inserted_count, updated_count,
                   deduplicated_count, error_code, error_message, related_snapshot_id, created_at
            FROM collection_jobs {where}
            ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            [*parameters, page_size, offset],
        ).fetchall()
    return {
        "items": [dict(row) for row in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


def _add_job_log(
    connection: sqlite3.Connection,
    job_id: str,
    level: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO collection_job_logs (job_id, level, message, details_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (job_id, level, message, json.dumps(details or {}, ensure_ascii=False), utc_now()),
    )


def _mark_job_failed(
    job_id: str,
    period_type: str,
    source_url: str,
    started_at: str,
    error: Exception,
    attempts: int,
) -> dict[str, Any]:
    finished_at = utc_now()
    message = str(error)[:1000]
    snapshot_id: int | None = None

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO trending_snapshots (
                period_type, period_key, collected_at, status, source_url, item_count, error_summary
            ) VALUES (?, ?, ?, 'failed', ?, 0, ?)
            """,
            (period_type, period_key(period_type), finished_at, source_url, message),
        )
        snapshot_id = int(cursor.lastrowid)
        connection.execute(
            """
            UPDATE collection_jobs
            SET status = 'failed', progress = 100, started_at = ?, finished_at = ?,
                request_count = ?, retry_count = MAX(retry_count, ?),
                error_code = 'TRENDING_COLLECTION_FAILED', error_message = ?,
                related_snapshot_id = ?
            WHERE id = ?
            """,
            (started_at, finished_at, attempts, max(attempts - 1, 0), message, snapshot_id, job_id),
        )
        _add_job_log(
            connection,
            job_id,
            "ERROR",
            "Trending collection failed; no successful ranking snapshot was created",
            {"period_type": period_type, "error": message, "attempts": attempts, "snapshot_id": snapshot_id},
        )

    logger.warning("Trending collection failed for %s: %s", period_type, message)
    return get_collection_job(job_id) or {"id": job_id, "status": "failed"}


def persist_trending_snapshot(
    job_id: str,
    period_type: str,
    parsed: ParsedTrending,
    source_url: str,
    started_at: str,
    attempts: int,
) -> dict[str, Any]:
    """Upsert repository metadata and persist a new immutable ranking snapshot atomically."""
    period_type = validate_period(period_type)
    collected_at = utc_now()
    snapshot_status = "partial_success" if parsed.skipped_count else "success"
    inserted_count = 0
    updated_count = 0

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO trending_snapshots (
                period_type, period_key, collected_at, status, source_url, item_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                period_type,
                period_key(period_type),
                collected_at,
                snapshot_status,
                source_url,
                len(parsed.items),
            ),
        )
        snapshot_id = int(cursor.lastrowid)

        for item in parsed.items:
            existing = connection.execute(
                "SELECT id FROM repositories WHERE full_name = ? COLLATE NOCASE",
                (item.full_name,),
            ).fetchone()

            connection.execute(
                """
                INSERT INTO repositories (
                    full_name, owner, name, description, html_url, language,
                    stars_count, forks_count, last_synced_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(full_name) DO UPDATE SET
                    owner = excluded.owner,
                    name = excluded.name,
                    description = excluded.description,
                    html_url = excluded.html_url,
                    language = excluded.language,
                    stars_count = excluded.stars_count,
                    forks_count = excluded.forks_count,
                    last_synced_at = excluded.last_synced_at,
                    updated_at = excluded.updated_at
                """,
                (
                    item.full_name,
                    item.owner,
                    item.name,
                    item.description,
                    item.html_url,
                    item.language,
                    item.stars_count,
                    item.forks_count,
                    collected_at,
                    collected_at,
                ),
            )
            repository = connection.execute(
                "SELECT id FROM repositories WHERE full_name = ? COLLATE NOCASE",
                (item.full_name,),
            ).fetchone()
            repository_id = int(repository["id"])

            if existing:
                updated_count += 1
            else:
                inserted_count += 1

            if item.topics:
                connection.execute(
                    "DELETE FROM repository_topics WHERE repository_id = ?",
                    (repository_id,),
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO repository_topics (repository_id, topic) VALUES (?, ?)",
                    [(repository_id, topic) for topic in item.topics],
                )

            connection.execute(
                """
                INSERT OR IGNORE INTO repository_stats (
                    repository_id, captured_at, source, stars_count, forks_count
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    repository_id,
                    collected_at,
                    f"trending_{period_type}",
                    item.stars_count,
                    item.forks_count,
                ),
            )

            connection.execute(
                """
                INSERT INTO trending_snapshot_items (
                    snapshot_id, repository_id, rank, stars_count, stars_delta, forks_count
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    repository_id,
                    item.rank,
                    item.stars_count,
                    item.stars_delta,
                    item.forks_count,
                ),
            )

        finished_at = utc_now()
        warning = None
        if parsed.skipped_count:
            warning = f"{parsed.skipped_count} malformed or non-repository cards were skipped."

        connection.execute(
            """
            UPDATE collection_jobs
            SET status = ?, progress = 100, started_at = ?, finished_at = ?,
                request_count = ?, fetched_count = ?, inserted_count = ?, updated_count = ?,
                deduplicated_count = ?, retry_count = MAX(retry_count, ?),
                error_message = ?, related_snapshot_id = ?
            WHERE id = ?
            """,
            (
                snapshot_status,
                started_at,
                finished_at,
                attempts,
                parsed.card_count,
                inserted_count,
                updated_count,
                parsed.duplicate_count,
                max(attempts - 1, 0),
                warning,
                snapshot_id,
                job_id,
            ),
        )
        _add_job_log(
            connection,
            job_id,
            "INFO" if snapshot_status == "success" else "WARNING",
            "Trending snapshot persisted",
            {
                "period_type": period_type,
                "snapshot_id": snapshot_id,
                "item_count": len(parsed.items),
                "inserted_count": inserted_count,
                "updated_count": updated_count,
                "duplicate_count": parsed.duplicate_count,
                "skipped_count": parsed.skipped_count,
                "attempts": attempts,
            },
        )

    return get_collection_job(job_id) or {
        "id": job_id,
        "status": snapshot_status,
        "related_snapshot_id": snapshot_id,
    }


async def execute_trending_job(job_id: str, period_type: str) -> dict[str, Any]:
    """Run a queued job; HTTP I/O occurs outside SQLite transactions."""
    period_type = validate_period(period_type)
    started_at = utc_now()
    source_url = build_trending_url(period_type)

    with get_connection() as connection:
        connection.execute(
            "UPDATE collection_jobs SET status = 'running', progress = 5, started_at = ? WHERE id = ?",
            (started_at, job_id),
        )
        _add_job_log(
            connection,
            job_id,
            "INFO",
            f"Fetching GitHub Trending {PERIOD_LABELS[period_type]} page",
            {"source_url": source_url},
        )

    attempts = 1
    try:
        html, source_url, attempts = await fetch_trending_html(period_type)
        with get_connection() as connection:
            connection.execute(
                "UPDATE collection_jobs SET progress = 55, request_count = 1 WHERE id = ?",
                (job_id,),
            )
        parsed = parse_trending_html(html, period_type)
        with get_connection() as connection:
            _add_job_log(
                connection,
                job_id,
                "INFO",
                "Trending HTML parsed",
                {
                    "card_count": parsed.card_count,
                    "parsed_count": len(parsed.items),
                    "duplicate_count": parsed.duplicate_count,
                    "skipped_count": parsed.skipped_count,
                },
            )
        return persist_trending_snapshot(
            job_id, period_type, parsed, source_url, started_at, attempts
        )
    except Exception as exc:
        if isinstance(exc, TrendingCollectionError):
            error = exc
            attempts = max(attempts, exc.attempts)
        else:
            error = TrendingCollectionError(f"{type(exc).__name__}: {exc}")
        return _mark_job_failed(job_id, period_type, source_url, started_at, error, attempts)


async def collect_trending_period(
    period_type: str,
    trigger_type: str = "manual",
) -> dict[str, Any]:
    """Convenience entry point for tests and non-background callers."""
    job = create_trending_job(period_type, trigger_type)
    return await execute_trending_job(job["id"], period_type)
