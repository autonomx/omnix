from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from app.chat.models import ChatSession, SendChatMessageRequest
from app.gateway import live_chat_postgres_fast_path as fast_path


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

    def fake_start(current: ChatSession, message: object, request: SendChatMessageRequest) -> FakeTurn:
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

    duplicate = fast_path._begin_user_message_fast(store, session.id, request)

    assert duplicate is not None
    assert duplicate[0] is session
    assert duplicate[1] is message
    assert len(persisted) == 1
