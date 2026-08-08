from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.gateway import live_chat_lmstudio_diagnostics as diagnostics
from app.gateway import live_chat_lmstudio_responses as responses_runtime
from app.providers.base import ChatMessage, ProviderConfig
from app.providers.lmstudio_provider import LMStudioProvider


class _FakeLmStudioResponse:
    def __init__(
        self,
        *,
        json_payload: dict[str, Any] | None = None,
        lines: list[str] | None = None,
    ) -> None:
        self._json_payload = json_payload or {}
        self._lines = lines or []
        self.closed = False

    def json(self) -> dict[str, Any]:
        return self._json_payload

    def iter_lines(self):
        yield from self._lines

    def close(self) -> None:
        self.closed = True


def _lmstudio_provider() -> LMStudioProvider:
    return LMStudioProvider(
        ProviderConfig(
            provider_type="lmstudio",
            base_url="http://localhost:1234",
            model="test-model",
        )
    )


def test_channel_error_is_normalized_without_raw_prompt_content() -> None:
    code, summary = diagnostics._classify_lmstudio_error(
        RuntimeError("Unexpected error: Channel Error")
    )

    assert code == "lmstudio_channel_error"
    assert summary == "LM Studio inference channel closed."
    assert "Unexpected" not in summary


def test_nonstream_success_logs_prompt_size_and_provider_metrics(monkeypatch) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        diagnostics,
        "stream_log",
        lambda stream_id, source, event, **fields: events.append((event, fields)),
    )

    provider = SimpleNamespace(config=SimpleNamespace(model="gemma-4-e4b"))
    session = SimpleNamespace(
        messages=[SimpleNamespace(content="old message") for _ in range(93)]
    )
    user_message = SimpleNamespace(content="Hello")

    def original(*args: Any, **kwargs: Any) -> dict[str, Any]:
        active = diagnostics._ACTIVE_CALL.get()
        assert active is not None
        active.update(
            {
                "rendered_message_count": 12,
                "prompt_chars": 4_800,
                "estimated_input_tokens": 1_200,
                "usable_input_tokens": 12_288,
                "truncated_sections": ["recent_messages"],
                "recent_message_count": 10,
            }
        )
        return {
            "content": "Hello back",
            "metadata": {
                "provider_metrics": {
                    "input_tokens": 1_210,
                    "output_tokens": 8,
                    "tokens_per_second": 88.5,
                }
            },
        }

    result = diagnostics._run_lmstudio_nonstream_diagnostics(
        original,
        SimpleNamespace(),
        session,
        user_message,
        provider_id="lmstudio",
        model_id=None,
        context_items=[],
        provider=provider,
    )

    assert result["content"] == "Hello back"
    assert [event for event, _ in events] == [
        "live_chat_lmstudio_nonstream_started",
        "live_chat_lmstudio_nonstream_completed",
    ]
    completed = events[-1][1]
    assert completed["model_id"] == "gemma-4-e4b"
    assert completed["session_message_count"] == 93
    assert completed["rendered_message_count"] == 12
    assert completed["estimated_input_tokens"] == 1_200
    assert completed["input_tokens"] == 1_210
    assert completed["response_chars"] == 10


def test_nonstream_failure_logs_normalized_channel_error(monkeypatch) -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        diagnostics,
        "stream_log",
        lambda stream_id, source, event, **fields: events.append((event, fields)),
    )

    provider = SimpleNamespace(config=SimpleNamespace(model="qwen3.5-0.8b"))

    def original(*args: Any, **kwargs: Any) -> dict[str, Any]:
        active = diagnostics._ACTIVE_CALL.get()
        assert active is not None
        active.update(
            {
                "rendered_message_count": 93,
                "prompt_chars": 22_000,
                "estimated_input_tokens": 5_500,
                "usable_input_tokens": 61_440,
                "truncated_sections": [],
                "recent_message_count": 91,
            }
        )
        raise RuntimeError("Unexpected error: Channel Error")

    with pytest.raises(RuntimeError, match="Channel Error"):
        diagnostics._run_lmstudio_nonstream_diagnostics(
            original,
            SimpleNamespace(),
            SimpleNamespace(messages=[object()] * 93),
            SimpleNamespace(content="Hello"),
            provider_id="lmstudio",
            model_id=None,
            context_items=[],
            provider=provider,
        )

    assert [event for event, _ in events] == [
        "live_chat_lmstudio_nonstream_started",
        "live_chat_lmstudio_nonstream_failed",
    ]
    failed = events[-1][1]
    assert failed["model_id"] == "qwen3.5-0.8b"
    assert failed["session_message_count"] == 93
    assert failed["estimated_input_tokens"] == 5_500
    assert failed["error_code"] == "lmstudio_channel_error"
    assert failed["error_summary"] == "LM Studio inference channel closed."
    assert "Channel Error" not in failed["error_summary"]


def test_native_v1_chat_is_opt_in_stateless_and_exposes_native_stats(monkeypatch) -> None:
    provider = _lmstudio_provider()
    captured: dict[str, Any] = {}
    response = _FakeLmStudioResponse(
        json_payload={
            "model_instance_id": "liquid/lfm2.5-1.2b",
            "output": [{"type": "message", "content": "Hello back"}],
            "stats": {
                "input_tokens": 120,
                "total_output_tokens": 5,
                "tokens_per_second": 91.5,
                "time_to_first_token_seconds": 0.081,
            },
        }
    )

    def fake_request(method: str, endpoint: str, **kwargs: Any):
        captured.update({"method": method, "endpoint": endpoint, **kwargs})
        return response

    monkeypatch.setattr(provider, "_make_request", fake_request)
    result = provider.chat_completion(
        messages=[
            ChatMessage(role="system", content="Be concise."),
            ChatMessage(role="user", content="Hello"),
        ],
        model="test-model",
        stream=False,
        _lmstudio_native_v1=True,
        chat_template_kwargs={"enable_thinking": False},
    )

    assert result.content == "Hello back"
    assert result.model == "liquid/lfm2.5-1.2b"
    assert result.usage == {
        "prompt_tokens": 120,
        "completion_tokens": 5,
        "total_tokens": 125,
    }
    assert result.raw_response["stats"]["time_to_first_token_seconds"] == 0.081
    assert captured["endpoint"] == "/api/v1/chat"
    assert captured["json"] == {
        "input": "Hello",
        "stream": False,
        "store": False,
        "temperature": 0.7,
        "model": "test-model",
        "system_prompt": "Be concise.",
        "reasoning": "off",
    }


def test_native_v1_stream_continues_from_response_id_and_keeps_final_stats(monkeypatch) -> None:
    provider = _lmstudio_provider()
    captured: dict[str, Any] = {}
    response = _FakeLmStudioResponse(
        lines=[
            'event: chat.start',
            'data: {"type":"chat.start","model_instance_id":"test-model"}',
            'event: prompt_processing.start',
            'data: {"type":"prompt_processing.start"}',
            'event: message.delta',
            'data: {"type":"message.delta","content":"Fast "}',
            'event: message.delta',
            'data: {"type":"message.delta","content":"reply"}',
            'event: chat.end',
            'data: {"type":"chat.end","result":{"model_instance_id":"test-model","output":[{"type":"message","content":"Fast reply"}],"stats":{"input_tokens":24,"total_output_tokens":2,"tokens_per_second":100.0,"time_to_first_token_seconds":0.05},"response_id":"resp_next"}}',
        ]
    )

    def fake_request(method: str, endpoint: str, **kwargs: Any):
        captured.update({"method": method, "endpoint": endpoint, **kwargs})
        return response

    monkeypatch.setattr(provider, "_make_request", fake_request)
    chunks = list(
        provider.chat_completion(
            messages=[ChatMessage(role="user", content="Continue")],
            model="test-model",
            stream=True,
            _lmstudio_native_v1=True,
            _lmstudio_store=True,
            _lmstudio_previous_response_id="resp_previous",
        )
    )

    assert [chunk.content for chunk in chunks] == ["Fast ", "reply", ""]
    assert chunks[-1].usage == {
        "prompt_tokens": 24,
        "completion_tokens": 2,
        "total_tokens": 26,
    }
    assert chunks[-1].raw_response["response_id"] == "resp_next"
    assert captured["json"]["store"] is True
    assert captured["json"]["previous_response_id"] == "resp_previous"
    assert captured["json"]["input"] == "Continue"
    assert response.closed is True


def test_native_v1_refuses_to_silently_flatten_assistant_history() -> None:
    provider = _lmstudio_provider()

    with pytest.raises(ValueError, match="cannot seed assistant/tool history"):
        provider.chat_completion(
            messages=[
                ChatMessage(role="user", content="One"),
                ChatMessage(role="assistant", content="Two"),
                ChatMessage(role="user", content="Three"),
            ],
            model="test-model",
            stream=False,
            _lmstudio_native_v1=True,
        )


def test_responses_transport_seeds_assistant_history_and_preserves_cached_usage(
    monkeypatch,
) -> None:
    provider = _lmstudio_provider()
    captured: dict[str, Any] = {}
    response = _FakeLmStudioResponse(
        lines=[
            'event: response.created',
            'data: {"type":"response.created","response":{"id":"resp_seed","model":"test-model"}}',
            'event: response.output_text.delta',
            'data: {"type":"response.output_text.delta","delta":"Okay"}',
            'event: response.completed',
            'data: {"type":"response.completed","response":{"id":"resp_seed","model":"test-model","usage":{"input_tokens":1200,"output_tokens":4,"total_tokens":1204,"input_tokens_details":{"cached_tokens":900}}}}',
        ]
    )

    def fake_request(method: str, endpoint: str, **kwargs: Any):
        captured.update({"method": method, "endpoint": endpoint, **kwargs})
        return response

    monkeypatch.setattr(provider, "_make_request", fake_request)
    chunks = list(
        responses_runtime._stream_responses(
            provider,
            messages=[
                ChatMessage(role="system", content="Stay in character."),
                ChatMessage(role="user", content="Hello"),
                ChatMessage(role="assistant", content="Hi."),
                ChatMessage(role="user", content="Continue"),
            ],
            model="test-model",
            previous_response_id=None,
        )
    )

    assert [chunk.content for chunk in chunks] == ["Okay", ""]
    assert chunks[-1].usage == {
        "input_tokens": 1200,
        "output_tokens": 4,
        "total_tokens": 1204,
        "input_tokens_details": {"cached_tokens": 900},
    }
    assert chunks[-1].raw_response["id"] == "resp_seed"
    assert captured["endpoint"] == "/v1/responses"
    assert captured["json"]["store"] is True
    assert captured["json"]["input"] == [
        {"role": "system", "content": "Stay in character."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi."},
        {"role": "user", "content": "Continue"},
    ]
    assert response.closed is True


def test_responses_continuation_sends_only_new_user_input() -> None:
    payload = responses_runtime._responses_payload(
        messages=[ChatMessage(role="user", content="Next question")],
        model="test-model",
        previous_response_id="resp_previous",
        stream=True,
    )

    assert payload["input"] == "Next question"
    assert payload["previous_response_id"] == "resp_previous"
    assert payload["model"] == "test-model"
    assert payload["store"] is True


def test_response_state_reuses_only_exact_prompt_prefix_and_model() -> None:
    responses_runtime._clear_response_states_for_tests()
    request_messages = [
        ChatMessage(role="system", content="Persona v1"),
        ChatMessage(role="user", content="First"),
    ]
    assert responses_runtime._remember_response_state(
        session_id="chat-one",
        model_id="test-model",
        request_messages=request_messages,
        assistant_text="Answer one",
        response_id="resp_one",
    ) is True

    next_messages = [
        *request_messages,
        ChatMessage(role="assistant", content="Answer one"),
        ChatMessage(role="user", content="Second"),
    ]
    response_id, reason = responses_runtime._resolve_previous_response_id(
        session_id="chat-one",
        model_id="test-model",
        messages=next_messages,
    )
    assert (response_id, reason) == ("resp_one", "hit")

    changed_prompt = [
        ChatMessage(role="system", content="Persona v2"),
        *next_messages[1:],
    ]
    response_id, reason = responses_runtime._resolve_previous_response_id(
        session_id="chat-one",
        model_id="test-model",
        messages=changed_prompt,
    )
    assert response_id is None
    assert reason == "prompt_prefix_changed"


def test_response_state_invalidates_when_loaded_model_changes() -> None:
    responses_runtime._clear_response_states_for_tests()
    request_messages = [
        ChatMessage(role="system", content="Persona"),
        ChatMessage(role="user", content="First"),
    ]
    responses_runtime._remember_response_state(
        session_id="chat-two",
        model_id="model-a",
        request_messages=request_messages,
        assistant_text="Answer",
        response_id="resp_model_a",
    )
    next_messages = [
        *request_messages,
        ChatMessage(role="assistant", content="Answer"),
        ChatMessage(role="user", content="Second"),
    ]

    response_id, reason = responses_runtime._resolve_previous_response_id(
        session_id="chat-two",
        model_id="model-b",
        messages=next_messages,
    )

    assert response_id is None
    assert reason == "model_changed"
