from __future__ import annotations

from typing import Any

from app.gateway.lmstudio_loaded_model_resolution import (
    _clear_lmstudio_model_discovery_cache,
    _resolve_lmstudio_model,
)
from app.providers import LMStudioProvider, ProviderConfig


class _Response:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def json(self) -> Any:
        return self.payload


def _provider(*, configured_model: str = "fallback/model") -> LMStudioProvider:
    return LMStudioProvider(
        ProviderConfig(
            provider_type="lmstudio",
            base_url="http://localhost:1234",
            model=configured_model,
        )
    )


def test_explicit_request_model_wins_without_discovery(monkeypatch) -> None:
    provider = _provider()

    def unexpected_request(*args, **kwargs):
        raise AssertionError("explicit model should not query model discovery")

    monkeypatch.setattr(provider, "_make_request", unexpected_request)

    selected, diagnostics = _resolve_lmstudio_model(provider, "session/model")

    assert selected == "session/model"
    assert diagnostics["source"] == "explicit_request"
    assert diagnostics["loaded_model_count"] is None


def test_single_loaded_llm_replaces_stale_configured_model(monkeypatch) -> None:
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

    assert selected == "gemma-current-instance"
    assert diagnostics["source"] == "loaded_instance"
    assert diagnostics["loaded_model_count"] == 1
    assert diagnostics["configured_fallback"] == "qwen/old"


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

    assert selected == "qwen-instance"
    assert diagnostics["source"] == "loaded_instance_config_match"
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
    assert diagnostics["source"] == "loaded_instance"
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

    assert first == second == "loaded-instance"
    assert calls == 1
    assert first_diagnostics["discovery_cache_hit"] is False
    assert second_diagnostics["discovery_cache_hit"] is True
