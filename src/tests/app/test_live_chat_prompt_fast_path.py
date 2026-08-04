from __future__ import annotations

from types import SimpleNamespace

from app.chat.models import ChatMessage, ChatSession
from app.gateway import live_chat_prompt_fast_path as fast_path


def _session(*, memory_enabled: bool = False) -> ChatSession:
    messages = [
        ChatMessage(
            id=f"message-{index}",
            role="user" if index % 2 == 0 else "assistant",
            content=f"turn {index}",
            created_at=f"2026-08-03T00:00:{index:02d}+00:00",
        )
        for index in range(20)
    ]
    return ChatSession(
        id="session-fast",
        title="Fast prompt",
        provider_id="fake",
        model_id="fake-model",
        memory_enabled=memory_enabled,
        message_count=len(messages),
        messages=messages,
        created_at="2026-08-03T00:00:00+00:00",
        updated_at="2026-08-03T00:00:20+00:00",
    )


def test_live_prompt_fast_path_bounds_recent_turns_and_preserves_context(monkeypatch) -> None:
    monkeypatch.setattr(fast_path, "history_recall_enabled", lambda: False)
    monkeypatch.setattr(fast_path, "compaction_enabled", lambda: False)
    monkeypatch.setattr(fast_path.shared, "get_global_system_prompt", lambda: "System prompt")
    fallback_calls = []
    store = SimpleNamespace(
        build_provider_prompt=lambda *args: fallback_calls.append(args),
    )
    user_message = ChatMessage(
        id="current-user",
        role="user",
        content="answer quickly",
        created_at="2026-08-03T00:01:00+00:00",
    )

    assembly, rendered = fast_path.build_live_provider_prompt(
        store,
        _session(),
        user_message,
        [{"source_id": "screen", "title": "Screen", "content": "Visible state"}],
    )

    assert fallback_calls == []
    assert len(assembly.recent_messages) == fast_path.LIVE_PROMPT_RECENT_MESSAGE_LIMIT
    assert assembly.recent_messages[0].content == "turn 8"
    assert assembly.current_user_message.content == "answer quickly"
    assert assembly.external_context[0].content == "Visible state"
    assert assembly.diagnostics["live_prompt_fast_path"]["enabled"] is True
    assert assembly.diagnostics["memory"]["memory_enabled"] is False
    assert rendered.messages[-1].content.endswith("answer quickly")


def test_live_prompt_fast_path_falls_back_when_memory_is_active(monkeypatch) -> None:
    monkeypatch.setattr(fast_path, "history_recall_enabled", lambda: False)
    monkeypatch.setattr(fast_path, "compaction_enabled", lambda: False)
    expected = (SimpleNamespace(name="assembly"), SimpleNamespace(name="rendered"))
    calls = []

    def build_provider_prompt(*args):
        calls.append(args)
        return expected

    user_message = ChatMessage(
        id="current-user",
        role="user",
        content="remember this",
        created_at="2026-08-03T00:01:00+00:00",
    )
    result = fast_path.build_live_provider_prompt(
        SimpleNamespace(build_provider_prompt=build_provider_prompt),
        _session(memory_enabled=True),
        user_message,
        [],
    )

    assert result == expected
    assert len(calls) == 1
