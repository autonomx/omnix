from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from app.chat.models import ChatMessage, ChatSession, SendChatMessageRequest
from app.gateway import live_chat_postgres_fast_path as fast_path
from app.persistence import chat_runtime_compat


NOW = "2026-07-18T00:00:00+00:00"


def _session() -> ChatSession:
    return ChatSession(
        id="chat:test",
        title="New chat",
        provider_id="llm:old-provider",
        model_id="llm:old-provider:old-model",
        active_segment_id="segment:test",
        messages=[],
        created_at=NOW,
        updated_at=NOW,
    )


def test_load_single_session_avoids_workspace_scan(monkeypatch) -> None:
    session = _session()

    class FakeChats:
        def __init__(self) -> None:
            self.get_calls = 0
            self.list_message_calls = 0

        def get_session(self, context: object, session_id: str) -> dict[str, Any]:
            self.get_calls += 1
            assert session_id == session.id
            return {"id": session.id}

        def list_messages(
            self,
            context: object,
            session_id: str,
            *,
            limit: int,
            after_position: int,
        ) -> list[dict[str, Any]]:
            self.list_message_calls += 1
            assert session_id == session.id
            assert limit == 500
            assert after_position == -1
            return []

        def list_sessions(self, *args: object, **kwargs: object) -> list[dict[str, Any]]:
            raise AssertionError("fast path must not scan all sessions")

    class FakeWork:
        def __init__(self) -> None:
            self.chats = FakeChats()
            self.rolled_back = False

        def rollback(self) -> None:
            self.rolled_back = True

    work = FakeWork()

    @contextmanager
    def fake_unit_of_work(database: object):
        yield work

    adapter = SimpleNamespace(
        database=object(),
        context=object(),
        _to_session=lambda record, messages: session,
    )
    store = SimpleNamespace(_repository=adapter)
    monkeypatch.setattr(fast_path, "unit_of_work", fake_unit_of_work)

    loaded = fast_path._load_single_session(store, session.id)

    assert loaded is session
    assert work.chats.get_calls == 1
    assert work.chats.list_message_calls == 1
    assert work.rolled_back is True


def test_begin_user_message_persists_one_targeted_turn(monkeypatch) -> None:
    session = _session()
    persisted: list[tuple[ChatSession, object]] = []

    def fake_load(store: object, session_id: str) -> ChatSession:
        assert session_id == session.id
        return session

    def fake_persist(store: object, current: ChatSession, message: object) -> bool:
        persisted.append((current, message))
        return True

    class FakeTurn:
        user_turn_id = "voice-user-turn:test"
        speech_segment_id = "voice-segment:test"
        assistant_turn_id = "assistant-turn:test"

        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {
                "user_turn_id": self.user_turn_id,
                "speech_segment_id": self.speech_segment_id,
                "assistant_turn_id": self.assistant_turn_id,
            }

    def fake_start(
        current: ChatSession,
        message: object,
        request: SendChatMessageRequest,
    ) -> FakeTurn:
        turn = FakeTurn()
        message.metadata.update(
            {
                "user_turn_id": turn.user_turn_id,
                "speech_segment_id": turn.speech_segment_id,
                "assistant_turn_id": turn.assistant_turn_id,
                "assistant_turn": turn.model_dump(mode="json"),
            }
        )
        return turn

    monkeypatch.setattr(fast_path, "_load_single_session", fake_load)
    monkeypatch.setattr(fast_path, "_persist_user_turn", fake_persist)
    monkeypatch.setattr(fast_path, "_start_assistant_turn", fake_start)
    monkeypatch.setattr(fast_path, "stream_log", lambda *args, **kwargs: None)

    request = SendChatMessageRequest(
        content="Hello from live voice",
        provider_id="llm:lmstudio",
        model_id="llm:lmstudio:qwen",
        user_turn_id="voice-user-turn:test",
        speech_segment_id="voice-segment:test",
        workspace_root="F:/LLM/omnix",
    )
    store = SimpleNamespace()

    result = fast_path._begin_user_message_fast(store, session.id, request)

    assert result is not None
    returned_session, message = result
    assert returned_session is session
    assert len(persisted) == 1
    assert persisted[0] == (session, message)
    assert session.title == "Hello from live voice"
    assert session.provider_id == "llm:lmstudio"
    assert session.model_id == "llm:lmstudio:qwen"
    assert session.message_count == 1
    assert message.metadata["generation_status"] == "running"
    assert message.metadata["segment_id"] == "segment:test"
    assert message.metadata["assistant_turn_id"] == "assistant-turn:test"
    assert message.metadata["workspace_root"] == "F:/LLM/omnix"

    duplicate = fast_path._begin_user_message_fast(store, session.id, request)

    assert duplicate is not None
    assert duplicate[0] is session
    assert duplicate[1] is message
    assert len(persisted) == 1


def test_assistant_completion_is_targeted_and_idempotent(monkeypatch) -> None:
    session = _session()
    user_message = ChatMessage(
        id="msg:user",
        role="user",
        content="Hello",
        created_at=NOW,
        metadata={
            "generation_status": "running",
            "assistant_turn_id": "assistant-turn:test",
        },
    )
    session.messages = [user_message]
    session.message_count = 1

    class Result:
        def __init__(self, row: tuple[str] | None) -> None:
            self.row = row

        def fetchone(self) -> tuple[str] | None:
            return self.row

    class FakeConnection:
        def __init__(self) -> None:
            self.assistant_exists = False
            self.user_metadata_json = ""
            self.session_updates = 0

        def execute(self, statement: str, params: tuple[Any, ...]) -> Result:
            normalized = " ".join(statement.split())
            if normalized.startswith("UPDATE omnix_chat_messages"):
                self.user_metadata_json = str(params[0])
                return Result((user_message.id,))
            if normalized.startswith("SELECT id FROM omnix_chat_messages"):
                return Result(("msg:assistant",) if self.assistant_exists else None)
            if normalized.startswith("UPDATE omnix_chat_sessions"):
                self.session_updates += 1
                return Result(None)
            raise AssertionError(normalized)

    connection = FakeConnection()

    class FakeChats:
        def __init__(self) -> None:
            self.appended: list[dict[str, Any]] = []

        def append_message(
            self,
            context: object,
            session_id: str,
            payload: dict[str, Any],
        ) -> None:
            assert session_id == session.id
            self.appended.append(payload)
            connection.assistant_exists = True

    class FakeWork:
        def __init__(self) -> None:
            self.connection = connection
            self.chats = FakeChats()
            self.commits = 0
            self.rollbacks = 0

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

    work = FakeWork()

    @contextmanager
    def fake_unit_of_work(database: object):
        yield work

    adapter = SimpleNamespace(
        database=object(),
        context=SimpleNamespace(workspace_id="workspace:test"),
    )
    store = SimpleNamespace(_repository=adapter)
    monkeypatch.setattr(fast_path, "unit_of_work", fake_unit_of_work)

    first = fast_path._persist_assistant_completion(
        store,
        session,
        user_message,
        content="Assistant answer.",
        metadata={"generation_status": "completed"},
        assistant_turn_id="assistant-turn:test",
        generation_status="completed",
        assistant_turn_payload={"lifecycle": "completed"},
    )
    second = fast_path._persist_assistant_completion(
        store,
        session,
        user_message,
        content="Assistant answer.",
        metadata={"generation_status": "completed"},
        assistant_turn_id="assistant-turn:test",
        generation_status="completed",
        assistant_turn_payload={"lifecycle": "completed"},
    )

    assert first == (True, False)
    assert second == (False, True)
    assert len(work.chats.appended) == 1
    assistant = work.chats.appended[0]
    assert assistant["id"] == fast_path._assistant_message_id(session.id, user_message.id)
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "Assistant answer."
    assert assistant["metadata"]["assistant_turn_id"] == "assistant-turn:test"
    assert assistant["metadata"]["segment_id"] == "segment:test"
    persisted_user_metadata = json.loads(connection.user_metadata_json)
    assert persisted_user_metadata["generation_status"] == "completed"
    assert persisted_user_metadata["assistant_turn"]["lifecycle"] == "completed"
    assert work.commits == 2
    assert work.rollbacks == 0
    assert connection.session_updates == 1


def test_complete_streamed_reply_avoids_compatibility_save(monkeypatch) -> None:
    session = _session()
    user_message = ChatMessage(
        id="msg:user",
        role="user",
        content="Hello",
        created_at=NOW,
        metadata={"assistant_turn_id": "assistant-turn:test"},
    )
    session.messages = [user_message]
    session.message_count = 1
    maintenance: list[str] = []
    events: list[str] = []

    class FakeTurn:
        terminal = False
        lifecycle = "streaming"

        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {"lifecycle": self.lifecycle}

    class FakeCoordinator:
        def __init__(self) -> None:
            self.turn = FakeTurn()

        def get(self, assistant_turn_id: str) -> FakeTurn:
            assert assistant_turn_id == "assistant-turn:test"
            return self.turn

        def try_complete(self, assistant_turn_id: str) -> bool:
            assert assistant_turn_id == "assistant-turn:test"
            self.turn.terminal = True
            self.turn.lifecycle = "completed"
            return True

        def mark_provider_cancelled(self, assistant_turn_id: str) -> None:
            raise AssertionError("completed output must not be cancelled")

    coordinator = FakeCoordinator()

    def fake_load(store: object, session_id: str) -> ChatSession:
        assert session_id == session.id
        return session

    def fake_persist(
        store: object,
        current: ChatSession,
        current_user: ChatMessage,
        **kwargs: Any,
    ) -> tuple[bool, bool]:
        assert current is session
        assert current_user is user_message
        return True, False

    monkeypatch.setattr(fast_path, "_load_single_session", fake_load)
    monkeypatch.setattr(fast_path, "_persist_assistant_completion", fake_persist)
    monkeypatch.setattr(
        fast_path,
        "default_assistant_turn_coordinator",
        lambda: coordinator,
    )
    monkeypatch.setattr(
        fast_path,
        "stream_log",
        lambda stream_id, source, event, **details: events.append(event),
    )
    store = SimpleNamespace(
        _run_post_turn_maintenance=lambda current, message_id: maintenance.append(
            message_id
        ),
        _save_sessions=lambda sessions: (_ for _ in ()).throw(
            AssertionError("compatibility save must not run")
        ),
    )

    result = fast_path._complete_streamed_reply_fast(
        store,
        session.id,
        user_message.id,
        "Assistant answer.",
        {"generation_status": "completed"},
    )

    assert result is session
    assert session.message_count == 2
    assert maintenance == [user_message.id]
    assert events == ["live_chat_assistant_completion_fast_path_completed"]


def test_live_session_mutation_allows_different_sessions_to_proceed() -> None:
    """The PostgreSQL path must not inherit the file-store global mutex."""
    import threading

    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def hold_first() -> None:
        with fast_path._live_session_mutation("chat:first"):
            first_entered.set()
            assert release_first.wait(timeout=1)

    thread = threading.Thread(target=hold_first)
    thread.start()
    assert first_entered.wait(timeout=1)
    with fast_path._live_session_mutation("chat:second"):
        second_entered.set()
    release_first.set()
    thread.join(timeout=1)

    assert second_entered.is_set()
    assert not thread.is_alive()


def test_default_postgres_chat_services_are_process_resident(monkeypatch) -> None:
    created_history: list[object] = []
    created_stores: list[object] = []

    class FakeHistorySearchService:
        def __init__(self) -> None:
            created_history.append(self)

    class FakeChatStore:
        def __init__(self, *, history_search_factory) -> None:
            self.history_search_factory = history_search_factory
            created_stores.append(self)

    chat_runtime_compat.reset_default_chat_runtime_caches()
    monkeypatch.setattr(
        chat_runtime_compat,
        "PostgresHistorySearchService",
        FakeHistorySearchService,
    )
    monkeypatch.setattr(
        chat_runtime_compat,
        "PostgresCharacterChatSessionStore",
        FakeChatStore,
    )

    try:
        first_history = chat_runtime_compat.default_history_search_service()
        second_history = chat_runtime_compat.default_history_search_service()
        first_store = chat_runtime_compat.default_chat_store()
        second_store = chat_runtime_compat.default_chat_store()

        assert first_history is second_history
        assert first_store is second_store
        assert first_store.history_search_factory() is first_history
        assert created_history == [first_history]
        assert created_stores == [first_store]
    finally:
        chat_runtime_compat.reset_default_chat_runtime_caches()
