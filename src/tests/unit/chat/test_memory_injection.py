from __future__ import annotations

from types import SimpleNamespace

from app import shared
from app.assistant_memory import MemoryService, SQLiteMemoryRepository, resolve_chat_scope
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.chat.memory_session import RefreshSessionMemoryRequest, refresh_session_memory
from app.chat.store import ChatSessionStore as LegacyChatSessionStore


class RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat_completion(self, *, messages, model, stream=False):
        self.calls.append(
            {
                "messages": [(message.role, message.content) for message in messages],
                "model": model,
                "stream": stream,
            }
        )
        if stream:
            return iter([SimpleNamespace(content="Streamed answer.", model=model, usage={})])
        return SimpleNamespace(content="Regular answer.", model=model, usage={})


def setup_memory_chat(tmp_path):
    service = MemoryService(SQLiteMemoryRepository(tmp_path / "memory.sqlite3"))
    store = ChatSessionStore(
        tmp_path / "chat.json",
        memory_service_factory=lambda: service,
    )
    session = store.create_session(
        CreateChatSessionRequest(
            title="Memory injection",
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:test-model",
        )
    )
    context = resolve_chat_scope(
        session.id,
        profile_id=session.profile_id,
        workspace_id=session.workspace_id,
        project_id=session.project_id,
    )
    return service, store, session, context


def test_memory_feature_flag_off_preserves_legacy_provider_payload(monkeypatch, tmp_path):
    service, store, session, context = setup_memory_chat(tmp_path)
    service.create_explicit_memory(
        context,
        scope="global",
        category="preference",
        content="Prefer detailed answers.",
        provenance_id="msg:memory",
    )
    refresh_session_memory(store, service, session.id, RefreshSessionMemoryRequest())
    active_session = store.get_session(session.id)
    request_message = SimpleNamespace(
        id="msg:current",
        role="user",
        content="Continue",
        created_at="2026-07-08T00:00:00+00:00",
    )
    from app.chat import ChatMessage

    current = ChatMessage.model_validate(vars(request_message))
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "0")
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")

    current_messages = store._provider_messages(active_session, current, [])
    legacy_messages = LegacyChatSessionStore()._provider_messages(active_session, current, [])

    assert [(message.role, message.content) for message in current_messages] == [
        (message.role, message.content) for message in legacy_messages
    ]
    assembly, rendered = store.build_provider_prompt(active_session, current, [])
    assert assembly.diagnostics["memory"]["status"] == "disabled_by_feature_flag"
    assert store._active_memory_metadata(assembly, rendered) == {}


def test_enabled_memory_injects_only_approved_frozen_records(monkeypatch, tmp_path):
    service, store, session, context = setup_memory_chat(tmp_path)
    approved = service.create_explicit_memory(
        context,
        scope="global",
        category="instruction",
        content="Use GitHub Actions as verification truth.",
        provenance_id="msg:approved",
    )
    pending = service.propose_memory(
        context,
        source_session_id=session.id,
        source_message_id="msg:pending",
        scope="global",
        category="fact",
        content="Unapproved inferred detail.",
        confidence=0.7,
    )
    refresh_session_memory(store, service, session.id, RefreshSessionMemoryRequest())
    provider = RecordingProvider()
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")

    result = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="Continue the implementation"),
    )

    assert result is not None
    captured = "\n".join(content for _, content in provider.calls[0]["messages"])
    assert "Approved remembered context follows." in captured
    assert approved.content in captured
    assert pending.proposed_content not in captured
    persisted = store.get_session(session.id)
    assistant = persisted.messages[-1]
    assert assistant.metadata["memory_context"]["selected_memory_ids"] == [approved.id]
    assert assistant.metadata["memory_context"]["selected_memory_count"] == 1


def test_streaming_and_non_streaming_use_same_memory_snapshot(monkeypatch, tmp_path):
    provider = RecordingProvider()
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")

    for name, stream in (("regular", False), ("stream", True)):
        root = tmp_path / name
        root.mkdir()
        service, store, session, context = setup_memory_chat(root)
        service.create_explicit_memory(
            context,
            scope="workspace",
            category="preference",
            content="Prefer auditable changes.",
            provenance_id="msg:memory",
        )
        refresh_session_memory(store, service, session.id, RefreshSessionMemoryRequest())
        if not stream:
            store.append_user_message(
                session.id,
                SendChatMessageRequest(content="Proceed"),
            )
            continue
        appended = store.begin_user_message(
            session.id,
            SendChatMessageRequest(content="Proceed"),
        )
        assert appended is not None
        active_session, user_message = appended
        events = list(
            store.stream_provider_reply_chunks(
                active_session,
                user_message,
                provider_id=active_session.provider_id,
                model_id=active_session.model_id,
            )
        )
        complete = events[-1]
        assert complete["metadata"]["memory_context"]["selected_memory_count"] == 1

    assert provider.calls[0]["messages"] == provider.calls[1]["messages"]


def test_forgotten_snapshot_record_is_not_injected(monkeypatch, tmp_path):
    service, store, session, context = setup_memory_chat(tmp_path)
    record = service.create_explicit_memory(
        context,
        scope="global",
        category="fact",
        content="Fact that must disappear.",
        provenance_id="msg:memory",
    )
    refresh_session_memory(store, service, session.id, RefreshSessionMemoryRequest())
    service.forget_memory(context, record.id, expected_revision=1)
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    from app.chat import ChatMessage

    current = ChatMessage(
        id="msg:current",
        role="user",
        content="Continue",
        created_at="2026-07-08T00:00:00+00:00",
    )
    assembly, rendered = store.build_provider_prompt(store.get_session(session.id), current, [])
    rendered_text = "\n".join(message.content for message in rendered.messages)

    assert record.content not in rendered_text
    assert assembly.diagnostics["memory"]["selected_memory_count"] == 0
