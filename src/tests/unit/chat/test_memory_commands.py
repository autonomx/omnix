from __future__ import annotations

from types import SimpleNamespace

from app import shared
from app.assistant_memory import MemoryService, SQLiteMemoryRepository, resolve_chat_scope
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.chat.memory_commands import parse_memory_command


class FailingProvider:
    def chat_completion(self, **kwargs):
        raise AssertionError("recognized memory commands must not call the provider")


def setup_store(tmp_path):
    service = MemoryService(SQLiteMemoryRepository(tmp_path / "memory.sqlite3"))
    store = ChatSessionStore(tmp_path / "chat.json", memory_service_factory=lambda: service)
    session = store.create_session(
        CreateChatSessionRequest(
            title="Commands",
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
    return store, service, session, context


def test_parser_is_anchored_and_does_not_trigger_ordinary_discussion():
    assert parse_memory_command("I remember that we discussed this") is None
    assert parse_memory_command("Can you remember how caches work?") is None
    assert parse_memory_command("remember that the rpg branch is authoritative").kind == "save"
    explicit = parse_memory_command("save as workspace instruction: use exact-head CI")
    assert explicit.scope == "workspace"
    assert explicit.category == "instruction"
    assert parse_memory_command("forget exact-head CI").kind == "forget"
    assert parse_memory_command("refresh memory").kind == "refresh"
    assert parse_memory_command("start without memory").kind == "disable"


def test_non_streaming_save_list_refresh_and_disable_bypass_provider(monkeypatch, tmp_path):
    store, service, session, _ = setup_store(tmp_path)
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: FailingProvider())

    saved = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="save as workspace instruction: use exact-head CI"),
    )
    assert saved is not None
    saved_session, _ = saved
    assert "Saved as workspace instruction memory" in saved_session.messages[-1].content
    assert saved_session.messages[-1].metadata["memory_command"]["mutated"] is True

    listed = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="what do you remember?"),
    )
    assert "use exact-head CI" in listed[0].messages[-1].content

    refreshed = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="refresh memory"),
    )
    assert "snapshot revision 1" in refreshed[0].messages[-1].content
    assert store.get_session(session.id).memory_enabled is True

    disabled = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="disable memory for this chat"),
    )
    assert "Memory is disabled" in disabled[0].messages[-1].content
    assert store.get_session(session.id).memory_enabled is False
    assert len(service.list_active(resolve_chat_scope(session.id))) == 1


def test_forget_is_non_mutating_when_ambiguous_and_purges_unique_match(monkeypatch, tmp_path):
    store, service, session, context = setup_store(tmp_path)
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: FailingProvider())
    first = service.create_explicit_memory(
        context,
        scope="session",
        category="fact",
        content="Use local model alpha.",
        provenance_id="msg:a",
    )
    second = service.create_explicit_memory(
        context,
        scope="session",
        category="fact",
        content="Use local model beta.",
        provenance_id="msg:b",
    )

    ambiguous = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="forget local model"),
    )
    assert "More than one memory matched" in ambiguous[0].messages[-1].content
    assert service.repository.get_record(first.id) is not None
    assert service.repository.get_record(second.id) is not None

    unique = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="forget model alpha"),
    )
    assert "Forgot the matching memory" in unique[0].messages[-1].content
    assert service.repository.get_record(first.id) is None
    assert service.repository.get_record(second.id) is not None


def test_streaming_command_returns_deterministic_events_without_provider(monkeypatch, tmp_path):
    store, _, session, _ = setup_store(tmp_path)
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: FailingProvider())
    appended = store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="remember that streaming commands are deterministic"),
    )
    assert appended is not None
    active, user_message = appended

    events = list(
        store.stream_provider_reply_chunks(
            active,
            user_message,
            provider_id=active.provider_id,
            model_id=active.model_id,
        )
    )

    assert events[0]["type"] == "text_chunk"
    assert events[-1]["type"] == "complete"
    assert events[-1]["metadata"]["memory_command"]["command"] == "save"
    assert events[-1]["metadata"]["memory_command"]["mutated"] is True


def test_update_requires_an_available_exact_memory_id(monkeypatch, tmp_path):
    store, service, session, context = setup_store(tmp_path)
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: FailingProvider())
    record = service.create_explicit_memory(
        context,
        scope="session",
        category="fact",
        content="Old value.",
        provenance_id="msg:old",
    )

    updated = store.append_user_message(
        session.id,
        SendChatMessageRequest(content=f"update memory {record.id}: New value."),
    )
    assert "Updated the memory" in updated[0].messages[-1].content
    assert service.repository.get_record(record.id).content == "New value."

    unavailable = store.append_user_message(
        session.id,
        SendChatMessageRequest(content="update memory memory:missing: No value."),
    )
    assert "not available" in unavailable[0].messages[-1].content
