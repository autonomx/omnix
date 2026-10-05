from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.platform.chat.provider_metrics import merge_provider_response_metrics
from app.platform.live_voice.llm import stream as live_voice_stream
from app.platform.live_voice.llm.metrics import (
    is_lmstudio,
    stream_lmstudio_reply,
)
from app.platform.live_voice.llm.stream import LowLatencyTextChunker
from app.platform.live_voice.llm.lmstudio_model_resolution import (
    chat_completion_with_loaded_model,
)
from app.providers import ChatMessage, ChatResponse, LMStudioProvider, ProviderConfig
from app.providers import service as provider_service


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
        chat_completion_with_loaded_model(
            provider,
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
        chat_completion_with_loaded_model(
            provider,
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

    monkeypatch.setattr(provider_service, "get_provider", fake_get_provider)

    assert is_lmstudio(None) is True
    assert requested == [None]


def test_lmstudio_metrics_use_feature_owned_model_resolution(monkeypatch) -> None:
    from app.platform.live_voice.llm import lmstudio_model_resolution, metrics

    provider = _provider()
    calls: list[tuple[Any, list[Any], dict[str, Any]]] = []

    def complete(selected_provider: Any, messages: list[Any], **kwargs: Any):
        calls.append((selected_provider, messages, kwargs))
        return ChatResponse(content="Resolved response", model="loaded/qwen")

    monkeypatch.setattr(
        lmstudio_model_resolution,
        "chat_completion_with_loaded_model",
        complete,
    )

    response = metrics._chat_completion(
        provider,
        [ChatMessage(role="user", content="Hello")],
        model="qwen",
        stream=False,
        kwargs={"include_metrics": True},
    )

    assert response.content == "Resolved response"
    assert calls[0][0] is provider
    assert calls[0][2] == {"model": "qwen", "stream": False, "include_metrics": True}


def test_low_latency_chunker_emits_first_word_before_sentence_completion() -> None:
    chunker = LowLatencyTextChunker()

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

    monkeypatch.setattr(
        provider_service,
        "get_provider",
        lambda name: FakeProvider() if name == "lmstudio" else None,
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
    session = SimpleNamespace(id="chat:test")
    user_message = SimpleNamespace(id="msg:user", content="Hello")

    events = list(
        stream_lmstudio_reply(
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
        stream_lmstudio_reply(
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


def test_prompt_store_stream_composes_lmstudio_metrics_directly(monkeypatch) -> None:
    from app.platform.chat import prompt_store
    from app.platform.live_voice.llm import metrics as llm_metrics

    provider = SimpleNamespace(provider_name="lmstudio")
    monkeypatch.setattr(provider_service, "get_provider", lambda _name=None: provider)
    monkeypatch.setattr(
        prompt_store,
        "route_typed_stream_boundary",
        lambda *_args, **_kwargs: None,
    )
    calls: list[dict[str, Any]] = []

    def stream_metrics(_store: Any, _session: Any, _message: Any, **kwargs: Any):
        calls.append(kwargs)
        yield {"type": "complete", "content": "Hello", "metadata": {}}

    monkeypatch.setattr(llm_metrics, "stream_lmstudio_reply", stream_metrics)

    from app.platform.live_voice.chat_integration import create_live_voice_chat_port

    store = prompt_store.ChatSessionStore(
        live_voice_chat_port=create_live_voice_chat_port(),
    )
    events = list(
        store.stream_provider_reply_chunks(
            SimpleNamespace(id="chat:test"),
            SimpleNamespace(id="msg:user", content="Hello", metadata={}),
            provider_id="lmstudio",
            model_id="qwen",
            context_items=[],
        )
    )

    assert events[-1]["content"] == "Hello"
    assert calls[0]["provider"] is provider
    assert calls[0]["provider_id"] == "lmstudio"


def test_prompt_store_generation_composes_lmstudio_metrics_directly(monkeypatch) -> None:
    from app.platform.chat import prompt_store
    from app.platform.live_voice.llm import metrics as llm_metrics

    provider = SimpleNamespace(provider_name="lmstudio")
    monkeypatch.setattr(provider_service, "get_provider", lambda _name=None: provider)
    calls: list[dict[str, Any]] = []

    def generate_metrics(_store: Any, _session: Any, _message: Any, **kwargs: Any):
        calls.append(kwargs)
        return {"content": "Hello", "metadata": {}}

    monkeypatch.setattr(llm_metrics, "generate_lmstudio_reply", generate_metrics)

    from app.platform.live_voice.chat_integration import create_live_voice_chat_port

    result = prompt_store.ChatSessionStore._generate_provider_reply(
        SimpleNamespace(live_voice_chat_port=create_live_voice_chat_port()),
        SimpleNamespace(id="chat:test"),
        SimpleNamespace(id="msg:user", metadata={}),
        provider_id="lmstudio",
        model_id="qwen",
        context_items=[],
    )

    assert result["content"] == "Hello"
    assert calls[0]["provider"] is provider
    assert calls[0]["provider_id"] == "lmstudio"


def test_raw_live_voice_provider_stream_logs_cache_and_ttft(monkeypatch) -> None:
    payload = _stats_payload()
    logs: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        live_voice_stream,
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
        live_voice_stream.observe_live_voice_provider_stream(source)
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
