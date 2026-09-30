from __future__ import annotations

from contextvars import copy_context
from typing import Any, Iterator

import pytest

from app.chat.models import ChatMessage, ChatSession, SendChatMessageRequest
from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore
from app.live_voice import pipeline as live_voice_pipeline
from app.live_voice.prompt import profile
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


def test_prompt_store_selects_feature_pipeline_for_live_voice(monkeypatch) -> None:
    session, current = _session_with_long_history()
    expected = (object(), object())
    observed: list[tuple[object, object, object, object]] = []

    def build(store, routed_session, user_message, context_items):
        observed.append((store, routed_session, user_message, context_items))
        return expected

    monkeypatch.setattr(live_voice_pipeline, "build_live_voice_prompt", build)
    store = object()

    result = PromptChatSessionStore.build_provider_prompt(
        store,
        session,
        current,
        [],
    )

    assert result is expected
    assert observed == [(store, session, current, [])]


def test_live_voice_prompt_policy_bounds_history_budget() -> None:
    assert profile._live_voice_recent_message_limit() == 12

    budget = profile._live_voice_prompt_budget()

    assert budget.max_input_tokens == 12_288
    assert budget.reserved_output_tokens == 1_024
    assert budget.memory_tokens <= 1_000
    assert budget.summary_tokens <= 2_000
    assert budget.history_tokens == 0
    assert budget.external_context_tokens <= 2_048


def test_lmstudio_live_voice_disables_thinking_without_affecting_text_chat(monkeypatch) -> None:
    profile._install_lmstudio_thinking_policy()
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
