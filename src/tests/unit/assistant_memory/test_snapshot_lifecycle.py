from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_memory import MemoryService, SQLiteMemoryRepository, resolve_chat_scope
from app.assistant_memory.routes import register_assistant_memory_routes
from app.chat import ChatSessionStore, CreateChatSessionRequest
from app.chat.memory_session import (
    RefreshSessionMemoryRequest,
    SessionMemoryConflictError,
    get_session_memory_state,
    refresh_session_memory,
)


def setup_services(tmp_path):
    chat_store = ChatSessionStore(tmp_path / "chat.json")
    memory_service = MemoryService(SQLiteMemoryRepository(tmp_path / "memory.sqlite3"))
    session = chat_store.create_session(CreateChatSessionRequest(title="Memory lifecycle"))
    context = resolve_chat_scope(
        session.id,
        profile_id=session.profile_id,
        workspace_id=session.workspace_id,
        project_id=session.project_id,
    )
    return chat_store, memory_service, session, context


def test_refresh_freezes_snapshot_until_explicit_next_refresh(tmp_path):
    store, service, session, context = setup_services(tmp_path)
    first_record = service.create_explicit_memory(
        context,
        scope="global",
        category="preference",
        content="Prefer detailed explanations.",
        provenance_id="msg:one",
    )

    first = refresh_session_memory(store, service, session.id, RefreshSessionMemoryRequest())
    assert first is not None
    assert first.snapshot_revision == 1
    assert [item.memory_record_id for item in first.snapshot.items] == [first_record.id]

    second_record = service.create_explicit_memory(
        context,
        scope="workspace",
        category="instruction",
        content="Use GitHub Actions as verification truth.",
        provenance_id="msg:two",
    )
    unchanged = get_session_memory_state(store, service, session.id)
    assert unchanged is not None
    assert unchanged.snapshot_revision == 1
    assert [item.memory_record_id for item in unchanged.snapshot.items] == [first_record.id]

    refreshed = refresh_session_memory(
        store,
        service,
        session.id,
        RefreshSessionMemoryRequest(expected_snapshot_revision=1),
    )
    assert refreshed is not None
    assert refreshed.snapshot_revision == 2
    assert {item.memory_record_id for item in refreshed.snapshot.items} == {
        first_record.id,
        second_record.id,
    }


def test_stale_refresh_is_rejected_without_changing_active_snapshot(tmp_path):
    store, service, session, context = setup_services(tmp_path)
    service.create_explicit_memory(
        context,
        scope="global",
        category="preference",
        content="Prefer detailed explanations.",
        provenance_id="msg:one",
    )
    first = refresh_session_memory(store, service, session.id, RefreshSessionMemoryRequest())
    assert first is not None

    with __import__("pytest").raises(SessionMemoryConflictError):
        refresh_session_memory(
            store,
            service,
            session.id,
            RefreshSessionMemoryRequest(expected_snapshot_revision=2),
        )
    state = get_session_memory_state(store, service, session.id)
    assert state.snapshot_id == first.snapshot_id
    assert state.snapshot_revision == 1


def test_forget_purges_frozen_content_and_updates_projected_count(tmp_path):
    store, service, session, context = setup_services(tmp_path)
    record = service.create_explicit_memory(
        context,
        scope="global",
        category="fact",
        content="Old sensitive environment fact.",
        provenance_id="msg:one",
    )
    first = refresh_session_memory(store, service, session.id, RefreshSessionMemoryRequest())
    assert first.memory_record_count == 1

    service.forget_memory(context, record.id, expected_revision=1)
    state = get_session_memory_state(store, service, session.id)
    assert state is not None
    assert state.memory_record_count == 0
    assert state.snapshot.items == []
    assert "Old sensitive environment fact" not in state.model_dump_json()


def test_expiry_and_scope_loss_override_frozen_snapshot(tmp_path):
    store, service, session, context = setup_services(tmp_path)
    record = service.create_explicit_memory(
        context,
        scope="global",
        category="fact",
        content="Temporary fact.",
        provenance_id="msg:one",
    )
    first = refresh_session_memory(store, service, session.id, RefreshSessionMemoryRequest())
    assert first.memory_record_count == 1

    expired = record.model_copy(
        update={
            "expires_at": "2000-01-01T00:00:00+00:00",
            "updated_at": "2026-07-08T00:00:00+00:00",
        }
    )
    service.repository.update_record(expired, expected_revision=1)
    state = get_session_memory_state(store, service, session.id)
    assert state.snapshot.items[0].active is False
    assert state.snapshot.items[0].content == ""
    assert state.snapshot.items[0].invalidation_reason == "record_expired"


def test_snapshot_routes_expose_state_refresh_and_revision_conflicts(tmp_path):
    store, service, session, context = setup_services(tmp_path)
    service.create_explicit_memory(
        context,
        scope="global",
        category="instruction",
        content="Never claim tests passed unless they ran.",
        provenance_id="msg:one",
    )
    app = FastAPI()
    register_assistant_memory_routes(
        app,
        chat_store_factory=lambda: store,
        memory_service_factory=lambda: service,
    )
    client = TestClient(app)

    before = client.get(f"/api/chat/sessions/{session.id}/memory")
    assert before.status_code == 200
    assert before.json()["memory_enabled"] is False

    refreshed = client.post(
        f"/api/chat/sessions/{session.id}/memory/refresh",
        json={"token_budget": 4000},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["snapshot_revision"] == 1
    assert refreshed.json()["memory_record_count"] == 1

    conflict = client.post(
        f"/api/chat/sessions/{session.id}/memory/refresh",
        json={"expected_snapshot_revision": 2},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "memory_snapshot_revision_conflict"

    missing = client.get("/api/chat/sessions/chat:missing/memory")
    assert missing.status_code == 404
