"""GitHub Search API Stars leaderboard collector with bounded, auditable sharding."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.database.connection import get_connection
from app.services.trending_collector import get_collection_job, utc_now

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.github.com/search/repositories"
PER_PAGE = 100
SEARCH_RESULT_LIMIT = 1_000
DEFAULT_MAX_RESULTS = 5_000
DEFAULT_MIN_STARS = 100
MAX_MAX_RESULTS = 10_000
MIN_REPOSITORY_CREATED = date(2008, 1, 1)
MAX_RATE_LIMIT_WAIT_SECONDS = 90


class ActiveStarsScanError(RuntimeError):
    def __init__(self, job_id: str):
        super().__init__("A Stars leaderboard scan is already queued or running.")
        self.job_id = job_id


class StarsCollectionError(RuntimeError):
    """An API or persistence failure that should remain visible in scan history."""


@dataclass
class SearchState:
    request_count: int = 0
    retry_count: int = 0
    incomplete_results: bool = False
    total_count: int = 0
    deduplicated_count: int = 0
    failed_shards: list[str] = field(default_factory=list)
    shard_count: int = 0
    cap_reached: bool = False


@dataclass
class StarsScanResult:
    repositories: list[dict[str, Any]]
    request_count: int
    retry_count: int
    total_count: int
    deduplicated_count: int
    incomplete_results: bool
    failed_shards: list[str]
    shard_count: int
    cap_reached: bool
    coverage_description: str


def validate_scan_options(max_results: int, min_stars: int) -> tuple[int, int]:
    if not 100 <= int(max_results) <= MAX_MAX_RESULTS:
        raise ValueError(f"max_results must be between 100 and {MAX_MAX_RESULTS}")
    if not 1 <= int(min_stars) <= 10_000_000:
        raise ValueError("min_stars must be between 1 and 10000000")
    return int(max_results), int(min_stars)


def _query(
    min_stars: int,
    max_stars: int | None = None,
    include_forks: bool = False,
    created_range: tuple[date, date] | None = None,
) -> str:
    star_filter = (
        f"stars:>={min_stars}"
        if max_stars is None
        else f"stars:{min_stars}..{max_stars}"
    )
    parts = ["is:public", star_filter]
    if include_forks:
        parts.append("fork:true")
    if created_range:
        parts.append(f"created:{created_range[0].isoformat()}..{created_range[1].isoformat()}")
    return " ".join(parts)


def _retry_after(response: httpx.Response, attempt: int) -> float:
    value = response.headers.get("Retry-After")
    if value:
        try:
            return max(0.5, float(value))
        except ValueError:
            pass

    if response.headers.get("X-RateLimit-Remaining") == "0":
        reset = response.headers.get("X-RateLimit-Reset")
        if reset:
            try:
                return max(1.0, float(reset) - time.time())
            except ValueError:
                pass

    return min(2 ** attempt, 8.0)


def _safe_api_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        message = payload.get("message") if isinstance(payload, dict) else None
    except ValueError:
        message = None
    if response.status_code in {403, 429} and (
        response.headers.get("X-RateLimit-Remaining") == "0"
        or "rate limit" in str(message).lower()
        or "secondary rate limit" in str(message).lower()
    ):
        if not os.getenv("GITHUB_TOKEN", "").strip():
            return (
                "GitHub Search API rate limit reached. Add a personal access token "
                "to the local .env file as GITHUB_TOKEN, then retry."
            )
        return "GitHub Search API rate limit reached. Wait for the reset window, then retry."
    return f"GitHub Search API returned HTTP {response.status_code}: {str(message or response.text)[:300]}"


async def _fetch_page(
    client: httpx.AsyncClient,
    query: str,
    page: int,
    state: SearchState,
) -> dict[str, Any]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    configured_interval = os.getenv("GITSCOUT_GITHUB_SEARCH_INTERVAL_SECONDS")
    interval = (
        max(0.0, float(configured_interval))
        if configured_interval is not None
        else (2.1 if token else 6.1)
    )
    last_request = getattr(state, "_last_request_at", None)
    if last_request is not None:
        wait = interval - (time.monotonic() - last_request)
        if wait > 0:
            await asyncio.sleep(wait)

    for attempt in range(1, 4):
        state.request_count += 1
        setattr(state, "_last_request_at", time.monotonic())
        try:
            response = await client.get(
                SEARCH_URL,
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": PER_PAGE,
                    "page": page,
                },
            )
            if response.status_code in {403, 429}:
                wait = _retry_after(response, attempt)
                if attempt < 3 and wait <= MAX_RATE_LIMIT_WAIT_SECONDS:
                    state.retry_count += 1
                    await asyncio.sleep(wait)
                    continue
                raise StarsCollectionError(_safe_api_error(response))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise StarsCollectionError("GitHub Search API returned an unexpected response shape.")
            state.incomplete_results = state.incomplete_results or bool(payload.get("incomplete_results"))
            return payload
        except httpx.HTTPStatusError as exc:
            response = exc.response
            if response.status_code >= 500 and attempt < 3:
                state.retry_count += 1
                await asyncio.sleep(min(2 ** attempt, 8.0))
                continue
            raise StarsCollectionError(_safe_api_error(response)) from exc
        except httpx.RequestError as exc:
            if attempt < 3:
                state.retry_count += 1
                await asyncio.sleep(min(2 ** attempt, 8.0))
                continue
            raise StarsCollectionError(f"GitHub Search API network error: {exc}") from exc
        except ValueError as exc:
            raise StarsCollectionError("GitHub Search API returned invalid JSON.") from exc

    raise StarsCollectionError("GitHub Search API request failed after retries.")


def _normalize_repository(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        github_repo_id = int(item["id"])
        full_name = str(item["full_name"]).strip()
        stars_count = int(item.get("stargazers_count") or 0)
    except (KeyError, TypeError, ValueError):
        return None

    owner_data = item.get("owner") or {}
    owner = str(owner_data.get("login") or full_name.split("/", 1)[0]).strip()
    name = str(item.get("name") or full_name.split("/", 1)[-1]).strip()
    if not full_name or "/" not in full_name or not owner or not name:
        return None

    license_data = item.get("license") or {}
    topics_value = item.get("topics")
    topics = (
        list(dict.fromkeys(str(topic).strip() for topic in topics_value if str(topic).strip()))
        if isinstance(topics_value, list)
        else None
    )
    return {
        "github_repo_id": github_repo_id,
        "full_name": full_name,
        "owner": owner,
        "name": name,
        "description": item.get("description"),
        "html_url": item.get("html_url") or f"https://github.com/{full_name}",
        "language": item.get("language"),
        "stars_count": max(0, stars_count),
        "forks_count": max(0, int(item.get("forks_count") or 0)),
        "open_issues_count": max(0, int(item.get("open_issues_count") or 0)),
        "github_created_at": item.get("created_at"),
        "github_updated_at": item.get("updated_at"),
        "pushed_at": item.get("pushed_at"),
        "license_spdx_id": license_data.get("spdx_id"),
        "topics": topics,
    }


def create_stars_scan_job(
    trigger_type: str = "manual",
    max_results: int = DEFAULT_MAX_RESULTS,
    min_stars: int = DEFAULT_MIN_STARS,
    include_forks: bool = False,
    retry_count: int = 0,
    retry_of_job_id: str | None = None,
    schedule_id: int | None = None,
) -> dict[str, Any]:
    max_results, min_stars = validate_scan_options(max_results, min_stars)
    if trigger_type not in {"manual", "scheduled", "startup"}:
        raise ValueError("Unsupported trigger_type")

    job_id = uuid.uuid4().hex
    created_at = utc_now()
    query_plan = {
        "max_results": max_results,
        "min_stars": min_stars,
        "include_forks": bool(include_forks),
        "sort": "stars_desc",
        "scope": "public",
        "per_page": PER_PAGE,
        "search_result_limit": SEARCH_RESULT_LIMIT,
    }

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        active = connection.execute(
            """
            SELECT id FROM collection_jobs
            WHERE job_type = 'stars_scan' AND status IN ('queued', 'running')
            ORDER BY created_at DESC LIMIT 1
            """
        ).fetchone()
        if active:
            raise ActiveStarsScanError(active["id"])

        cursor = connection.execute(
            """
            INSERT INTO stars_scans (
                trigger_type, started_at, status, query_plan, coverage_description
            ) VALUES (?, ?, 'queued', ?, ?)
            """,
            (
                trigger_type,
                created_at,
                json.dumps(query_plan, ensure_ascii=False),
                f"待采集：公开仓库，Stars ≥ {min_stars}，目标 Top {max_results}。",
            ),
        )
        scan_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO collection_jobs (
                id, job_type, trigger_type, schedule_id, status, progress,
                retry_count, retry_of_job_id, related_stars_scan_id, created_at
            ) VALUES (?, 'stars_scan', ?, ?, 'queued', 0, ?, ?, ?, ?)
            """,
            (job_id, trigger_type, schedule_id, retry_count, retry_of_job_id, scan_id, created_at),
        )
        connection.execute(
            """
            INSERT INTO collection_job_logs (job_id, level, message, details_json, created_at)
            VALUES (?, 'INFO', ?, ?, ?)
            """,
            (
                job_id,
                "GitHub Stars leaderboard scan queued",
                json.dumps({"scan_id": scan_id, **query_plan}, ensure_ascii=False),
                created_at,
            ),
        )

    job = get_collection_job(job_id) or {"id": job_id, "status": "queued"}
    job["scan_id"] = scan_id
    return job


def _create_shard(scan_id: int, shard_key: str, query_text: str) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO stars_scan_shards (
                scan_id, shard_key, query_text, status, started_at
            ) VALUES (?, ?, ?, 'running', ?)
            """,
            (scan_id, shard_key, query_text, utc_now()),
        )
        return int(cursor.lastrowid)


def _finish_shard(
    shard_id: int,
    status: str,
    total_count: int,
    fetched_count: int,
    incomplete_results: bool,
    error_message: str | None = None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE stars_scan_shards
            SET status = ?, total_count = ?, fetched_count = ?, incomplete_results = ?,
                finished_at = ?, error_message = ?
            WHERE id = ?
            """,
            (
                status,
                total_count,
                fetched_count,
                1 if incomplete_results else 0,
                utc_now(),
                error_message,
                shard_id,
            ),
        )


def _add_log(job_id: str, level: str, message: str, details: dict[str, Any] | None = None) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO collection_job_logs (job_id, level, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, level, message, json.dumps(details or {}, ensure_ascii=False), utc_now()),
        )


async def collect_stars_repositories(
    scan_id: int,
    job_id: str,
    max_results: int,
    min_stars: int,
    include_forks: bool = False,
) -> StarsScanResult:
    """Collect the highest-starred public repositories up to the configured top-N cap.

    Search API queries are recursively partitioned into non-overlapping star ranges.
    A same-star bucket that still exceeds the API's 1,000-result window is partitioned
    by repository creation dates. Results are always sorted by stars before persistence.
    """
    max_results, min_stars = validate_scan_options(max_results, min_stars)
    state = SearchState()
    repositories_by_id: dict[int, dict[str, Any]] = {}
    coverage_total = 0
    last_query_progress = 0

    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "GitScout/0.3.0 (local GitHub project discovery workspace)",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async def update_progress() -> None:
        progress = min(95, 5 + int(len(repositories_by_id) / max_results * 85))
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE collection_jobs
                SET progress = ?, request_count = ?, fetched_count = ?, deduplicated_count = ?
                WHERE id = ?
                """,
                (
                    progress,
                    state.request_count,
                    len(repositories_by_id),
                    state.deduplicated_count,
                    job_id,
                ),
            )

    async def consume_pages(
        client: httpx.AsyncClient,
        query_text: str,
        first_payload: dict[str, Any],
        shard_id: int,
        total_count: int,
    ) -> None:
        remaining = max_results - len(repositories_by_id)
        target_count = min(total_count, remaining)
        fetched = 0
        shard_incomplete = bool(first_payload.get("incomplete_results"))
        page_count = max(1, math.ceil(target_count / PER_PAGE))
        page_error: str | None = None
        for page in range(1, page_count + 1):
            try:
                payload = first_payload if page == 1 else await _fetch_page(client, query_text, page, state)
            except Exception as exc:
                page_error = str(exc)[:800]
                break
            page_incomplete = bool(payload.get("incomplete_results"))
            shard_incomplete = shard_incomplete or page_incomplete
            state.incomplete_results = state.incomplete_results or page_incomplete
            page_items = payload.get("items") or []
            for raw_item in page_items:
                if len(repositories_by_id) >= max_results:
                    state.cap_reached = True
                    break
                normalized = _normalize_repository(raw_item)
                if normalized is None:
                    continue
                repo_id = normalized["github_repo_id"]
                if repo_id in repositories_by_id:
                    state.deduplicated_count += 1
                    continue
                repositories_by_id[repo_id] = normalized
                fetched += 1
            await update_progress()
            if len(repositories_by_id) >= max_results:
                if total_count > fetched:
                    state.cap_reached = True
                break
        if fetched < target_count and page_error is None:
            shard_incomplete = True
            state.incomplete_results = True
        if page_error:
            state.failed_shards.append(shard_key)
            _add_log(job_id, "ERROR", "Stars shard pagination failed", {"query": query_text, "error": page_error})
        shard_status = (
            "failed" if page_error and fetched == 0
            else "partial_success" if page_error or shard_incomplete or fetched < total_count
            else "success"
        )
        _finish_shard(
            shard_id,
            shard_status,
            total_count,
            fetched,
            shard_incomplete,
            page_error or (
                "The configured top-N limit was reached before this shard was fully enumerated."
                if state.cap_reached and fetched < total_count
                else None
            ),
        )

    async def process_query(
        client: httpx.AsyncClient,
        query_text: str,
        shard_key: str,
        star_low: int,
        star_high: int,
        created_start: date | None = None,
        created_end: date | None = None,
    ) -> None:
        nonlocal coverage_total
        if len(repositories_by_id) >= max_results:
            return

        shard_id = _create_shard(scan_id, shard_key, query_text)
        state.shard_count += 1
        try:
            payload = await _fetch_page(client, query_text, 1, state)
        except Exception as exc:
            await update_progress()
            message = str(exc)[:800]
            _finish_shard(shard_id, "failed", 0, 0, False, message)
            state.failed_shards.append(shard_key)
            _add_log(job_id, "ERROR", f"Stars shard failed: {shard_key}", {"query": query_text, "error": message})
            return

        total_count = max(0, int(payload.get("total_count") or 0))
        await update_progress()
        incomplete = bool(payload.get("incomplete_results"))
        state.incomplete_results = state.incomplete_results or incomplete
        remaining = max_results - len(repositories_by_id)

        if total_count > SEARCH_RESULT_LIMIT and remaining > SEARCH_RESULT_LIMIT:
            _finish_shard(
                shard_id,
                "success",
                total_count,
                0,
                incomplete,
                "Probe shard partitioned into smaller non-overlapping queries.",
            )
            if star_low < star_high:
                midpoint = (star_low + star_high) // 2
                await process_query(
                    client,
                    _query(midpoint + 1, star_high, include_forks),
                    f"stars-{midpoint + 1}-{star_high}",
                    midpoint + 1,
                    star_high,
                )
                await process_query(
                    client,
                    _query(star_low, midpoint, include_forks),
                    f"stars-{star_low}-{midpoint}",
                    star_low,
                    midpoint,
                )
                return

            if created_start is None or created_end is None:
                await process_date_range(
                    client,
                    star_low,
                    star_high,
                    MIN_REPOSITORY_CREATED,
                    datetime.now(timezone.utc).date(),
                    include_forks,
                )
                return
            elif created_start < created_end:
                midpoint_date = created_start + (created_end - created_start) // 2
                await process_query(
                    client,
                    _query(star_low, star_high, include_forks, (midpoint_date + timedelta(days=1), created_end)),
                    f"stars-{star_low}-created-{(midpoint_date + timedelta(days=1)).isoformat()}-{created_end.isoformat()}",
                    star_low,
                    star_high,
                    midpoint_date + timedelta(days=1),
                    created_end,
                )
                await process_query(
                    client,
                    _query(star_low, star_high, include_forks, (created_start, midpoint_date)),
                    f"stars-{star_low}-created-{created_start.isoformat()}-{midpoint_date.isoformat()}",
                    star_low,
                    star_high,
                    created_start,
                    midpoint_date,
                )
                return

            message = (
                f"More than {SEARCH_RESULT_LIMIT} repositories share {star_low} stars "
                "on the same creation date; this Search API shard cannot be split further."
            )
            _finish_shard(shard_id, "failed", total_count, 0, True, message)
            state.failed_shards.append(shard_key)
            state.incomplete_results = True
            _add_log(job_id, "WARNING", "Stars shard could not be subdivided further", {"shard": shard_key, "error": message})
            return

        coverage_total += total_count
        await consume_pages(client, query_text, payload, shard_id, total_count)
        _add_log(
            job_id,
            "INFO",
            f"Stars shard completed: {shard_key}",
            {
                "query": query_text,
                "total_count": total_count,
                "fetched_count": min(total_count, max_results),
                "incomplete_results": incomplete,
            },
        )

    async def process_date_range(
        client: httpx.AsyncClient,
        stars: int,
        unused_high: int,
        start: date,
        end: date,
        forks: bool,
    ) -> None:
        if len(repositories_by_id) >= max_results:
            return
        await process_query(
            client,
            _query(stars, stars, forks, (start, end)),
            f"stars-{stars}-created-{start.isoformat()}-{end.isoformat()}",
            stars,
            stars,
            start,
            end,
        )

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        headers=headers,
    ) as client:
        root_query = _query(min_stars, None, include_forks)
        root_id = _create_shard(scan_id, "root", root_query)
        state.shard_count += 1
        try:
            root_payload = await _fetch_page(client, root_query, 1, state)
        except Exception as exc:
            await update_progress()
            message = str(exc)[:800]
            _finish_shard(root_id, "failed", 0, 0, False, message)
            state.failed_shards.append("root")
            raise StarsCollectionError(message) from exc

        root_total = max(0, int(root_payload.get("total_count") or 0))
        await update_progress()
        root_incomplete = bool(root_payload.get("incomplete_results"))
        state.incomplete_results = state.incomplete_results or root_incomplete
        first_items = root_payload.get("items") or []
        max_stars = max(
            (int(item.get("stargazers_count") or 0) for item in first_items),
            default=min_stars,
        )
        remaining = max_results

        if root_total > SEARCH_RESULT_LIMIT and remaining > SEARCH_RESULT_LIMIT:
            _finish_shard(
                root_id,
                "success",
                root_total,
                0,
                root_incomplete,
                "Root query partitioned into non-overlapping Stars ranges.",
            )
            if max_stars > min_stars:
                midpoint = (min_stars + max_stars) // 2
                await process_query(
                    client,
                    _query(midpoint + 1, max_stars, include_forks),
                    f"stars-{midpoint + 1}-{max_stars}",
                    midpoint + 1,
                    max_stars,
                )
                await process_query(
                    client,
                    _query(min_stars, midpoint, include_forks),
                    f"stars-{min_stars}-{midpoint}",
                    min_stars,
                    midpoint,
                )
            else:
                await process_date_range(
                    client,
                    min_stars,
                    min_stars,
                    MIN_REPOSITORY_CREATED,
                    datetime.now(timezone.utc).date(),
                    include_forks,
                )
        else:
            coverage_total += root_total
            await consume_pages(client, root_query, root_payload, root_id, root_total)

    repositories = sorted(
        repositories_by_id.values(),
        key=lambda item: (-item["stars_count"], item["full_name"].casefold()),
    )
    if len(repositories) > max_results:
        repositories = repositories[:max_results]

    coverage_description = (
        f"Top {len(repositories)} public repositories with at least {min_stars} stars"
        + (" (forks included)." if include_forks else " (forks excluded by GitHub's default search behavior).")
        + " This is a bounded leaderboard, not a complete inventory of every GitHub repository."
    )
    if state.failed_shards:
        coverage_description += f" {len(state.failed_shards)} shard(s) failed."
    if state.incomplete_results:
        coverage_description += " GitHub marked one or more search responses incomplete."
    if state.cap_reached:
        coverage_description += f" The configured Top {max_results} result cap was reached."

    return StarsScanResult(
        repositories=repositories,
        request_count=state.request_count,
        retry_count=state.retry_count,
        total_count=coverage_total,
        deduplicated_count=state.deduplicated_count,
        incomplete_results=state.incomplete_results,
        failed_shards=state.failed_shards,
        shard_count=state.shard_count,
        cap_reached=state.cap_reached,
        coverage_description=coverage_description,
    )


def _upsert_repository(connection: Any, item: dict[str, Any], captured_at: str) -> tuple[int, bool]:
    github_repo_id = item["github_repo_id"]
    full_name = item["full_name"]
    by_id = connection.execute(
        "SELECT id, full_name FROM repositories WHERE github_repo_id = ?",
        (github_repo_id,),
    ).fetchone()
    by_name = connection.execute(
        "SELECT id, full_name FROM repositories WHERE full_name = ? COLLATE NOCASE",
        (full_name,),
    ).fetchone()

    existing = by_id or by_name
    inserted = existing is None
    if existing:
        repository_id = int(existing["id"])
        current_name = str(existing["full_name"])
        name_collision = by_id is not None and by_name is not None and int(by_id["id"]) != int(by_name["id"])
        persisted_name = current_name if name_collision else full_name
        persisted_owner = current_name.split("/", 1)[0] if name_collision else item["owner"]
        persisted_repo_name = current_name.split("/", 1)[-1] if name_collision else item["name"]
        connection.execute(
            """
            UPDATE repositories SET
                github_repo_id = ?, full_name = ?, owner = ?, name = ?,
                description = ?, html_url = ?, language = ?, license_spdx_id = ?,
                stars_count = ?, forks_count = ?, open_issues_count = ?,
                github_created_at = ?, github_updated_at = ?, pushed_at = ?,
                last_synced_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                github_repo_id,
                persisted_name,
                persisted_owner,
                persisted_repo_name,
                item["description"],
                item["html_url"],
                item["language"],
                item["license_spdx_id"],
                item["stars_count"],
                item["forks_count"],
                item["open_issues_count"],
                item["github_created_at"],
                item["github_updated_at"],
                item["pushed_at"],
                captured_at,
                captured_at,
                repository_id,
            ),
        )
    else:
        cursor = connection.execute(
            """
            INSERT INTO repositories (
                github_repo_id, full_name, owner, name, description, html_url, language,
                license_spdx_id, stars_count, forks_count, open_issues_count,
                github_created_at, github_updated_at, pushed_at, last_synced_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                github_repo_id,
                full_name,
                item["owner"],
                item["name"],
                item["description"],
                item["html_url"],
                item["language"],
                item["license_spdx_id"],
                item["stars_count"],
                item["forks_count"],
                item["open_issues_count"],
                item["github_created_at"],
                item["github_updated_at"],
                item["pushed_at"],
                captured_at,
                captured_at,
            ),
        )
        repository_id = int(cursor.lastrowid)

    if item["topics"] is not None:
        connection.execute("DELETE FROM repository_topics WHERE repository_id = ?", (repository_id,))
        connection.executemany(
            "INSERT OR IGNORE INTO repository_topics (repository_id, topic) VALUES (?, ?)",
            [(repository_id, topic) for topic in item["topics"]],
        )

    connection.execute(
        """
        INSERT OR IGNORE INTO repository_stats (
            repository_id, captured_at, source, stars_count, forks_count, open_issues_count
        ) VALUES (?, ?, 'stars_scan', ?, ?, ?)
        """,
        (
            repository_id,
            captured_at,
            item["stars_count"],
            item["forks_count"],
            item["open_issues_count"],
        ),
    )
    return repository_id, inserted


def persist_stars_scan(
    job_id: str,
    scan_id: int,
    result: StarsScanResult,
) -> dict[str, Any]:
    captured_at = utc_now()
    inserted_count = 0
    updated_count = 0
    final_status = (
        "failed"
        if not result.repositories and (result.failed_shards or result.incomplete_results)
        else "partial_success"
        if result.failed_shards or result.incomplete_results
        else "success"
    )

    with get_connection() as connection:
        for rank, item in enumerate(result.repositories, start=1):
            repository_id, inserted = _upsert_repository(connection, item, captured_at)
            inserted_count += int(inserted)
            updated_count += int(not inserted)
            connection.execute(
                """
                INSERT INTO stars_scan_items (
                    scan_id, repository_id, rank, stars_count, forks_count, language
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    repository_id,
                    rank,
                    item["stars_count"],
                    item["forks_count"],
                    item["language"],
                ),
            )

        finished_at = utc_now()
        connection.execute(
            """
            UPDATE stars_scans SET
                finished_at = ?, status = ?, incomplete_results = ?,
                total_count = ?, fetched_count = ?, deduplicated_count = ?,
                coverage_description = ?, error_summary = ?
            WHERE id = ?
            """,
            (
                finished_at,
                final_status,
                1 if result.incomplete_results else 0,
                result.total_count,
                len(result.repositories),
                result.deduplicated_count,
                result.coverage_description,
                "; ".join(result.failed_shards)[:1000] if result.failed_shards else None,
                scan_id,
            ),
        )
        error_message = (
            f"{len(result.failed_shards)} shard(s) failed; see scan details."
            if result.failed_shards
            else "GitHub marked one or more Search API responses incomplete."
            if result.incomplete_results
            else None
        )
        connection.execute(
            """
            UPDATE collection_jobs SET
                status = ?, progress = 100, finished_at = ?,
                request_count = ?, fetched_count = ?, inserted_count = ?, updated_count = ?,
                deduplicated_count = ?, retry_count = MAX(retry_count, ?),
                error_code = ?, error_message = ?, related_stars_scan_id = ?
            WHERE id = ?
            """,
            (
                final_status,
                finished_at,
                result.request_count,
                len(result.repositories),
                inserted_count,
                updated_count,
                result.deduplicated_count,
                result.retry_count,
                "STARS_SCAN_FAILED" if final_status == "failed" else "STARS_SCAN_PARTIAL" if final_status == "partial_success" else None,
                error_message,
                scan_id,
                job_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO collection_job_logs (job_id, level, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                job_id,
                "INFO" if final_status == "success" else "WARNING" if final_status == "partial_success" else "ERROR",
                "GitHub Stars scan persisted",
                json.dumps(
                    {
                        "scan_id": scan_id,
                        "status": final_status,
                        "fetched_count": len(result.repositories),
                        "request_count": result.request_count,
                        "shard_count": result.shard_count,
                        "failed_shards": result.failed_shards,
                        "coverage": result.coverage_description,
                    },
                    ensure_ascii=False,
                ),
                finished_at,
            ),
        )

    return get_collection_job(job_id) or {"id": job_id, "status": final_status, "related_stars_scan_id": scan_id}


async def execute_stars_scan(
    job_id: str,
    scan_id: int,
    max_results: int = DEFAULT_MAX_RESULTS,
    min_stars: int = DEFAULT_MIN_STARS,
    include_forks: bool = False,
) -> dict[str, Any]:
    """Execute one Stars scan and persist its audit trail and immutable ranking."""
    started_at = utc_now()
    with get_connection() as connection:
        connection.execute(
            "UPDATE collection_jobs SET status = 'running', progress = 2, started_at = ? WHERE id = ?",
            (started_at, job_id),
        )
        connection.execute(
            "UPDATE stars_scans SET status = 'running', started_at = ? WHERE id = ?",
            (started_at, scan_id),
        )
        connection.execute(
            """
            INSERT INTO collection_job_logs (job_id, level, message, details_json, created_at)
            VALUES (?, 'INFO', 'GitHub Search API Stars scan started', ?, ?)
            """,
            (
                job_id,
                json.dumps({"scan_id": scan_id, "max_results": max_results, "min_stars": min_stars}),
                started_at,
            ),
        )

    try:
        result = await collect_stars_repositories(
            scan_id,
            job_id,
            max_results,
            min_stars,
            include_forks,
        )
        return persist_stars_scan(job_id, scan_id, result)
    except Exception as exc:
        message = str(exc)[:1000]
        finished_at = utc_now()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE stars_scans SET status = 'failed', finished_at = ?,
                    error_summary = ?, coverage_description = ?
                WHERE id = ?
                """,
                (finished_at, message, "采集失败，未生成可用的 Stars 排名快照。", scan_id),
            )
            connection.execute(
                """
                UPDATE collection_jobs SET status = 'failed', progress = 100,
                    finished_at = ?, error_code = 'STARS_SCAN_FAILED',
                    error_message = ?, related_stars_scan_id = ?
                WHERE id = ?
                """,
                (finished_at, message, scan_id, job_id),
            )
            connection.execute(
                """
                INSERT INTO collection_job_logs (job_id, level, message, details_json, created_at)
                VALUES (?, 'ERROR', 'GitHub Stars scan failed', ?, ?)
                """,
                (job_id, json.dumps({"scan_id": scan_id, "error": message}), finished_at),
            )
        logger.warning("GitHub Stars scan %s failed: %s", scan_id, message)
        return get_collection_job(job_id) or {"id": job_id, "status": "failed"}


def list_stars_scans(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        total = connection.execute("SELECT COUNT(*) AS count FROM stars_scans").fetchone()["count"]
        rows = connection.execute(
            """
            SELECT id, trigger_type, started_at, finished_at, status, incomplete_results,
                   total_count, fetched_count, deduplicated_count, coverage_description,
                   error_summary, query_plan
            FROM stars_scans ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["query_plan"] = json.loads(item["query_plan"] or "{}")
        except json.JSONDecodeError:
            item["query_plan"] = {}
        item["incomplete_results"] = bool(item["incomplete_results"])
        items.append(item)
    return {
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


def get_stars_scan(scan_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM stars_scans WHERE id = ?", (scan_id,)).fetchone()
        if row is None:
            return None
        scan = dict(row)
        try:
            scan["query_plan"] = json.loads(scan["query_plan"] or "{}")
        except json.JSONDecodeError:
            scan["query_plan"] = {}
        scan["incomplete_results"] = bool(scan["incomplete_results"])
        scan["shards"] = [
            dict(shard)
            for shard in connection.execute(
                """
                SELECT id, shard_key, query_text, status, total_count, fetched_count,
                       incomplete_results, started_at, finished_at, error_message
                FROM stars_scan_shards WHERE scan_id = ? ORDER BY id ASC
                """,
                (scan_id,),
            ).fetchall()
        ]
        return scan


def list_stars_leaderboard(
    scan_id: int | None = None,
    q: str | None = None,
    language: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    with get_connection() as connection:
        if scan_id is None:
            scan_row = connection.execute(
                """
                SELECT * FROM stars_scans
                WHERE status IN ('success', 'partial_success')
                ORDER BY finished_at DESC, id DESC LIMIT 1
                """
            ).fetchone()
        else:
            scan_row = connection.execute(
                """
                SELECT * FROM stars_scans
                WHERE id = ? AND status IN ('success', 'partial_success')
                """,
                (scan_id,),
            ).fetchone()

        if scan_row is None:
            return {
                "scan": None,
                "items": [],
                "pagination": {"page": page, "page_size": page_size, "total": 0, "total_pages": 0},
            }

        scan = dict(scan_row)
        try:
            scan["query_plan"] = json.loads(scan["query_plan"] or "{}")
        except json.JSONDecodeError:
            scan["query_plan"] = {}
        scan["incomplete_results"] = bool(scan["incomplete_results"])

        conditions = ["i.scan_id = ?"]
        parameters: list[Any] = [scan["id"]]
        if q:
            conditions.append("(r.full_name LIKE ? OR r.description LIKE ?)")
            keyword = f"%{q.strip()}%"
            parameters.extend([keyword, keyword])
        if language:
            conditions.append("r.language = ? COLLATE NOCASE")
            parameters.append(language.strip())

        where_clause = "WHERE " + " AND ".join(conditions)
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS count FROM stars_scan_items i
            JOIN repositories r ON r.id = i.repository_id
            {where_clause}
            """,
            parameters,
        ).fetchone()["count"]
        rows = connection.execute(
            f"""
            SELECT i.rank, i.stars_count, i.forks_count, i.language,
                   r.id AS repository_id, r.github_repo_id, r.full_name, r.owner, r.name,
                   r.description, r.html_url,
                   GROUP_CONCAT(DISTINCT t.topic) AS topics
            FROM stars_scan_items i
            JOIN repositories r ON r.id = i.repository_id
            LEFT JOIN repository_topics t ON t.repository_id = r.id
            {where_clause}
            GROUP BY i.id, r.id
            ORDER BY i.rank ASC
            LIMIT ? OFFSET ?
            """,
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()

    items = []
    for row in rows:
        item = dict(row)
        item["topics"] = [value for value in (item.pop("topics") or "").split(",") if value]
        items.append(item)
    return {
        "scan": scan,
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


def retry_stars_scan_job(original_job_id: str) -> dict[str, Any]:
    original = get_collection_job(original_job_id)
    if original is None or original.get("job_type") != "stars_scan":
        raise ValueError("Stars scan job not found")
    if original["status"] not in {"failed", "partial_success", "interrupted"}:
        raise ValueError("Only failed, partial-success or interrupted Stars scans can be retried.")

    scan = get_stars_scan(int(original["related_stars_scan_id"]))
    if scan is None:
        raise ValueError("Original Stars scan details are unavailable.")
    plan = scan.get("query_plan") or {}
    return create_stars_scan_job(
        trigger_type="manual",
        max_results=int(plan.get("max_results", DEFAULT_MAX_RESULTS)),
        min_stars=int(plan.get("min_stars", DEFAULT_MIN_STARS)),
        include_forks=bool(plan.get("include_forks", False)),
        retry_count=int(original.get("retry_count", 0)) + 1,
        retry_of_job_id=original_job_id,
    )
