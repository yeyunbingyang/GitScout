"""Deterministic, auditable recommendation scoring over local GitScout snapshots."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database.connection import get_connection

ALGORITHM_VERSION = "1.0.0"
WINDOW_DEFAULTS: dict[str, dict[str, int]] = {
    "daily": {"limit": 30, "minimum": 10},
    "weekly": {"limit": 12, "minimum": 4},
    "monthly": {"limit": 12, "minimum": 3},
}
STARS_STALE_AFTER_DAYS = 7
CATEGORY_THRESHOLDS = {
    "priority_min_score": 85.0,
    "emerging_daily_min": 60.0,
    "emerging_stars_max": 70.0,
    "stable_weekly_min": 60.0,
    "stable_monthly_min": 60.0,
}
PERIOD_LABELS = {"daily": "日榜", "weekly": "周榜", "monthly": "月榜"}
DIMENSION_LABELS = {
    "stars": "Stars",
    "daily": "日榜",
    "weekly": "周榜",
    "monthly": "月榜",
}
GRADE_LABELS = {
    "priority": "优先研究",
    "strong": "强烈推荐",
    "watch": "值得关注",
    "observe": "观察",
    "low": "低优先级",
}
CATEGORY_LABELS = {
    "all": "全部推荐",
    "priority": "优先关注",
    "emerging": "新兴潜力",
    "stable": "长期稳定",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _age_days(value: str | None, now: datetime) -> int | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds() // 86400))


def _json_load(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _weights(profile: sqlite3.Row) -> dict[str, float]:
    return {
        "stars": float(profile["stars_weight"]),
        "daily": float(profile["daily_weight"]),
        "weekly": float(profile["weekly_weight"]),
        "monthly": float(profile["monthly_weight"]),
    }


def _profile_dict(row: sqlite3.Row) -> dict[str, Any]:
    weights = _weights(row)
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "is_default": bool(row["is_default"]),
        "weights": weights,
        "weights_percent": {key: round(value * 100) for key, value in weights.items()},
        "created_at": row["created_at"],
    }


def list_recommendation_profiles() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, description, stars_weight, daily_weight,
                   weekly_weight, monthly_weight, is_default, created_at
            FROM recommendation_profiles
            ORDER BY is_default DESC, id ASC
            """
        ).fetchall()
    return [_profile_dict(row) for row in rows]


def _grade(score: float) -> str:
    if score >= 85:
        return "priority"
    if score >= 75:
        return "strong"
    if score >= 65:
        return "watch"
    if score >= 50:
        return "observe"
    return "low"


def _category_matches(
    category: str,
    item: dict[str, Any],
    thresholds: dict[str, float],
) -> bool:
    if category == "all":
        return True
    if category == "priority":
        return item["total_score"] >= thresholds["priority_min_score"]
    if category == "emerging":
        daily = item["daily_score"]
        stars = item["stars_score"]
        return (
            daily is not None
            and stars is not None
            and daily >= thresholds["emerging_daily_min"]
            and stars <= thresholds["emerging_stars_max"]
        )
    if category == "stable":
        weekly = item["weekly_score"]
        monthly = item["monthly_score"]
        return (
            weekly is not None
            and monthly is not None
            and weekly >= thresholds["stable_weekly_min"]
            and monthly >= thresholds["stable_monthly_min"]
        )
    return False


def _reason_text(code: str, coverage: dict[str, Any]) -> str:
    if code == "stars":
        stars = coverage.get("stars", {})
        return (
            f"Stars 排名第 {stars.get('rank', '—')} / "
            f"{stars.get('candidate_count', 0)}"
        )
    period = coverage.get("periods", {}).get(code, {})
    label = PERIOD_LABELS.get(code, code)
    return (
        f"{label}出现 {period.get('appearance_count', 0)} / "
        f"{period.get('sample_count', 0)} 次"
    )


def _item_from_row(row: sqlite3.Row, thresholds: dict[str, float]) -> dict[str, Any]:
    coverage = _json_load(row["sample_coverage_json"], {})
    reason_codes = _json_load(row["reasons_json"], [])
    total_score = float(row["total_score"])
    item = {
        "repository_id": int(row["repository_id"]),
        "github_repo_id": row["github_repo_id"],
        "full_name": row["full_name"],
        "owner": row["owner"],
        "name": row["name"],
        "description": row["description"],
        "html_url": row["html_url"],
        "language": row["language"],
        "stars_count": int(row["stars_count"]),
        "forks_count": int(row["forks_count"]),
        "last_synced_at": row["last_synced_at"],
        "stars_score": row["stars_score"],
        "daily_score": row["daily_score"],
        "weekly_score": row["weekly_score"],
        "monthly_score": row["monthly_score"],
        "total_score": total_score,
        "rank": int(row["rank"]),
        "grade": _grade(total_score),
        "grade_label": GRADE_LABELS[_grade(total_score)],
        "reason_codes": reason_codes,
        "reasons": [_reason_text(code, coverage) for code in reason_codes],
        "coverage": coverage,
        "stars_rank": coverage.get("stars", {}).get("rank"),
        "interested": row["interested_at"] is not None,
        "research_status": row["research_status"],
    }
    item["categories"] = [
        name
        for name in ("priority", "emerging", "stable")
        if _category_matches(name, item, thresholds)
    ]
    return item


def _read_run_context(connection: sqlite3.Connection) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    latest_scan_row = connection.execute(
        """
        SELECT id, trigger_type, started_at, finished_at, status, incomplete_results,
               total_count, fetched_count, deduplicated_count, coverage_description,
               error_summary
        FROM stars_scans
        ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    latest_successful_scan = connection.execute(
        """
        SELECT id, trigger_type, started_at, finished_at, status, incomplete_results,
               total_count, fetched_count, deduplicated_count, coverage_description
        FROM stars_scans
        WHERE status = 'success'
        ORDER BY finished_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()

    latest_scan = dict(latest_scan_row) if latest_scan_row else None
    scoring_scan = dict(latest_successful_scan) if latest_successful_scan else None
    scoring_scan_id = int(scoring_scan["id"]) if scoring_scan else None

    candidate_ids: set[int] = set()
    if scoring_scan_id is not None:
        candidate_ids.update(
            int(row["repository_id"])
            for row in connection.execute(
                "SELECT repository_id FROM stars_scan_items WHERE scan_id = ?",
                (scoring_scan_id,),
            ).fetchall()
        )

    windows: dict[str, dict[str, Any]] = {}
    cutoff_values: list[str] = []
    if scoring_scan and scoring_scan.get("finished_at"):
        cutoff_values.append(str(scoring_scan["finished_at"]))

    for period, settings in WINDOW_DEFAULTS.items():
        snapshot_rows = connection.execute(
            """
            SELECT id, period_key, collected_at
            FROM trending_snapshots
            WHERE period_type = ? AND status = 'success'
            ORDER BY collected_at DESC, id DESC
            LIMIT ?
            """,
            (period, settings["limit"]),
        ).fetchall()
        snapshot_ids = [int(row["id"]) for row in snapshot_rows]
        if snapshot_rows:
            cutoff_values.append(str(snapshot_rows[0]["collected_at"]))
        appearances: dict[int, int] = {}
        last_appearance: dict[int, str] = {}
        if snapshot_ids:
            placeholders = ",".join("?" for _ in snapshot_ids)
            rows = connection.execute(
                f"""
                SELECT i.repository_id, COUNT(DISTINCT i.snapshot_id) AS appearance_count,
                       MAX(s.collected_at) AS last_appearance_at
                FROM trending_snapshot_items i
                JOIN trending_snapshots s ON s.id = i.snapshot_id
                WHERE i.snapshot_id IN ({placeholders})
                GROUP BY i.repository_id
                """,
                snapshot_ids,
            ).fetchall()
            for row in rows:
                repository_id = int(row["repository_id"])
                appearances[repository_id] = int(row["appearance_count"])
                if row["last_appearance_at"]:
                    last_appearance[repository_id] = str(row["last_appearance_at"])
                candidate_ids.add(repository_id)
        windows[period] = {
            "snapshot_ids": snapshot_ids,
            "sample_count": len(snapshot_ids),
            "minimum_samples": settings["minimum"],
            "limit": settings["limit"],
            "appearance_counts": appearances,
            "last_appearance": last_appearance,
            "latest_snapshot": dict(snapshot_rows[0]) if snapshot_rows else None,
        }

    repositories: list[sqlite3.Row] = []
    if candidate_ids:
        ids = sorted(candidate_ids)
        placeholders = ",".join("?" for _ in ids)
        repositories = connection.execute(
            f"""
            SELECT id, github_repo_id, full_name, owner, name, description, html_url,
                   language, stars_count, forks_count, last_synced_at
            FROM repositories
            WHERE id IN ({placeholders})
            """,
            ids,
        ).fetchall()

    repository_rows = [dict(row) for row in repositories]
    repository_rows.sort(
        key=lambda row: (
            -int(row["stars_count"]),
            str(row["full_name"]).casefold(),
            int(row["id"]),
        )
    )
    stars_rank = {
        int(row["id"]): index
        for index, row in enumerate(repository_rows, start=1)
    }
    last_appearance_by_repo: dict[int, str] = {}
    for window in windows.values():
        for repository_id, captured_at in window["last_appearance"].items():
            previous = last_appearance_by_repo.get(repository_id)
            if previous is None or captured_at > previous:
                last_appearance_by_repo[repository_id] = captured_at

    scoring_scan_finished = scoring_scan.get("finished_at") if scoring_scan else None
    scan_age_days = _age_days(scoring_scan_finished, now)
    latest_scan_age_days = _age_days(
        (latest_scan or {}).get("finished_at") or (latest_scan or {}).get("started_at"),
        now,
    )
    stars_stale = (
        scoring_scan is None
        or scan_age_days is None
        or scan_age_days > STARS_STALE_AFTER_DAYS
    )
    stars_incomplete = bool(
        latest_scan
        and (
            latest_scan.get("status") != "success"
            or latest_scan.get("incomplete_results")
        )
    )
    data_cutoff = max(cutoff_values) if cutoff_values else None

    return {
        "repositories": repository_rows,
        "windows": windows,
        "stars_rank": stars_rank,
        "last_appearance_by_repo": last_appearance_by_repo,
        "candidate_count": len(repository_rows),
        "data_cutoff_at": data_cutoff,
        "latest_stars_scan": latest_scan,
        "scoring_stars_scan": scoring_scan,
        "stars_scan_age_days": scan_age_days,
        "latest_stars_scan_age_days": latest_scan_age_days,
        "stars_stale": stars_stale,
        "stars_incomplete": stars_incomplete,
        "stars_stale_after_days": STARS_STALE_AFTER_DAYS,
    }


def _coverage_for_repository(
    repository: dict[str, Any],
    repository_id: int,
    context: dict[str, Any],
    weights: dict[str, float],
    stars_rank: int,
) -> tuple[dict[str, Any], dict[str, float | None], float, list[str]]:
    candidate_count = int(context["candidate_count"])
    stars_score = (
        100.0 * (candidate_count - stars_rank + 1) / candidate_count
        if candidate_count > 0
        else None
    )
    scores: dict[str, float | None] = {"stars": stars_score}
    periods: dict[str, Any] = {}
    for period, window in context["windows"].items():
        sample_count = int(window["sample_count"])
        appearance_count = int(window["appearance_counts"].get(repository_id, 0))
        available = sample_count >= int(window["minimum_samples"])
        score = (
            appearance_count / sample_count * 100.0
            if available and sample_count > 0
            else None
        )
        scores[period] = score
        periods[period] = {
            "sample_count": sample_count,
            "window_limit": int(window["limit"]),
            "minimum_samples": int(window["minimum_samples"]),
            "appearance_count": appearance_count,
            "available": available,
            "score": round(score, 1) if score is not None else None,
        }

    available_dimensions = [
        dimension for dimension, score in scores.items() if score is not None
    ]
    effective_weight = sum(weights[dimension] for dimension in available_dimensions)
    raw_total = (
        sum(weights[key] * float(scores[key]) for key in available_dimensions) / effective_weight
        if effective_weight > 0
        else 0.0
    )
    last_appearance = context["last_appearance_by_repo"].get(repository_id)
    coverage = {
        "stars": {
            "rank": stars_rank,
            "candidate_count": candidate_count,
            "stars_count": int(repository["stars_count"]),
            "last_synced_at": repository.get("last_synced_at"),
            "scoring_scan_id": (
                context["scoring_stars_scan"]["id"]
                if context["scoring_stars_scan"]
                else None
            ),
            "scoring_scan_finished_at": (
                context["scoring_stars_scan"]["finished_at"]
                if context["scoring_stars_scan"]
                else None
            ),
            "latest_scan_id": (
                context["latest_stars_scan"]["id"]
                if context["latest_stars_scan"]
                else None
            ),
            "latest_scan_status": (
                context["latest_stars_scan"]["status"]
                if context["latest_stars_scan"]
                else None
            ),
            "latest_scan_incomplete_results": (
                bool(context["latest_stars_scan"]["incomplete_results"])
                if context["latest_stars_scan"]
                else None
            ),
            "stale": context["stars_stale"],
            "incomplete": context["stars_incomplete"],
            "age_days": context["stars_scan_age_days"],
            "stale_after_days": context["stars_stale_after_days"],
        },
        "periods": periods,
        "last_appearance_at": last_appearance,
        "available_dimensions": available_dimensions,
        "effective_weight": round(effective_weight, 4),
        "weights": weights,
    }
    contributions = [
        (weights[key] * float(scores[key]), key)
        for key in available_dimensions
        if float(scores[key]) > 0
    ]
    contributions.sort(key=lambda item: (-item[0], item[1]))
    reason_codes = [key for _, key in contributions[:2]]
    if not reason_codes:
        reason_codes = ["low_signal"]
    return coverage, scores, raw_total, reason_codes


def create_recommendation_run(profile_id: int | None = None) -> dict[str, Any]:
    """Create an immutable recommendation run and persist all candidate scores."""
    with get_connection() as connection:
        if profile_id is None:
            profile_row = connection.execute(
                """
                SELECT * FROM recommendation_profiles
                ORDER BY is_default DESC, id ASC LIMIT 1
                """
            ).fetchone()
        else:
            profile_row = connection.execute(
                "SELECT * FROM recommendation_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        if profile_row is None:
            raise ValueError("Recommendation weight profile not found")
        profile = dict(profile_row)
        weights = _weights(profile_row)
        created_at = utc_now()
        cursor = connection.execute(
            """
            INSERT INTO recommendation_runs (
                profile_id, algorithm_version, weights_json, window_config_json,
                candidate_count, data_cutoff_at, status, created_at
            ) VALUES (?, ?, ?, ?, 0, NULL, 'running', ?)
            """,
            (
                int(profile["id"]),
                ALGORITHM_VERSION,
                json.dumps(weights, ensure_ascii=False, sort_keys=True),
                json.dumps(
                    {
                        "periods": WINDOW_DEFAULTS,
                        "stars_stale_after_days": STARS_STALE_AFTER_DAYS,
                        "category_thresholds": CATEGORY_THRESHOLDS,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                created_at,
            ),
        )
        run_id = int(cursor.lastrowid)

    try:
        with get_connection() as connection:
            context = _read_run_context(connection)
            scored: list[dict[str, Any]] = []
            for repository in context["repositories"]:
                repository_id = int(repository["id"])
                rank = int(context["stars_rank"][repository_id])
                coverage, scores, raw_total, reasons = _coverage_for_repository(
                    repository,
                    repository_id,
                    context,
                    weights,
                    rank,
                )
                scored.append(
                    {
                        "repository": repository,
                        "stars_rank": rank,
                        "coverage": coverage,
                        "scores": scores,
                        "raw_total": raw_total,
                        "reasons": reasons,
                        "last_appearance_at": coverage["last_appearance_at"],
                    }
                )

            scored.sort(
                key=lambda item: (
                    -item["raw_total"],
                    item["stars_rank"],
                    -(item["last_appearance_at"] or ""),
                    str(item["repository"]["full_name"]).casefold(),
                )
            )
            for rank, item in enumerate(scored, start=1):
                scores = item["scores"]
                connection.execute(
                    """
                    INSERT INTO recommendation_scores (
                        run_id, repository_id, stars_score, daily_score, weekly_score,
                        monthly_score, total_score, rank, reasons_json, sample_coverage_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        int(item["repository"]["id"]),
                        round(scores["stars"], 1) if scores["stars"] is not None else None,
                        round(scores["daily"], 1) if scores["daily"] is not None else None,
                        round(scores["weekly"], 1) if scores["weekly"] is not None else None,
                        round(scores["monthly"], 1) if scores["monthly"] is not None else None,
                        round(item["raw_total"], 1),
                        rank,
                        json.dumps(item["reasons"], ensure_ascii=False),
                        json.dumps(item["coverage"], ensure_ascii=False, sort_keys=True),
                    ),
                )

            windows_for_storage = {}
            for period, window in context["windows"].items():
                windows_for_storage[period] = {
                    "sample_count": window["sample_count"],
                    "minimum_samples": window["minimum_samples"],
                    "window_limit": window["limit"],
                    "latest_snapshot": window["latest_snapshot"],
                }
            config = {
                "periods": windows_for_storage,
                "stars_stale_after_days": STARS_STALE_AFTER_DAYS,
                "category_thresholds": CATEGORY_THRESHOLDS,
                "latest_stars_scan": context["latest_stars_scan"],
                "scoring_stars_scan": context["scoring_stars_scan"],
                "stars_scan_age_days": context["stars_scan_age_days"],
                "latest_stars_scan_age_days": context["latest_stars_scan_age_days"],
                "stars_stale": context["stars_stale"],
                "stars_incomplete": context["stars_incomplete"],
                "candidate_sources": [
                    "latest_successful_stars_scan",
                    "successful_daily_snapshots",
                    "successful_weekly_snapshots",
                    "successful_monthly_snapshots",
                ],
            }
            finished_at = utc_now()
            connection.execute(
                """
                UPDATE recommendation_runs
                SET candidate_count = ?, data_cutoff_at = ?, window_config_json = ?,
                    status = 'success', finished_at = ?, error_summary = NULL
                WHERE id = ?
                """,
                (
                    len(scored),
                    context["data_cutoff_at"],
                    json.dumps(config, ensure_ascii=False, sort_keys=True),
                    finished_at,
                    run_id,
                ),
            )
    except Exception as exc:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE recommendation_runs
                SET status = 'failed', finished_at = ?, error_summary = ?
                WHERE id = ?
                """,
                (utc_now(), str(exc)[:1000], run_id),
            )
        raise

    result = get_recommendation_run_detail(run_id, page=1, page_size=50)
    if result is None:
        raise RuntimeError("Recommendation run was saved but could not be read back")
    return result


def list_recommendation_runs(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    offset = (page - 1) * page_size
    with get_connection() as connection:
        total = int(
            connection.execute("SELECT COUNT(*) AS count FROM recommendation_runs").fetchone()["count"]
        )
        rows = connection.execute(
            """
            SELECT r.id, r.profile_id, p.name AS profile_name, r.algorithm_version,
                   r.weights_json, r.candidate_count, r.data_cutoff_at, r.status,
                   r.created_at, r.finished_at, r.error_summary
            FROM recommendation_runs r
            LEFT JOIN recommendation_profiles p ON p.id = r.profile_id
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["weights"] = _json_load(item.pop("weights_json"), {})
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


def get_latest_recommendation_run_id() -> int | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id FROM recommendation_runs
            WHERE status = 'success'
            ORDER BY created_at DESC, id DESC LIMIT 1
            """
        ).fetchone()
    return int(row["id"]) if row else None


def get_recommendation_run_detail(
    run_id: int,
    *,
    category: str = "all",
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any] | None:
    with get_connection() as connection:
        run_row = connection.execute(
            """
            SELECT r.*, p.name AS profile_name, p.description AS profile_description
            FROM recommendation_runs r
            LEFT JOIN recommendation_profiles p ON p.id = r.profile_id
            WHERE r.id = ?
            """,
            (run_id,),
        ).fetchone()
        if run_row is None:
            return None
        rows = connection.execute(
            """
            SELECT s.repository_id, s.stars_score, s.daily_score, s.weekly_score,
                   s.monthly_score, s.total_score, s.rank, s.reasons_json,
                   s.sample_coverage_json, r.github_repo_id, r.full_name, r.owner,
                   r.name, r.description, r.html_url, r.language, r.stars_count,
                   r.forks_count, r.last_synced_at, i.marked_at AS interested_at,
                   p.status AS research_status
            FROM recommendation_scores s
            JOIN repositories r ON r.id = s.repository_id
            LEFT JOIN interested_projects i ON i.repository_id = r.id
            LEFT JOIN research_projects p ON p.repository_id = r.id
            WHERE s.run_id = ?
            ORDER BY s.rank ASC
            """,
            (run_id,),
        ).fetchall()

    run = dict(run_row)
    weights = _json_load(run.pop("weights_json"), {})
    window_config = _json_load(run.pop("window_config_json"), {})
    thresholds = {
        **CATEGORY_THRESHOLDS,
        **(window_config.get("category_thresholds") or {}),
    }
    all_items = [_item_from_row(row, thresholds) for row in rows]
    grade_counts = {key: 0 for key in GRADE_LABELS}
    for item in all_items:
        grade_counts[item["grade"]] += 1
    summary = {
        "candidate_count": int(run["candidate_count"]),
        "scored_count": len(all_items),
        "priority_count": sum("priority" in item["categories"] for item in all_items),
        "emerging_count": sum("emerging" in item["categories"] for item in all_items),
        "stable_count": sum("stable" in item["categories"] for item in all_items),
        "grade_counts": grade_counts,
        "latest_stars_scan": window_config.get("latest_stars_scan"),
        "scoring_stars_scan": window_config.get("scoring_stars_scan"),
        "stars_stale": bool(window_config.get("stars_stale", True)),
        "stars_incomplete": bool(window_config.get("stars_incomplete", False)),
        "stars_stale_after_days": window_config.get(
            "stars_stale_after_days", STARS_STALE_AFTER_DAYS
        ),
        "stars_scan_age_days": window_config.get("stars_scan_age_days"),
        "data_coverage": window_config.get("periods", {}),
        "candidate_sources": window_config.get("candidate_sources", []),
    }
    normalized_query = (q or "").strip().casefold()
    filtered = [
        item
        for item in all_items
        if _category_matches(category, item, thresholds)
        and (
            not normalized_query
            or normalized_query in item["full_name"].casefold()
            or normalized_query in (item["description"] or "").casefold()
        )
    ]
    offset = (page - 1) * page_size
    total = len(filtered)
    return {
        "run": {
            **run,
            "weights": weights,
            "window_config": window_config,
        },
        "summary": summary,
        "items": filtered[offset : offset + page_size],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
        "filters": {
            "category": category,
            "category_label": CATEGORY_LABELS.get(category, category),
            "query": q or "",
        },
    }
