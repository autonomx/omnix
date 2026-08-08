from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app import shared
from app.chat.provider_metrics import merge_provider_response_metrics
from app.gateway import live_chat_live_voice_profile as live_voice_profile
from app.gateway.live_chat_provider_metrics import (
    _LowLatencyTextChunker,
    _is_lmstudio,
    _stream_lmstudio_reply,
)
from app.providers import ChatMessage, ChatResponse, LMStudioProvider, ProviderConfig


def _stats_payload() -> dict[str, Any]:
    return {
        "usage": {
            "prompt_tokens": 18,
            "completion_tokens": 37,
            "total_tokens": 55,
            "prompt_tokens_details": {"cached_tokens": 12},
        },
        "stats": {
            "tokens_per_second": 127.26,
            "time_to_first_token": 0.11,
            "generation_time": 0.38,
            "stop_reason": "eosFound",
            "draft_model": "draft-qwen",
            "total_draft_tokens_count": 20,
            "accepted_draft_tokens_count": 15,
            "rejected_draft_tokens_count": 4,
            "ignored_draft_tokens_count": 1,
        },
    }


class _JsonResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.headers: dict[str, str] = {}
        self.content = b"{}"

    def json(self) -> Any:
        return self.payload


class _StreamResponse:
    def __init__(self) -> None:
        self.closed = False

    def iter_lines(self):
        yield b'data: {"model":"qwen","choices":[{"delta":{"content":"Howdy"}}]}'
        yield (
            b'data: {"model":"qwen","choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":18,"completion_tokens":37,"total_tokens":55,'
            b'"prompt_tokens_details":{"cached_tokens":12}},'
            b'"stats":{"tokens_per_second":127.26,"time_to_first_token":0.11,'
            b'"generation_time":0.38,"stop_reason":"eosFound","draft_model":"draft-qwen",'
            b'"total_draft_tokens_count":20,"accepted_draft_tokens_count":15,'
            b'"rejected_draft_tokens_count":4,"ignored_draft_tokens_count":1}}'
        )
        yield b'data: [DONE]'

    def close(self) -> None:
        self.closed = True


def _loaded_model_response() -> _JsonResponse:
    return _JsonResponse(
        {
            "models": [
                {
                    "type": "llm",
                    "key": "qwen",
                    "display_name": "Qwen",
                    "loaded_instances": [{"id": "qwen"}],
                }
            ]
        }
    )


def _provider() -> LMStudioProvider:
    return LMStudioProvider(
        ProviderConfig(
            provider_type="lmstudio",
            base_url="http://localhost:1234",
            model="qwen",
        )
    )


def test_lmstudio_metric_stream_retains_final_usage_and_stats(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []
    provider = _provider()
    stream_response = _StreamResponse()

    def fake_make_request(method: str, endpoint: str, **kwargs: Any):
        calls.append((method, endpoint, kwargs))
        if endpoint == "/api/v1/models":
            return _loaded_model_response()
        return stream_response

    monkeypatch.setattr(provider, "_make_request", fake_make_request)

    chunks = list(
        provider.chat_completion(
            [ChatMessage(role="user", content="Hello")],
            stream=True,
            include_metrics=True,
        )
    )

    assert [call[1] for call in calls] == [
        "/api/v1/models",
        "/api/v0/chat/completions",
    ]
    assert calls[-1][2]["json"]["model"] == "qwen"
    assert chunks[0].content == "Howdy"
    assert chunks[-1].content == ""
    assert chunks[-1].usage == {
        "prompt_tokens": 18,
        "completion_tokens": 37,
        "total_tokens": 55,
        "prompt_tokens_details": {"cached_tokens": 12},
    }
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].raw_response["stats"]["tokens_per_second"] == 127.26
    assert stream_response.closed is True


def test_lmstudio_regular_stream_keeps_openai_compatible_endpoint(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    provider = _provider()
    stream_response = _StreamResponse()

    def fake_make_request(method: str, endpoint: str, **kwargs: Any):
        calls.append((endpoint, kwargs))
        if endpoint == "/api/v1/models":
            return _loaded_model_response()
        return stream_response

    monkeypatch.setattr(provider, "_make_request", fake_make_request)

    list(
        provider.chat_completion(
            [ChatMessage(role="user", content="Hello")],
            stream=True,
        )
    )

    assert [endpoint for endpoint, _ in calls] == [
        "/api/v1/models",
        "/v1/chat/completions",
    ]
    assert calls[-1][1]["json"]["model"] == "qwen"
    assert stream_response.closed is True


def test_lmstudio_cancelled_stream_closes_http_response(monkeypatch) -> None:
    provider = _provider()
    stream_response = _StreamResponse()
    monkeypatch.setattr(
        provider,
        "_make_chat_completion_request",
        lambda *_args, **_kwargs: stream_response,
    )

    stream = provider.chat_completion(
        [ChatMessage(role="user", content="Hello")],
        stream=True,
    )
    assert next(stream).content == "Howdy"
    assert stream_response.closed is False

    stream.close()

    assert stream_response.closed is True


def test_provider_metrics_normalize_lmstudio_stats() -> None:
    payload = _stats_payload()
    response = ChatResponse(
        content="",
        model="qwen",
        usage=payload["usage"],
        finish_reason="stop",
        raw_response=payload,
    )

    metrics = merge_provider_response_metrics(
        None,
        response,
        provider_id="llm:lmstudio",
    )

    assert metrics == {
        "provider": "lmstudio",
        "tokens_per_second": 127.26,
        "output_tokens": 37,
        "input_tokens": 18,
        "cached_input_tokens": 12,
        "uncached_input_tokens": 6,
        "prompt_cache_hit_ratio": 12 / 18,
        "total_tokens": 55,
        "generation_time_seconds": 0.38,
        "time_to_first_token_seconds": 0.11,
        "draft_model": "draft-qwen",
        "total_draft_tokens": 20,
        "accepted_draft_tokens": 15,
        "rejected_draft_tokens": 4,
        "ignored_draft_tokens": 1,
        "draft_acceptance_ratio": 0.75,
        "stop_reason": "eosFound",
        "finish_reason": "stop",
    }


def test_default_provider_is_detected_as_lmstudio(monkeypatch) -> None:
    provider = SimpleNamespace(provider_name="lmstudio")
    requested: list[str | None] = []

    def fake_get_provider(name: str | None):
        requested.append(name)
        return provider

    monkeypatch.setattr(shared, "get_provider", fake_get_provider)

    assert _is_lmstudio(None) is True
    assert requested == [None]


def test_low_latency_chunker_emits_first_word_before_sentence_completion() -> None:
    chunker = _LowLatencyTextChunker()

    assert chunker.push("How") == []
    assert chunker.push("dy ") == ["Howdy "]
    assert chunker.push("right back") == []
    assert chunker.push(" at ya.") == ["right back at ya."]
    assert chunker.flush() == ""


def test_lmstudio_prompt_stream_persists_metrics_on_completion(monkeypatch) -> None:
    payload = _stats_payload()

    class FakeProvider:
        provider_name = "lmstudio"

        def chat_completion(self, **kwargs: Any):
            assert kwargs["stream"] is True
            assert kwargs["include_metrics"] is True
            return iter(
                [
                    ChatResponse(content="Hello there.", model="qwen"),
                    ChatResponse(
                        content="",
                        model="qwen",
                        usage=payload["usage"],
                        finish_reason="stop",
                        raw_response=payload,
                    ),
                ]
            )

    monkeypatch.setattr(shared, "get_provider", lambda name: FakeProvider() if name == "lmstudio" else None)

    rendered = SimpleNamespace(
        messages=[SimpleNamespace(role="user", content="Hello")],
    )
    store = SimpleNamespace(
        build_provider_prompt=lambda session, user_message, context_items: (
            SimpleNamespace(diagnostics={}),
            rendered,
        ),
        _active_memory_metadata=lambda assembly, current_rendered: {},
        _active_history_metadata=lambda assembly: {},
    )
    session = SimpleNamespace(id="chat:test")
    user_message = SimpleNamespace(id="msg:user", content="Hello")

    events = list(
        _stream_lmstudio_reply(
            store,
            session,
            user_message,
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:qwen",
            context_items=[],
        )
    )

    complete = events[-1]
    assert complete["type"] == "complete"
    assert complete["content"] == "Hello there."
    assert complete["metadata"]["usage"]["completion_tokens"] == 37
    assert complete["metadata"]["provider_metrics"]["tokens_per_second"] == 127.26
    assert complete["metadata"]["provider_metrics"]["cached_input_tokens"] == 12
    assert complete["metadata"]["provider_metrics"]["draft_acceptance_ratio"] == 0.75
    assert complete["metadata"]["provider_metrics"]["stop_reason"] == "eosFound"


def test_lmstudio_prompt_stream_reconstructs_split_provider_deltas(monkeypatch) -> None:
    payload = _stats_payload()

    class FakeProvider:
        provider_name = "lmstudio"

        def chat_completion(self, **kwargs: Any):
            return iter(
                [
                    ChatResponse(content="How", model="qwen"),
                    ChatResponse(content="dy ", model="qwen"),
                    ChatResponse(content="right", model="qwen"),
                    ChatResponse(content=" back", model="qwen"),
                    ChatResponse(content=" at ya.", model="qwen"),
                    ChatResponse(
                        content="",
                        model="qwen",
                        usage=payload["usage"],
                        finish_reason="stop",
                        raw_response=payload,
                    ),
                ]
            )

    rendered = SimpleNamespace(
        messages=[SimpleNamespace(role="user", content="Hello")],
    )
    store = SimpleNamespace(
        build_provider_prompt=lambda session, user_message, context_items: (
            SimpleNamespace(diagnostics={}),
            rendered,
        ),
        _active_memory_metadata=lambda assembly, current_rendered: {},
        _active_history_metadata=lambda assembly: {},
    )

    events = list(
        _stream_lmstudio_reply(
            store,
            SimpleNamespace(id="chat:test"),
            SimpleNamespace(id="msg:user", content="Hello"),
            provider_id="llm:lmstudio",
            model_id="llm:lmstudio:qwen",
            context_items=[],
            provider=FakeProvider(),
        )
    )

    text_events = [event["text"] for event in events if event["type"] == "text_chunk"]
    assert text_events[0] == "Howdy "
    assert "".join(text_events) == "Howdy right back at ya."
    assert events[-1]["content"] == "Howdy right back at ya."


def test_live_voice_policy_requests_native_metrics(monkeypatch) -> None:
    live_voice_profile._install_lmstudio_thinking_policy()
    provider = _provider()
    calls: list[tuple[str, dict[str, Any]]] = []
    payload = _stats_payload()

    def fake_make_request(method: str, endpoint: str, **kwargs: Any):
        calls.append((endpoint, kwargs))
        if endpoint == "/api/v1/models":
            return _loaded_model_response()
        return _JsonResponse(
            {
                "model": "qwen",
                "choices": [
                    {
                        "message": {"content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
                **payload,
            }
        )

    monkeypatch.setattr(provider, "_make_request", fake_make_request)
    token = live_voice_profile._LIVE_VOICE_TURN.set(True)
    try:
        provider.chat_completion(
            [ChatMessage(role="user", content="Hello")],
            stream=False,
        )
    finally:
        live_voice_profile._LIVE_VOICE_TURN.reset(token)

    endpoint, request = calls[-1]
    assert endpoint == "/api/v0/chat/completions"
    assert request["json"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_raw_live_voice_provider_stream_logs_cache_and_ttft(monkeypatch) -> None:
    payload = _stats_payload()
    logs: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        live_voice_profile,
        "stream_log",
        lambda *args, **kwargs: logs.append((args, kwargs)),
    )

    source = iter(
        [
            ChatResponse(content="Hello ", model="qwen"),
            ChatResponse(
                content="there.",
                model="qwen",
                usage=payload["usage"],
                finish_reason="stop",
                raw_response=payload,
            ),
        ]
    )

    chunks = list(
        live_voice_profile._stream_with_live_voice_context(
            source,
            is_live_voice=True,
        )
    )

    assert "".join(chunk.content for chunk in chunks) == "Hello there."
    metric_log = next(
        kwargs
        for args, kwargs in logs
        if len(args) >= 3 and args[2] == "live_voice_raw_provider_stream_metrics"
    )
    assert metric_log["stream_completed"] is True
    assert metric_log["input_tokens"] == 18
    assert metric_log["cached_input_tokens"] == 12
    assert metric_log["uncached_input_tokens"] == 6
    assert metric_log["prompt_cache_hit_ratio"] == 12 / 18
    assert metric_log["native_ttft_ms"] == 110.0
    assert metric_log["draft_model"] == "draft-qwen"
    assert metric_log["accepted_draft_tokens"] == 15
    assert metric_log["draft_acceptance_ratio"] == 0.75
