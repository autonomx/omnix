from __future__ import annotations

from contextvars import copy_context
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from app import shared
from app.chat.models import ChatMessage, ChatSession, SendChatMessageRequest
from app.gateway import live_chat_live_voice_profile as profile
from app.providers import ChatMessage as ProviderMessage
from app.providers import LMStudioProvider, ProviderConfig


def _session_with_long_history() -> tuple[ChatSession, ChatMessage]:
    now = "2026-07-19T00:00:00+00:00"
    messages: list[ChatMessage] = []
    for index in range(30):
        messages.append(
            ChatMessage(
                id=f"msg:{index}",
                role="user" if index % 2 == 0 else "assistant",
                content=f"Earlier turn {index}",
                created_at=now,
                metadata={},
            )
        )
    current = ChatMessage(
        id="msg:current",
        role="user",
        content="Answer quickly.",
        created_at=now,
        metadata={
            "user_turn_id": "voice-user-turn:test",
            "speech_segment_id": "voice-segment:test",
        },
    )
    messages.append(current)
    session = ChatSession(
        id="chat:test",
        title="Voice test",
        message_count=len(messages),
        messages=messages,
        created_at=now,
        updated_at=now,
    )
    return session, current


def test_browser_live_turn_marker_derives_existing_request_ids() -> None:
    request = SendChatMessageRequest.model_validate(
        {
            "content": "Hello",
            "live_voice_turn_id": "voice-turn:12345",
        }
    )

    assert request.user_turn_id == "voice-user-turn:voice-turn:12345"
    assert request.speech_segment_id == "voice-segment:voice-turn:12345"


def test_live_voice_prompt_bounds_history_and_skips_cross_session_recall(monkeypatch) -> None:
    session, current = _session_with_long_history()
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    monkeypatch.setattr(
        profile,
        "resolve_prompt_memory",
        lambda session, memory_service_factory: ([], {"memory_enabled": False}),
    )
    monkeypatch.setattr(profile, "compaction_enabled", lambda: False)
    store = SimpleNamespace(
        memory_service_factory=lambda: None,
        summary_repository_factory=lambda: (_ for _ in ()).throw(
            AssertionError("summary lookup should be disabled")
        ),
    )

    assembly, rendered = profile._build_live_voice_prompt(
        store,
        session,
        current,
        [],
    )

    latency = assembly.diagnostics["latency_profile"]
    assert latency["name"] == "live_voice"
    assert latency["recent_message_limit"] == 12
    assert latency["max_input_tokens"] == 12_288
    assert latency["history_tokens"] == 0
    assert assembly.diagnostics["recent_message_count"] == 12
    assert assembly.diagnostics["history_recall"] == {
        "enabled": False,
        "retrieved_count": 0,
        "reason": "live_voice_latency_profile",
    }
    assert rendered.diagnostics.estimated_tokens <= latency["max_input_tokens"]
    assert rendered.messages[-1].content == "Answer quickly."


def test_lmstudio_live_voice_disables_thinking_without_affecting_text_chat(monkeypatch) -> None:
    provider = LMStudioProvider(
        ProviderConfig(
            provider_type="lmstudio",
            base_url="http://localhost:1234",
            model="qwen",
        )
    )
    payloads: list[dict[str, Any]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload
            self.headers: dict[str, str] = {}
            self.content = b"{}"

        def json(self) -> dict[str, Any]:
            return self.payload

    def fake_make_request(method: str, endpoint: str, **kwargs: Any) -> FakeResponse:
        if endpoint == "/api/v1/models":
            return FakeResponse(
                {
                    "models": [
                        {
                            "key": "qwen",
                            "display_name": "qwen",
                            "loaded_instances": [{"id": "qwen", "config": {}}],
                        }
                    ]
                }
            )
        payloads.append(dict(kwargs["json"]))
        return FakeResponse(
            {
                "model": "qwen",
                "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
                "usage": {},
            }
        )

    monkeypatch.setattr(provider, "_make_request", fake_make_request)

    token = profile._LIVE_VOICE_TURN.set(True)
    try:
        provider.chat_completion(
            [ProviderMessage(role="user", content="Hello")],
            stream=False,
        )
    finally:
        profile._LIVE_VOICE_TURN.reset(token)

    provider.chat_completion(
        [ProviderMessage(role="user", content="Hello")],
        stream=False,
    )

    assert payloads[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in payloads[1]


def test_live_voice_stream_can_advance_across_copied_contexts() -> None:
    observed_context: list[bool] = []

    def source() -> Iterator[dict[str, Any]]:
        observed_context.append(profile._LIVE_VOICE_TURN.get())
        yield {"type": "chunk", "text": "Hello"}
        observed_context.append(profile._LIVE_VOICE_TURN.get())
        yield {"type": "complete"}
        observed_context.append(profile._LIVE_VOICE_TURN.get())

    stream = profile._stream_with_live_voice_context(
        source(),
        is_live_voice=True,
    )

    assert copy_context().run(next, stream) == {"type": "chunk", "text": "Hello"}
    assert profile._LIVE_VOICE_TURN.get() is False
    assert copy_context().run(next, stream) == {"type": "complete"}
    assert profile._LIVE_VOICE_TURN.get() is False
    with pytest.raises(StopIteration):
        copy_context().run(next, stream)

    assert observed_context == [True, True, True]
    assert profile._LIVE_VOICE_TURN.get() is False
