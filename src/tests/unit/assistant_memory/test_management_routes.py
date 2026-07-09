from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_memory import MemoryService, SQLiteMemoryRepository, resolve_chat_scope
from app.assistant_memory.routes import register_assistant_memory_routes
from app.chat import ChatSessionStore, CreateChatSessionRequest


def setup_client(tmp_path):
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    memory_service = MemoryService(SQLiteMemoryRepository(tmp_path / "memory.sqlite3"))
    session = chat_store.create_session(CreateChatSessionRequest(title="Memory management"))
    other_session = chat_store.create_session(CreateChatSessionRequest(title="Other session"))
    app = FastAPI()
    register_assistant_memory_routes(
        app,
        chat_store_factory=lambda: chat_store,
        memory_service_factory=lambda: memory_service,
    )
    return TestClient(app), chat_store, memory_service, session, other_session


def test_memory_crud_is_session_scope_bound_and_revisioned(tmp_path):
    client, _, _, session, other_session = setup_client(tmp_path)

    created = client.post(
        "/api/assistant/memory",
        json={
            "session_id": session.id,
            "scope": "session",
            "category": "instruction",
            "content": "Use the current session workflow.",
            "pinned": False,
        },
    )
    assert created.status_code == 200
    record = created.json()
    assert record["scope_id"] == session.id
    assert record["revision"] == 1

    listed = client.get("/api/assistant/memory", params={"session_id": session.id})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    isolated = client.get("/api/assistant/memory", params={"session_id": other_session.id})
    assert isolated.status_code == 200
    assert isolated.json()["total"] == 0

    edited = client.patch(
        f"/api/assistant/memory/{record['id']}",
        json={
            "session_id": session.id,
            "expected_revision": 1,
            "content": "Use the revised current session workflow.",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["revision"] == 2

    stale = client.patch(
        f"/api/assistant/memory/{record['id']}",
        json={
            "session_id": session.id,
            "expected_revision": 1,
            "content": "Stale edit",
        },
    )
    assert stale.status_code == 409

    forbidden_read = client.get(
        f"/api/assistant/memory/{record['id']}",
        params={"session_id": other_session.id},
    )
    assert forbidden_read.status_code == 404

    forgotten = client.delete(
        f"/api/assistant/memory/{record['id']}",
        params={"session_id": session.id, "expected_revision": 2},
    )
    assert forgotten.status_code == 200
    assert forgotten.json() == {"ok": True, "memory_id": record["id"]}


def test_pin_move_filters_and_search_are_backend_derived(tmp_path):
    client, _, _, session, _ = setup_client(tmp_path)
    first = client.post(
        "/api/assistant/memory",
        json={
            "session_id": session.id,
            "scope": "global",
            "category": "preference",
            "content": "Prefer detailed explanations.",
            "pinned": False,
        },
    ).json()
    client.post(
        "/api/assistant/memory",
        json={
            "session_id": session.id,
            "scope": "workspace",
            "category": "fact",
            "content": "The workspace uses local providers.",
            "pinned": False,
        },
    )

    pinned = client.post(
        f"/api/assistant/memory/{first['id']}/pin",
        json={"session_id": session.id, "expected_revision": 1},
    )
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True
    assert pinned.json()["revision"] == 2

    filtered = client.get(
        "/api/assistant/memory",
        params={
            "session_id": session.id,
            "pinned_only": True,
            "query": "detailed",
        },
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["records"]] == [first["id"]]

    moved = client.post(
        f"/api/assistant/memory/{first['id']}/move",
        json={
            "session_id": session.id,
            "expected_revision": 2,
            "target_scope": "workspace",
        },
    )
    assert moved.status_code == 200
    assert moved.json()["scope"] == "workspace"
    assert moved.json()["revision"] == 3

    unpinned = client.post(
        f"/api/assistant/memory/{first['id']}/unpin",
        json={"session_id": session.id, "expected_revision": 3},
    )
    assert unpinned.status_code == 200
    assert unpinned.json()["pinned"] is False


def test_candidate_management_never_crosses_session_or_scope(tmp_path):
    client, _, service, session, other_session = setup_client(tmp_path)
    context = resolve_chat_scope(
        session.id,
        profile_id=session.profile_id,
        workspace_id=session.workspace_id,
        project_id=session.project_id,
    )
    candidate = service.propose_memory(
        context,
        source_session_id=session.id,
        source_message_id="msg:source",
        scope="session",
        category="preference",
        content="Prefer candidate reviews.",
        confidence=0.9,
    )

    listed = client.get(
        "/api/assistant/memory/candidates/pending",
        params={"session_id": session.id},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["candidates"]] == [candidate.id]

    isolated = client.get(
        "/api/assistant/memory/candidates/pending",
        params={"session_id": other_session.id},
    )
    assert isolated.status_code == 200
    assert isolated.json()["total"] == 0

    forbidden = client.post(
        f"/api/assistant/memory/candidates/{candidate.id}/reject",
        json={"session_id": other_session.id, "pinned": False},
    )
    assert forbidden.status_code == 403
    assert service.repository.get_candidate(candidate.id).status == "pending"

    approved = client.post(
        f"/api/assistant/memory/candidates/{candidate.id}/approve",
        json={"session_id": session.id, "pinned": True},
    )
    assert approved.status_code == 200
    assert approved.json()["trust_level"] == "user_approved"
    assert approved.json()["pinned"] is True
    assert service.repository.get_candidate(candidate.id).status == "accepted"

    pending_delete = client.request(
        "DELETE",
        f"/api/assistant/memory/candidates/{candidate.id}",
        json={"session_id": session.id, "expected_status": "pending"},
    )
    assert pending_delete.status_code == 403
    assert service.repository.get_candidate(candidate.id).status == "accepted"

    forbidden_delete = client.request(
        "DELETE",
        f"/api/assistant/memory/candidates/{candidate.id}",
        json={"session_id": other_session.id, "expected_status": "accepted"},
    )
    assert forbidden_delete.status_code == 403
    assert service.repository.get_candidate(candidate.id).status == "accepted"

    deleted = client.request(
        "DELETE",
        f"/api/assistant/memory/candidates/{candidate.id}",
        json={"session_id": session.id, "expected_status": "accepted"},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "candidate_id": candidate.id}
    assert service.repository.get_candidate(candidate.id) is None


def test_management_routes_are_hidden_from_generated_openapi(tmp_path):
    client, _, _, session, _ = setup_client(tmp_path)
    schema = client.get("/openapi.json").json()

    assert "/api/assistant/memory" not in schema["paths"]
    assert "/api/chat/sessions/{session_id}/memory" not in schema["paths"]
    assert client.get("/api/assistant/memory", params={"session_id": session.id}).status_code == 200
