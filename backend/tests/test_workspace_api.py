from fastapi.testclient import TestClient

from app.database.connection import get_connection
from app.main import app


def _seed_repositories():
    with get_connection() as connection:
        rows = [
            (501, "octo/alpha", "Alpha platform", "Python", 1200),
            (502, "octo/beta", "Beta developer tools", "TypeScript", 800),
            (503, "octo/gamma", "Gamma research library", "Python", 300),
        ]
        ids = {}
        for github_id, full_name, description, language, stars in rows:
            cursor = connection.execute(
                """
                INSERT INTO repositories (
                    github_repo_id, full_name, owner, name, description, html_url,
                    language, stars_count, forks_count, open_issues_count, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 10, 2, '2026-11-24T08:00:00Z')
                """,
                (
                    github_id,
                    full_name,
                    "octo",
                    full_name.split("/")[1],
                    description,
                    f"https://github.com/{full_name}",
                    language,
                    stars,
                ),
            )
            ids[full_name] = int(cursor.lastrowid)
    return ids


def test_interested_mark_update_unmark_is_independent_from_research(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        repository_id = _seed_repositories()["octo/alpha"]
        marked = client.post(
            "/api/v1/interested",
            json={
                "repository_id": repository_id,
                "source_page": "recommendations",
                "tags": ["AI", " tools ", "ai"],
                "notes": "Review the architecture later.",
            },
        )
        duplicate = client.post(
            "/api/v1/interested",
            json={"repository_id": repository_id, "source_page": "trending"},
        )
        updated = client.patch(
            f"/api/v1/interested/{repository_id}",
            json={"tags": ["AI", "Infrastructure"], "notes": "Read the source first."},
        )
        research = client.post(
            "/api/v1/research",
            json={
                "repository_id": repository_id,
                "research_goal": "Understand the project architecture.",
            },
        )
        unmarked = client.delete(f"/api/v1/interested/{repository_id}")
        research_after_unmark = client.get(
            f"/api/v1/research/{research.json()['item']['id']}"
        )
        interest_after_unmark = client.get(f"/api/v1/interested/{repository_id}")

    assert marked.status_code == 201
    assert marked.json()["created"] is True
    assert marked.json()["item"]["tags"] == ["AI", "tools"]
    assert duplicate.status_code == 201
    assert duplicate.json()["created"] is False
    assert duplicate.json()["item"]["source_page"] == "recommendations"
    assert updated.status_code == 200
    assert updated.json()["item"]["tags"] == ["AI", "Infrastructure"]
    assert updated.json()["item"]["notes"] == "Read the source first."
    assert research.status_code == 201
    assert unmarked.status_code == 200
    assert research_after_unmark.status_code == 200
    assert research_after_unmark.json()["item"]["repository"]["full_name"] == "octo/alpha"
    assert interest_after_unmark.status_code == 404


def test_research_lifecycle_tags_notes_and_status_timestamps(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        repository_id = _seed_repositories()["octo/beta"]
        created = client.post(
            "/api/v1/research",
            json={
                "repository_id": repository_id,
                "priority": "high",
                "research_goal": "Compare the API design.",
            },
        )
        research_id = created.json()["item"]["id"]
        duplicate = client.post(
            "/api/v1/research",
            json={"repository_id": repository_id},
        )
        started = client.patch(
            f"/api/v1/research/{research_id}",
            json={"status": "in_progress", "next_action": "Inspect the API routes."},
        )
        note = client.post(
            f"/api/v1/research/{research_id}/notes",
            json={
                "title": "API notes",
                "content": "The public API is split into small route modules.",
                "note_type": "analysis",
            },
        )
        note_id = note.json()["item"]["id"]
        note_updated = client.patch(
            f"/api/v1/research/{research_id}/notes/{note_id}",
            json={"title": "Updated API notes", "content": "The API has stable route boundaries."},
        )
        tags = client.put(
            f"/api/v1/research/{research_id}/tags",
            json={"tags": ["backend", "API", "backend"]},
        )
        completed = client.patch(
            f"/api/v1/research/{research_id}",
            json={"status": "completed", "conclusion": "Clear separation of concerns."},
        )
        reopened = client.patch(
            f"/api/v1/research/{research_id}",
            json={"status": "pending"},
        )
        detail = client.get(f"/api/v1/research/{research_id}")
        deleted_note = client.delete(
            f"/api/v1/research/{research_id}/notes/{note_id}"
        )
        deleted_research = client.delete(f"/api/v1/research/{research_id}")

    assert created.status_code == 201
    assert created.json()["item"]["status"] == "pending"
    assert created.json()["item"]["priority"] == "high"
    assert duplicate.status_code == 409
    assert started.status_code == 200
    assert started.json()["item"]["started_at"] is not None
    assert note.status_code == 201
    assert note_updated.status_code == 200
    assert note_updated.json()["item"]["title"] == "Updated API notes"
    assert tags.status_code == 200
    assert [item["name"] for item in tags.json()["item"]["tags"]] == ["API", "backend"]
    assert completed.json()["item"]["completed_at"] is not None
    assert reopened.json()["item"]["completed_at"] is None
    assert reopened.json()["item"]["started_at"] is not None
    assert detail.status_code == 200
    assert detail.json()["item"]["notes"][0]["content"] == "The API has stable route boundaries."
    assert deleted_note.status_code == 200
    assert deleted_research.status_code == 200


def test_interested_and_research_filters_and_pagination(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        ids = _seed_repositories()
        for name in ("octo/alpha", "octo/beta", "octo/gamma"):
            repository_id = ids[name]
            client.post("/api/v1/interested", json={"repository_id": repository_id})
        client.patch(
            f"/api/v1/interested/{ids['octo/alpha']}",
            json={"tags": ["AI", "backend"]},
        )
        client.patch(
            f"/api/v1/interested/{ids['octo/beta']}",
            json={"tags": ["frontend"]},
        )
        interested_tag = client.get("/api/v1/interested", params={"tag": "AI"})
        interested_language = client.get("/api/v1/interested", params={"language": "Python"})
        interested_page = client.get("/api/v1/interested", params={"page": 2, "page_size": 1})

        alpha = client.post(
            "/api/v1/research",
            json={"repository_id": ids["octo/alpha"], "priority": "high"},
        ).json()["item"]
        beta = client.post(
            "/api/v1/research",
            json={"repository_id": ids["octo/beta"], "priority": "low"},
        ).json()["item"]
        client.patch(f"/api/v1/research/{alpha['id']}", json={"status": "in_progress"})
        client.put(f"/api/v1/research/{alpha['id']}/tags", json={"tags": ["AI"]})
        client.put(f"/api/v1/research/{beta['id']}/tags", json={"tags": ["frontend"]})
        research_status = client.get(
            "/api/v1/research",
            params={"research_status": "in_progress"},
        )
        research_tag = client.get("/api/v1/research", params={"tag": "frontend"})
        research_priority = client.get("/api/v1/research", params={"priority": "high"})
        interested_with_research = client.get("/api/v1/interested", params={"research": "added"})
        interested_without_research = client.get("/api/v1/interested", params={"research": "not_added"})

    assert interested_tag.json()["pagination"]["total"] == 1
    assert interested_tag.json()["items"][0]["full_name"] == "octo/alpha"
    assert interested_language.json()["pagination"]["total"] == 2
    assert interested_page.json()["pagination"]["total_pages"] == 3
    assert len(interested_page.json()["items"]) == 1
    assert research_status.json()["pagination"]["total"] == 1
    assert research_status.json()["items"][0]["full_name"] == "octo/alpha"
    assert research_tag.json()["items"][0]["full_name"] == "octo/beta"
    assert research_priority.json()["items"][0]["full_name"] == "octo/alpha"
    assert interested_with_research.json()["pagination"]["total"] == 2
    assert interested_without_research.json()["pagination"]["total"] == 1
    assert interested_without_research.json()["items"][0]["full_name"] == "octo/gamma"


def test_workspace_validates_missing_repositories_and_missing_records(tmp_path, monkeypatch):
    monkeypatch.setenv("GITSCOUT_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        missing_interest = client.post(
            "/api/v1/interested",
            json={"repository_id": 9999},
        )
        missing_research = client.post(
            "/api/v1/research",
            json={"repository_id": 9999},
        )
        missing_note = client.post(
            "/api/v1/research/9999/notes",
            json={"content": "This should not be saved."},
        )
        empty = client.get("/api/v1/research")

    assert missing_interest.status_code == 404
    assert missing_research.status_code == 404
    assert missing_note.status_code == 404
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["pagination"]["total"] == 0
