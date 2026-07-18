from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app import shared
from app.chat.provider_metrics import merge_provider_response_metrics
from app.gateway.live_chat_provider_metrics import _is_lmstudio, _stream_lmstudio_reply
from app.providers import ChatMessage, ChatResponse, LMStudioProvider, ProviderConfig


def _stats_payload() -> dict[str, Any]:
    return {
        "usage": {
            "prompt_tokens": 18,
            "completion_tokens": 37,
            "total_tokens": 55,
        },
        "stats": {
            "tokens_per_second": 127.26,
            "time_to_first_token": 0.11,
            "generation_time": 0.38,
            "stop_reason": "eosFound",
        },
    }


def test_lmstudio_stream_retains_final_usage_and_stats(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    class FakeResponse:
        def iter_lines(self):
            yield b'data: {"model":"qwen","choices":[{"delta":{"content":"Howdy"}}]}'
            yield (
                b'data: {"model":"qwen","choices":[{"delta":{},"finish_reason":"stop"}],'
                b'"usage":{"prompt_tokens":18,"completion_tokens":37,"total_tokens":55},'
                b'"stats":{"tokens_per_second":127.26,"time_to_first_token":0.11,'
                b'"generation_time":0.38,"stop_reason":"eosFound"}}'
            )
            yield b'data: [DONE]'

    provider = LMStudioProvider(
        ProviderConfig(
            provider_type="lmstudio",
            base_url="http://localhost:1234",
            model="qwen",
        )
    )

    def fake_make_request(method: str, endpoint: str, **kwargs: Any) -> FakeResponse:
        calls.append((method, endpoint, kwargs))
        return FakeResponse()

    monkeypatch.setattr(provider, "_make_request", fake_make_request)

    chunks = list(
        provider.chat_completion(
            [ChatMessage(role="user", content="Hello")],
            stream=True,
        )
    )

    assert calls[0][1] == "/api/v0/chat/completions"
    assert chunks[0].content == "Howdy"
    assert chunks[-1].content == ""
    assert chunks[-1].usage == {
        "prompt_tokens": 18,
        "completion_tokens": 37,
        "total_tokens": 55,
    }
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].raw_response["stats"]["tokens_per_second"] == 127.26


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
        "total_tokens": 55,
        "generation_time_seconds": 0.38,
        "time_to_first_token_seconds": 0.11,
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


def test_lmstudio_prompt_stream_persists_metrics_on_completion(monkeypatch) -> None:
    payload = _stats_payload()

    class FakeProvider:
        provider_name = "lmstudio"

        def chat_completion(self, **kwargs: Any):
            assert kwargs["stream"] is True
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
    assert complete["metadata"]["provider_metrics"]["stop_reason"] == "eosFound"
