from __future__ import annotations

import json
from typing import Any

from app.gateway.lmstudio_loaded_model_resolution import (
    _clear_lmstudio_model_discovery_cache,
    _resolve_lmstudio_model,
)
from app.providers import ChatMessage, LMStudioProvider, ProviderConfig
from app.providers.base import ConnectionError as ProviderConnectionError


class _Response:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def json(self) -> Any:
        return self.payload


class _CompletionResponse(_Response):
    def __init__(self, payload: Any) -> None:
        super().__init__(payload)
        self.headers: dict[str, str] = {}
        self.content = json.dumps(payload).encode("utf-8")


class _StreamResponse:
    def __init__(self) -> None:
        self.closed = False

    def iter_lines(self):
        yield b'data: {"model":"qwen","choices":[{"delta":{"content":"Hello"}}]}'
        yield b'data: {"model":"qwen","choices":[{"delta":{},"finish_reason":"stop"}]}'
        yield b"data: [DONE]"

    def close(self) -> None:
        self.closed = True


def _provider(*, configured_model: str = "fallback/model") -> LMStudioProvider:
    return LMStudioProvider(
        ProviderConfig(
            provider_type="lmstudio",
            base_url="http://localhost:1234",
            model=configured_model,
        )
    )


def _loaded_qwen_response() -> _Response:
    return _Response(
        {
            "models": [
                {
                    "type": "llm",
                    "key": "qwen3.5-0.8b",
                    "display_name": "Qwen 3.5 0.8B",
                    "loaded_instances": [
                        {
                            "id": "qwen3.5-0.8b",
                            "config": {"context_length": 262144},
                        }
                    ],
                }
            ]
        }
    )


def test_explicit_request_model_wins_without_discovery(monkeypatch) -> None:
    provider = _provider()

    def unexpected_request(*args, **kwargs):
        raise AssertionError("explicit model should not query model discovery")

    monkeypatch.setattr(provider, "_make_request", unexpected_request)

    selected, diagnostics = _resolve_lmstudio_model(provider, "session/model")

    assert selected == "session/model"
    assert diagnostics["source"] == "explicit_request"
    assert diagnostics["selected_model_key"] == "session/model"
    assert diagnostics["selected_instance_id"] is None
    assert diagnostics["loaded_model_count"] is None


def test_single_loaded_llm_uses_model_key_not_instance_id(monkeypatch) -> None:
    provider = _provider(configured_model="qwen/old")
    _clear_lmstudio_model_discovery_cache()

    def request(method: str, endpoint: str, **kwargs):
        assert method == "get"
        assert endpoint == "/api/v1/models"
        return _Response(
            {
                "models": [
                    {
                        "type": "llm",
                        "key": "google/gemma-current",
                        "display_name": "Gemma Current",
                        "loaded_instances": [
                            {
                                "id": "gemma-current-instance",
                                "config": {"context_length": 8192},
                            }
                        ],
                    },
                    {
                        "type": "embedding",
                        "key": "embedding/model",
                        "loaded_instances": [{"id": "embedding-instance"}],
                    },
                ]
            }
        )

    monkeypatch.setattr(provider, "_make_request", request)

    selected, diagnostics = _resolve_lmstudio_model(provider, None)

    assert selected == "google/gemma-current"
    assert diagnostics["source"] == "loaded_model_key"
    assert diagnostics["selected_model_key"] == "google/gemma-current"
    assert diagnostics["selected_instance_id"] == "gemma-current-instance"
    assert diagnostics["selected_context_length"] == 8192
    assert diagnostics["loaded_model_count"] == 1
    assert diagnostics["configured_fallback"] == "qwen/old"


def test_loaded_model_key_is_sent_to_chat_endpoint(monkeypatch) -> None:
    provider = _provider(configured_model="stale/fallback")
    _clear_lmstudio_model_discovery_cache()
    chat_payloads: list[dict[str, Any]] = []

    def request(method: str, endpoint: str, **kwargs):
        if endpoint == "/api/v1/models":
            return _Response(
                {
                    "models": [
                        {
                            "type": "llm",
                            "key": "qwen/qwen3.5-0.8b",
                            "display_name": "Qwen 3.5 0.8B",
                            "loaded_instances": [
                                {
                                    "id": "qwen3.5-0.8b",
                                    "config": {"context_length": 8192},
                                }
                            ],
                        }
                    ]
                }
            )
        assert method == "post"
        assert endpoint == "/v1/chat/completions"
        chat_payloads.append(kwargs["json"])
        return _CompletionResponse(
            {
                "model": "qwen3.5-0.8b",
                "choices": [
                    {
                        "message": {"content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
            }
        )

    monkeypatch.setattr(provider, "_make_request", request)

    response = provider.chat_completion(
        [ChatMessage(role="user", content="Hello")],
        stream=False,
    )

    assert response.model == "qwen3.5-0.8b"
    assert len(chat_payloads) == 1
    assert chat_payloads[0]["model"] == "qwen/qwen3.5-0.8b"


def test_native_metrics_rejection_retries_openai_nonstream_transport(monkeypatch) -> None:
    provider = _provider(configured_model="stale/fallback")
    _clear_lmstudio_model_discovery_cache()
    calls: list[tuple[str, dict[str, Any]]] = []

    def request(method: str, endpoint: str, **kwargs):
        calls.append((endpoint, kwargs))
        if endpoint == "/api/v1/models":
            return _loaded_qwen_response()
        if endpoint == "/api/v0/chat/completions":
            raise ProviderConnectionError("HTTP error 400: legacy request rejected")
        assert endpoint == "/v1/chat/completions"
        return _CompletionResponse(
            {
                "model": "qwen3.5-0.8b",
                "choices": [
                    {
                        "message": {"content": "Recovered"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 1,
                    "total_tokens": 11,
                },
            }
        )

    monkeypatch.setattr(provider, "_make_request", request)

    response = provider.chat_completion(
        [ChatMessage(role="user", content="Hello")],
        stream=False,
        include_metrics=True,
    )

    assert response.content == "Recovered"
    assert [endpoint for endpoint, _ in calls] == [
        "/api/v1/models",
        "/api/v0/chat/completions",
        "/v1/chat/completions",
    ]
    assert calls[1][1]["json"]["model"] == "qwen3.5-0.8b"
    assert calls[2][1]["json"]["model"] == "qwen3.5-0.8b"


def test_native_metrics_rejection_retries_openai_stream_transport(monkeypatch) -> None:
    provider = _provider(configured_model="stale/fallback")
    _clear_lmstudio_model_discovery_cache()
    calls: list[str] = []

    def request(method: str, endpoint: str, **kwargs):
        calls.append(endpoint)
        if endpoint == "/api/v1/models":
            return _loaded_qwen_response()
        if endpoint == "/api/v0/chat/completions":
            raise ProviderConnectionError("HTTP error 422: legacy payload rejected")
        assert endpoint == "/v1/chat/completions"
        return _StreamResponse()

    monkeypatch.setattr(provider, "_make_request", request)

    chunks = list(
        provider.chat_completion(
            [ChatMessage(role="user", content="Hello")],
            stream=True,
            include_metrics=True,
        )
    )

    assert calls == [
        "/api/v1/models",
        "/api/v0/chat/completions",
        "/v1/chat/completions",
    ]
    assert chunks[0].content == "Hello"
    assert chunks[-1].finish_reason == "stop"


def test_configured_model_is_used_only_when_no_llm_is_loaded(monkeypatch) -> None:
    provider = _provider(configured_model="qwen/fallback")
    _clear_lmstudio_model_discovery_cache()
    monkeypatch.setattr(
        provider,
        "_make_request",
        lambda *args, **kwargs: _Response(
            {
                "models": [
                    {
                        "type": "llm",
                        "key": "qwen/fallback",
                        "loaded_instances": [],
                    }
                ]
            }
        ),
    )

    selected, diagnostics = _resolve_lmstudio_model(provider, None)

    assert selected == "qwen/fallback"
    assert diagnostics["source"] == "configured_fallback_no_loaded_model"
    assert diagnostics["discovery_available"] is True
    assert diagnostics["loaded_model_count"] == 0


def test_multiple_loaded_models_prefer_configured_model_only_if_already_loaded(
    monkeypatch,
) -> None:
    provider = _provider(configured_model="qwen/selected")
    _clear_lmstudio_model_discovery_cache()
    monkeypatch.setattr(
        provider,
        "_make_request",
        lambda *args, **kwargs: _Response(
            {
                "models": [
                    {
                        "type": "llm",
                        "key": "google/gemma",
                        "loaded_instances": [{"id": "gemma-instance"}],
                    },
                    {
                        "type": "llm",
                        "key": "qwen/selected",
                        "loaded_instances": [{"id": "qwen-instance"}],
                    },
                ]
            }
        ),
    )

    selected, diagnostics = _resolve_lmstudio_model(provider, None)

    assert selected == "qwen/selected"
    assert diagnostics["source"] == "loaded_model_key_config_match"
    assert diagnostics["selected_instance_id"] == "qwen-instance"
    assert diagnostics["loaded_model_count"] == 2


def test_discovery_failure_does_not_auto_load_stale_fallback(monkeypatch) -> None:
    provider = _provider(configured_model="stale/fallback")
    _clear_lmstudio_model_discovery_cache()

    def unavailable(*args, **kwargs):
        raise OSError("LM Studio model discovery unavailable")

    monkeypatch.setattr(provider, "_make_request", unavailable)

    selected, diagnostics = _resolve_lmstudio_model(provider, None)

    assert selected is None
    assert diagnostics["source"] == "runtime_default_discovery_unavailable"
    assert diagnostics["configured_fallback"] == "stale/fallback"


def test_discovery_failure_omits_stale_fallback_from_chat_payload(monkeypatch) -> None:
    provider = _provider(configured_model="stale/fallback")
    _clear_lmstudio_model_discovery_cache()
    chat_payloads: list[dict[str, Any]] = []

    def request(method: str, endpoint: str, **kwargs):
        if endpoint in {"/api/v1/models", "/api/v0/models"}:
            raise OSError("model discovery unavailable")
        assert endpoint == "/v1/chat/completions"
        chat_payloads.append(kwargs["json"])
        return _CompletionResponse(
            {
                "model": "runtime-selected-model",
                "choices": [
                    {
                        "message": {"content": "Hello"},
                        "finish_reason": "stop",
                    }
                ],
            }
        )

    monkeypatch.setattr(provider, "_make_request", request)

    response = provider.chat_completion(
        [ChatMessage(role="user", content="Hello")],
        stream=False,
    )

    assert response.model == "runtime-selected-model"
    assert len(chat_payloads) == 1
    assert "model" not in chat_payloads[0]


def test_v0_loaded_state_is_used_when_v1_is_unavailable(monkeypatch) -> None:
    provider = _provider(configured_model="fallback/model")
    _clear_lmstudio_model_discovery_cache()

    def request(method: str, endpoint: str, **kwargs):
        if endpoint == "/api/v1/models":
            raise OSError("v1 unavailable")
        assert endpoint == "/api/v0/models"
        return _Response(
            {
                "object": "list",
                "data": [
                    {
                        "id": "legacy-loaded-model",
                        "type": "llm",
                        "state": "loaded",
                        "context_length": 4096,
                    },
                    {
                        "id": "downloaded-only-model",
                        "type": "llm",
                        "state": "not-loaded",
                    },
                ],
            }
        )

    monkeypatch.setattr(provider, "_make_request", request)

    selected, diagnostics = _resolve_lmstudio_model(provider, None)

    assert selected == "legacy-loaded-model"
    assert diagnostics["source"] == "loaded_model_key"
    assert diagnostics["selected_context_length"] == 4096
    assert diagnostics["discovery_endpoint"] == "/api/v0/models"


def test_short_discovery_cache_avoids_duplicate_model_queries(monkeypatch) -> None:
    provider = _provider()
    _clear_lmstudio_model_discovery_cache()
    calls = 0

    def request(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Response(
            {
                "models": [
                    {
                        "type": "llm",
                        "key": "loaded/model",
                        "loaded_instances": [{"id": "loaded-instance"}],
                    }
                ]
            }
        )

    monkeypatch.setattr(provider, "_make_request", request)

    first, first_diagnostics = _resolve_lmstudio_model(provider, None)
    second, second_diagnostics = _resolve_lmstudio_model(provider, None)

    assert first == second == "loaded/model"
    assert calls == 1
    assert first_diagnostics["discovery_cache_hit"] is False
    assert second_diagnostics["discovery_cache_hit"] is True
