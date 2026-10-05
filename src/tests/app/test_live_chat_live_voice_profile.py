from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.platform.chat.models import ChatMessage, ChatSession
from app.platform.live_voice import pipeline as live_voice_pipeline
from app.platform.live_voice.chat_integration import create_live_voice_chat_port
from app.platform.live_voice.llm import metrics as live_voice_metrics
from app.platform.live_voice.llm import stream as live_voice_stream
from app.platform.live_voice.prompt import profile
from app.providers import ChatMessage as ProviderMessage
from app.providers import LMStudioProvider, ProviderConfig


def _session_with_long_history() -> tuple[ChatSession, ChatMessage]:
    now = "2026-07-19T00:00:00+00:00"
    messages = [
        ChatMessage(
            id=f"msg:{index}",
            role="user" if index % 2 == 0 else "assistant",
            content=f"Earlier turn {index}",
            created_at=now,
            metadata={},
        )
        for index in range(30)
    ]
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


def test_live_turn_profile_bounds_history_and_prompt_budget() -> None:
    assert profile._live_voice_recent_message_limit() == 12

    budget = profile._live_voice_prompt_budget()

    assert budget.max_input_tokens == 12_288
    assert budget.reserved_output_tokens == 1_024
    assert budget.memory_tokens <= 1_000
    assert budget.summary_tokens <= 2_000
    assert budget.history_tokens == 0
    assert budget.external_context_tokens <= 2_048


def test_prompt_store_selects_feature_pipeline_for_live_voice(monkeypatch) -> None:
    from app.platform.chat.prompt_store import ChatSessionStore

    session, current = _session_with_long_history()
    expected = (object(), object())
    observed: list[tuple[object, object, object, object]] = []

    def build(store, routed_session, user_message, context_items):
        observed.append((store, routed_session, user_message, context_items))
        return expected

    monkeypatch.setattr(live_voice_pipeline, "build_live_voice_prompt", build)
    store = ChatSessionStore(live_voice_chat_port=create_live_voice_chat_port())

    result = ChatSessionStore.build_provider_prompt(
        store,
        session,
        current,
        [],
    )

    assert result is expected
    assert observed == [(store, session, current, [])]


def test_lmstudio_live_voice_policy_is_applied_at_completion_boundary(monkeypatch) -> None:
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

    class PromptStore:
        def build_provider_prompt(self, _session, _message, _context_items):
            return SimpleNamespace(diagnostics={}), SimpleNamespace(
                messages=[ProviderMessage(role="user", content="Hello")]
            )

        def _active_memory_metadata(self, _assembly, _rendered):
            return {}

        def _active_history_metadata(self, _assembly):
            return {}

    store = PromptStore()
    session = SimpleNamespace(id="chat:test", provider_id="lmstudio")
    voice_message = ChatMessage(
        id="msg:voice",
        role="user",
        content="Hello",
        created_at="2026-07-19T00:00:00+00:00",
        metadata={"user_turn_id": "voice-user-turn:test"},
    )
    text_message = ChatMessage(
        id="msg:text",
        role="user",
        content="Hello",
        created_at="2026-07-19T00:00:00+00:00",
        metadata={},
    )

    live_voice_metrics.generate_lmstudio_reply(
        store,
        session,
        voice_message,
        provider_id="lmstudio",
        model_id="qwen",
        context_items=[],
        provider=provider,
    )
    live_voice_metrics.generate_lmstudio_reply(
        store,
        session,
        text_message,
        provider_id="lmstudio",
        model_id="qwen",
        context_items=[],
        provider=provider,
    )

    assert payloads[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in payloads[1]


def test_live_voice_provider_stream_observer_forwards_raw_chunks(monkeypatch) -> None:
    log_events: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    closed: list[bool] = []

    def source():
        try:
            yield SimpleNamespace(
                content="Hello",
                raw_response={"stats": {"output_tokens": 3}},
            )
        finally:
            closed.append(True)

    monkeypatch.setattr(
        live_voice_stream,
        "stream_log",
        lambda *args, **kwargs: log_events.append((args, kwargs)),
    )

    chunks = list(live_voice_stream.observe_live_voice_provider_stream(source()))

    assert chunks[0].content == "Hello"
    assert closed == [True]
    assert any(
        args[2] == "live_voice_raw_provider_stream_metrics"
        for args, _kwargs in log_events
    )
