from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_memory.controls import (
    export_owner_memory,
    recent_automatic_memories,
    reset_owner_memory,
    set_memory_archived,
    undo_automatic_memory,
)
from app.assistant_memory.management_routes import register_memory_management_routes
from app.assistant_memory.models import MemoryScopeContext
from app.assistant_memory.observability import (
    memory_usage_snapshot,
    record_memory_usage,
    reset_companion_metrics,
)
from app.assistant_memory.owner_repository import OwnerAwareInMemoryMemoryRepository
from app.assistant_memory.owner_service import OwnerAwareMemoryService
from app.assistant_memory.structured_consolidation import consolidate_structured_proposal
from app.assistant_memory.structured_extraction import extract_structured_memory_proposals
from app.chat.models import ChatMessage, ChatSession


def _context(owner_id: str = "system-assistant") -> MemoryScopeContext:
    return MemoryScopeContext(
        profile_id="profile:default",
        workspace_id="workspace:local",
        project_id=None,
        session_id="chat:controls",
        owner_type="system" if owner_id == "system-assistant" else "character",
        owner_id=owner_id,
    )


def _session() -> ChatSession:
    return ChatSession(
        id="chat:controls",
        title="Controls",
        memory_enabled=True,
        messages=[
            ChatMessage(
                id="msg:auto",
                role="user",
                content="I prefer quiet mornings",
                created_at="2026-07-19T00:00:00+00:00",
            )
        ],
        message_count=1,
        created_at="2026-07-19T00:00:00+00:00",
        updated_at="2026-07-19T00:00:00+00:00",
    )


class _Store:
    def __init__(self, session: ChatSession) -> None:
        self.sessions = [session]

    def get_session(self, session_id: str):
        return next((item for item in self.sessions if item.id == session_id), None)

    def _load_sessions(self):
        return self.sessions

    def _save_sessions(self, sessions):
        self.sessions = sessions


def test_archive_restore_export_and_reset_are_owner_scoped() -> None:
    repository = OwnerAwareInMemoryMemoryRepository("controls:lifecycle")
    service = OwnerAwareMemoryService(repository)
    context = _context()
    record = service.create_explicit_memory(
        context,
        scope="session",
        category="preference",
        content="Quiet mornings",
        provenance_id="msg:one",
    )
    other_context = _context("character:maya")
    service.create_explicit_memory(
        other_context,
        scope="session",
        category="fact",
        content="Maya-specific memory",
        provenance_id="msg:other",
    )

    archived = set_memory_archived(
        service,
        context,
        record.id,
        archived=True,
        expected_revision=record.revision,
    )
    assert archived.status == "archived"
    assert service.list_active(context) == []

    restored = set_memory_archived(
        service,
        context,
        record.id,
        archived=False,
        expected_revision=archived.revision,
    )
    assert restored.status == "active"
    exported = export_owner_memory(service, context)
    assert [item.id for item in exported.records] == [record.id]
    assert "Maya-specific memory" not in str(exported.model_dump(mode="json"))

    store = _Store(_session())
    result = reset_owner_memory(store, service, context)
    assert result.record_count == 1
    assert service.list_active(context) == []
    assert len(service.list_active(other_context)) == 1
    assert store.sessions[0].memory_enabled is False


def test_automatic_direct_assertion_has_visible_undo() -> None:
    service = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository("controls:undo"))
    context = _context()
    proposals, skipped = extract_structured_memory_proposals(
        "I prefer quiet mornings",
        source_message_id="msg:auto",
    )
    assert skipped == []
    action, record = consolidate_structured_proposal(
        service,
        context,
        proposals[0],
        source_session_id=context.session_id,
        source_message_id="msg:auto",
        auto_save_direct_assertions=True,
    )
    assert action == "saved"
    assert record.structured_payload["automatic_direct_assertion"] is True
    assert [item.id for item in recent_automatic_memories(service, context, {"msg:auto"})] == [record.id]

    assert undo_automatic_memory(
        service,
        context,
        {"msg:auto"},
        record.id,
        expected_revision=record.revision,
    ) is True
    assert service.repository.get_record(record.id) is None


def test_memory_usage_explanation_is_content_free() -> None:
    reset_companion_metrics()
    record_memory_usage(
        "chat:controls",
        [
            {
                "memory_id": "memory:route",
                "selection_reason": "routine_start_window",
                "activation_score": 900,
                "section": "due_routines",
                "source_revision": 2,
            }
        ],
    )
    payload = memory_usage_snapshot("chat:controls").model_dump(mode="json")
    assert payload["items"][0]["selection_reason"] == "routine_start_window"
    assert "content" not in str(payload)


def test_management_static_control_routes_are_reachable() -> None:
    store = _Store(_session())
    service = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository("controls:routes"))
    service.create_explicit_memory(
        _context(),
        scope="session",
        category="fact",
        content="Exportable memory",
        provenance_id="msg:auto",
    )
    app = FastAPI()
    register_memory_management_routes(
        app,
        chat_store_factory=lambda: store,
        memory_service_factory=lambda: service,
    )
    client = TestClient(app)

    export_response = client.get("/api/assistant/memory/export", params={"session_id": "chat:controls"})
    assert export_response.status_code == 200
    assert export_response.json()["records"][0]["content"] == "Exportable memory"
    usage_response = client.get("/api/assistant/memory/usage", params={"session_id": "chat:controls"})
    assert usage_response.status_code == 200
    assert usage_response.json()["diagnostics_policy"] == "content_free"
    assert "/api/assistant/memory/export" not in client.get("/openapi.json").json()["paths"]
