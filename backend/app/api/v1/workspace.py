"""Personal interest and research workspace APIs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.database.connection import get_connection

interested_router = APIRouter(prefix="/interested", tags=["interested"])
research_router = APIRouter(prefix="/research", tags=["research"])

ResearchStatus = Literal["pending", "in_progress", "completed", "paused"]
ResearchPriority = Literal["high", "medium", "low"]


class InterestedMark(BaseModel):
    repository_id: int = Field(gt=0)
    source_page: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=10000)


class InterestedUpdate(BaseModel):
    source_page: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=10000)


class ResearchCreate(BaseModel):
    repository_id: int = Field(gt=0)
    status: ResearchStatus = "pending"
    priority: ResearchPriority = "medium"
    research_goal: str | None = Field(default=None, max_length=5000)
    next_action: str | None = Field(default=None, max_length=2000)
    conclusion: str | None = Field(default=None, max_length=10000)


class ResearchUpdate(BaseModel):
    status: ResearchStatus | None = None
    priority: ResearchPriority | None = None
    research_goal: str | None = Field(default=None, max_length=5000)
    next_action: str | None = Field(default=None, max_length=2000)
    conclusion: str | None = Field(default=None, max_length=10000)


class ResearchTagsUpdate(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=20)


class ResearchNoteCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, max_length=50000)
    note_type: str = Field(default="general", max_length=40)


class ResearchNoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=50000)
    note_type: str | None = Field(default=None, max_length=40)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clean_tags(tags: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        value = raw.strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        if len(value) > 40:
            raise HTTPException(status_code=422, detail="Tags must be 40 characters or fewer.")
        seen.add(key)
        result.append(value)
    return result


def _decode_tags(raw: str | None) -> list[str]:
    try:
        values = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(value) for value in values if isinstance(value, str)] if isinstance(values, list) else []


def _require_repository(connection: sqlite3.Connection, repository_id: int) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT id, github_repo_id, full_name, owner, name, description, html_url,
               language, stars_count, forks_count, open_issues_count, last_synced_at
        FROM repositories WHERE id = ?
        """,
        (repository_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return dict(row)


def _interested_detail(connection: sqlite3.Connection, repository_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT ip.repository_id, ip.marked_at, ip.source_page, ip.tags_json, ip.notes,
               r.github_repo_id, r.full_name, r.owner, r.name, r.description, r.html_url,
               r.language, r.stars_count, r.forks_count, r.open_issues_count, r.last_synced_at
        FROM interested_projects ip
        JOIN repositories r ON r.id = ip.repository_id
        WHERE ip.repository_id = ?
        """,
        (repository_id,),
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["id"] = item["repository_id"]
    item["tags"] = _decode_tags(item.pop("tags_json"))
    return item


def _research_tags(connection: sqlite3.Connection, research_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT t.id, t.name, t.color
        FROM research_project_tags rpt
        JOIN research_tags t ON t.id = rpt.tag_id
        WHERE rpt.research_project_id = ?
        ORDER BY t.name COLLATE NOCASE
        """,
        (research_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _research_notes(connection: sqlite3.Connection, research_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, title, content, note_type, created_at, updated_at
        FROM research_notes
        WHERE research_project_id = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (research_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _research_detail(connection: sqlite3.Connection, research_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT rp.id, rp.repository_id, rp.status, rp.priority, rp.research_goal,
               rp.next_action, rp.conclusion, rp.added_at, rp.started_at,
               rp.completed_at, rp.updated_at,
               r.github_repo_id, r.full_name, r.owner, r.name, r.description,
               r.html_url, r.language, r.stars_count, r.forks_count,
               r.open_issues_count, r.last_synced_at
        FROM research_projects rp
        JOIN repositories r ON r.id = rp.repository_id
        WHERE rp.id = ?
        """,
        (research_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["repository"] = {
        "id": result["repository_id"],
        **{
        key: result.pop(key)
        for key in (
            "github_repo_id", "full_name", "owner", "name", "description",
            "html_url", "language", "stars_count", "forks_count",
            "open_issues_count", "last_synced_at",
        )
        },
    }
    result["tags"] = _research_tags(connection, research_id)
    result["notes"] = _research_notes(connection, research_id)
    return result


def _pagination(page: int, page_size: int, total: int) -> dict[str, int]:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@interested_router.get("")
def list_interested_projects(
    q: str | None = Query(default=None, max_length=120),
    language: str | None = Query(default=None, max_length=80),
    tag: str | None = Query(default=None, max_length=40),
    sort: Literal["marked_at", "stars", "name"] = Query(default="marked_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    conditions: list[str] = []
    parameters: list[Any] = []
    if q and q.strip():
        keyword = f"%{q.strip()}%"
        conditions.append("(r.full_name LIKE ? OR r.description LIKE ?)")
        parameters.extend([keyword, keyword])
    if language and language.strip():
        conditions.append("r.language = ?")
        parameters.append(language.strip())
    if tag and tag.strip():
        conditions.append(
            """
            EXISTS (
                SELECT 1 FROM json_each(ip.tags_json) AS interest_tag
                WHERE lower(interest_tag.value) = lower(?)
            )
            """
        )
        parameters.append(tag.strip())
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    order_clause = {
        "marked_at": "ip.marked_at DESC, r.stars_count DESC",
        "stars": "r.stars_count DESC, r.full_name COLLATE NOCASE",
        "name": "r.full_name COLLATE NOCASE",
    }[sort]
    offset = (page - 1) * page_size

    with get_connection() as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM interested_projects ip JOIN repositories r ON r.id = ip.repository_id
            {where_clause}
            """,
            parameters,
        ).fetchone()["count"]
        rows = connection.execute(
            f"""
            SELECT ip.repository_id, ip.marked_at, ip.source_page, ip.tags_json, ip.notes,
                   r.github_repo_id, r.full_name, r.owner, r.name, r.description,
                   r.html_url, r.language, r.stars_count, r.forks_count,
                   r.open_issues_count, r.last_synced_at
            FROM interested_projects ip
            JOIN repositories r ON r.id = ip.repository_id
            {where_clause}
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
            """,
            [*parameters, page_size, offset],
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["id"] = item["repository_id"]
            item["tags"] = _decode_tags(item.pop("tags_json"))
            items.append(item)

    return {"items": items, "pagination": _pagination(page, page_size, total)}


@interested_router.post("", status_code=status.HTTP_201_CREATED)
def mark_interested(payload: InterestedMark) -> dict[str, Any]:
    tags = _clean_tags(payload.tags)
    with get_connection() as connection:
        _require_repository(connection, payload.repository_id)
        existing = connection.execute(
            "SELECT 1 FROM interested_projects WHERE repository_id = ?",
            (payload.repository_id,),
        ).fetchone()
        connection.execute(
            """
            INSERT OR IGNORE INTO interested_projects (
                repository_id, source_page, tags_json, notes
            ) VALUES (?, ?, ?, ?)
            """,
            (
                payload.repository_id,
                payload.source_page,
                json.dumps(tags, ensure_ascii=False),
                payload.notes,
            ),
        )
        item = _interested_detail(connection, payload.repository_id)
    return {"item": item, "created": existing is None}


@interested_router.get("/{repository_id}")
def get_interested_project(repository_id: int) -> dict[str, Any]:
    with get_connection() as connection:
        item = _interested_detail(connection, repository_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Interested project not found")
    return {"item": item}


@interested_router.patch("/{repository_id}")
def update_interested_project(
    repository_id: int,
    payload: InterestedUpdate,
) -> dict[str, Any]:
    updates: list[str] = []
    values: list[Any] = []
    fields = payload.model_fields_set
    if "source_page" in fields:
        updates.append("source_page = ?")
        values.append(payload.source_page)
    if "tags" in fields:
        updates.append("tags_json = ?")
        values.append(json.dumps(_clean_tags(payload.tags or []), ensure_ascii=False))
    if "notes" in fields:
        updates.append("notes = ?")
        values.append(payload.notes)
    if updates:
        with get_connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM interested_projects WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="Interested project not found")
            connection.execute(
                f"UPDATE interested_projects SET {', '.join(updates)} WHERE repository_id = ?",
                [*values, repository_id],
            )
            item = _interested_detail(connection, repository_id)
    else:
        with get_connection() as connection:
            item = _interested_detail(connection, repository_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Interested project not found")
    return {"item": item}


@interested_router.delete("/{repository_id}")
def unmark_interested_project(repository_id: int) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM interested_projects WHERE repository_id = ?",
            (repository_id,),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Interested project not found")
    return {"deleted": True, "repository_id": repository_id}


@research_router.get("")
def list_research_projects(
    q: str | None = Query(default=None, max_length=120),
    research_status: ResearchStatus | None = Query(default=None),
    priority: ResearchPriority | None = Query(default=None),
    tag: str | None = Query(default=None, max_length=40),
    sort: Literal["updated_at", "added_at", "priority"] = Query(default="updated_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    conditions: list[str] = []
    parameters: list[Any] = []
    if q and q.strip():
        keyword = f"%{q.strip()}%"
        conditions.append("(r.full_name LIKE ? OR r.description LIKE ? OR rp.research_goal LIKE ?)")
        parameters.extend([keyword, keyword, keyword])
    if research_status:
        conditions.append("rp.status = ?")
        parameters.append(research_status)
    if priority:
        conditions.append("rp.priority = ?")
        parameters.append(priority)
    if tag and tag.strip():
        conditions.append(
            """
            EXISTS (
                SELECT 1 FROM research_project_tags filter_tag
                JOIN research_tags filter_name ON filter_name.id = filter_tag.tag_id
                WHERE filter_tag.research_project_id = rp.id
                  AND lower(filter_name.name) = lower(?)
            )
            """
        )
        parameters.append(tag.strip())
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    order_clause = {
        "updated_at": "rp.updated_at DESC, rp.id DESC",
        "added_at": "rp.added_at DESC, rp.id DESC",
        "priority": "CASE rp.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, rp.updated_at DESC",
    }[sort]
    offset = (page - 1) * page_size

    with get_connection() as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM research_projects rp JOIN repositories r ON r.id = rp.repository_id
            {where_clause}
            """,
            parameters,
        ).fetchone()["count"]
        rows = connection.execute(
            f"""
            SELECT rp.id, rp.repository_id, rp.status, rp.priority, rp.research_goal,
                   rp.next_action, rp.conclusion, rp.added_at, rp.started_at,
                   rp.completed_at, rp.updated_at,
                   r.github_repo_id, r.full_name, r.owner, r.name, r.description,
                   r.html_url, r.language, r.stars_count, r.forks_count,
                   r.open_issues_count, r.last_synced_at,
                   (SELECT COUNT(*) FROM research_notes n WHERE n.research_project_id = rp.id) AS notes_count
            FROM research_projects rp
            JOIN repositories r ON r.id = rp.repository_id
            {where_clause}
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
            """,
            [*parameters, page_size, offset],
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["tags"] = _research_tags(connection, int(item["id"]))
            items.append(item)

    return {"items": items, "pagination": _pagination(page, page_size, total)}


@research_router.post("", status_code=status.HTTP_201_CREATED)
def create_research_project(payload: ResearchCreate) -> dict[str, Any]:
    now = _now()
    started_at = now if payload.status in {"in_progress", "completed"} else None
    completed_at = now if payload.status == "completed" else None
    with get_connection() as connection:
        _require_repository(connection, payload.repository_id)
        existing = connection.execute(
            "SELECT id FROM research_projects WHERE repository_id = ?",
            (payload.repository_id,),
        ).fetchone()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Repository is already in the research workspace")
        cursor = connection.execute(
            """
            INSERT INTO research_projects (
                repository_id, status, priority, research_goal, next_action,
                conclusion, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.repository_id, payload.status, payload.priority,
                payload.research_goal, payload.next_action, payload.conclusion,
                started_at, completed_at,
            ),
        )
        result = _research_detail(connection, int(cursor.lastrowid))
    return {"item": result}


@research_router.get("/{research_id}")
def get_research_project(research_id: int) -> dict[str, Any]:
    with get_connection() as connection:
        item = _research_detail(connection, research_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research project not found")
    return {"item": item}


@research_router.patch("/{research_id}")
def update_research_project(
    research_id: int,
    payload: ResearchUpdate,
) -> dict[str, Any]:
    fields = payload.model_fields_set
    updates: list[str] = []
    values: list[Any] = []
    with get_connection() as connection:
        current = connection.execute(
            "SELECT status, started_at, completed_at FROM research_projects WHERE id = ?",
            (research_id,),
        ).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Research project not found")
        if "status" in fields and payload.status is not None:
            next_status = payload.status
            updates.append("status = ?")
            values.append(next_status)
            if next_status in {"in_progress", "completed"} and current["started_at"] is None:
                updates.append("started_at = ?")
                values.append(_now())
            if next_status == "completed" and current["status"] != "completed":
                updates.append("completed_at = ?")
                values.append(_now())
            elif next_status != "completed" and current["status"] == "completed":
                updates.append("completed_at = NULL")
        for field in ("priority", "research_goal", "next_action", "conclusion"):
            if field in fields:
                updates.append(f"{field} = ?")
                values.append(getattr(payload, field))
        if updates:
            updates.append("updated_at = ?")
            values.append(_now())
            connection.execute(
                f"UPDATE research_projects SET {', '.join(updates)} WHERE id = ?",
                [*values, research_id],
            )
        item = _research_detail(connection, research_id)
    return {"item": item}


@research_router.delete("/{research_id}")
def delete_research_project(research_id: int) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM research_projects WHERE id = ?",
            (research_id,),
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Research project not found")
    return {"deleted": True, "research_id": research_id}


@research_router.put("/{research_id}/tags")
def replace_research_tags(
    research_id: int,
    payload: ResearchTagsUpdate,
) -> dict[str, Any]:
    tags = _clean_tags(payload.tags)
    with get_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM research_projects WHERE id = ?",
            (research_id,),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Research project not found")
        connection.execute(
            "DELETE FROM research_project_tags WHERE research_project_id = ?",
            (research_id,),
        )
        for name in tags:
            connection.execute(
                "INSERT OR IGNORE INTO research_tags(name) VALUES (?)",
                (name,),
            )
            tag_row = connection.execute(
                "SELECT id FROM research_tags WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
            connection.execute(
                """
                INSERT OR IGNORE INTO research_project_tags (research_project_id, tag_id)
                VALUES (?, ?)
                """,
                (research_id, int(tag_row["id"])),
            )
        connection.execute(
            "UPDATE research_projects SET updated_at = ? WHERE id = ?",
            (_now(), research_id),
        )
        result = _research_detail(connection, research_id)
    return {"item": result}


@research_router.post("/{research_id}/notes", status_code=status.HTTP_201_CREATED)
def create_research_note(
    research_id: int,
    payload: ResearchNoteCreate,
) -> dict[str, Any]:
    note_content = payload.content.strip()
    if not note_content:
        raise HTTPException(status_code=422, detail="Note content cannot be empty.")
    with get_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM research_projects WHERE id = ?",
            (research_id,),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Research project not found")
        cursor = connection.execute(
            """
            INSERT INTO research_notes (research_project_id, title, content, note_type)
            VALUES (?, ?, ?, ?)
            """,
            (research_id, payload.title.strip(), note_content, payload.note_type.strip() or "general"),
        )
        note = connection.execute(
            """
            SELECT id, title, content, note_type, created_at, updated_at
            FROM research_notes WHERE id = ?
            """,
            (int(cursor.lastrowid),),
        ).fetchone()
        connection.execute(
            "UPDATE research_projects SET updated_at = ? WHERE id = ?",
            (_now(), research_id),
        )
    return {"item": dict(note)}


@research_router.patch("/{research_id}/notes/{note_id}")
def update_research_note(
    research_id: int,
    note_id: int,
    payload: ResearchNoteUpdate,
) -> dict[str, Any]:
    fields = payload.model_fields_set
    updates: list[str] = []
    values: list[Any] = []
    for field in ("title", "content", "note_type"):
        if field in fields:
            value = getattr(payload, field)
            if field == "content" and value is not None:
                value = value.strip()
                if not value:
                    raise HTTPException(status_code=422, detail="Note content cannot be empty.")
            if field == "title" and value is not None:
                value = value.strip()
            if value is None:
                raise HTTPException(status_code=422, detail=f"{field} cannot be null.")
            if field == "note_type":
                value = value.strip() or "general"
            updates.append(f"{field} = ?")
            values.append(value)
    with get_connection() as connection:
        note_exists = connection.execute(
            """
            SELECT 1 FROM research_notes
            WHERE id = ? AND research_project_id = ?
            """,
            (note_id, research_id),
        ).fetchone()
        if note_exists is None:
            raise HTTPException(status_code=404, detail="Research note not found")
        if updates:
            updates.append("updated_at = ?")
            values.append(_now())
            connection.execute(
                f"""
                UPDATE research_notes SET {', '.join(updates)}
                WHERE id = ? AND research_project_id = ?
                """,
                [*values, note_id, research_id],
            )
            connection.execute(
                "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                (_now(), research_id),
            )
        note = connection.execute(
            """
            SELECT id, title, content, note_type, created_at, updated_at
            FROM research_notes WHERE id = ?
            """,
            (note_id,),
        ).fetchone()
    return {"item": dict(note)}


@research_router.delete("/{research_id}/notes/{note_id}")
def delete_research_note(research_id: int, note_id: int) -> dict[str, Any]:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM research_notes
            WHERE id = ? AND research_project_id = ?
            """,
            (note_id, research_id),
        )
        if cursor.rowcount:
            connection.execute(
                "UPDATE research_projects SET updated_at = ? WHERE id = ?",
                (_now(), research_id),
            )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Research note not found")
    return {"deleted": True, "note_id": note_id}
