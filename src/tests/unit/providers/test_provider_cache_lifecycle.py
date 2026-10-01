"""Lifecycle regressions for process-backed LLM providers."""
from __future__ import annotations

from types import SimpleNamespace

import app.providers.service as provider_service
from app.providers import ProviderConfig


def test_invalidate_provider_cache_closes_cached_process_provider():
    closed: list[bool] = []
    provider = SimpleNamespace(close=lambda: closed.append(True))
    previous = provider_service._PROVIDER_CACHE
    try:
        provider_service._PROVIDER_CACHE = ("chatgpt_codex|cached", provider, 99.0)

        provider_service.invalidate_provider_cache()

        assert closed == [True]
        assert provider_service._PROVIDER_CACHE == (None, None, 0.0)
    finally:
        provider_service._PROVIDER_CACHE = previous


def test_provider_cache_key_tracks_codex_transport_options():
    medium = ProviderConfig(
        provider_type="chatgpt_codex",
        model="gpt-5.6-sol",
        extra_params={
            "reasoning_effort": "medium",
            "fast_mode": False,
            "codex_path": "codex",
            "transport": "app_server",
        },
    )
    high = ProviderConfig(
        provider_type="chatgpt_codex",
        model="gpt-5.6-sol",
        extra_params={
            "reasoning_effort": "high",
            "fast_mode": False,
            "codex_path": "codex",
            "transport": "app_server",
        },
    )

    assert provider_service._cache_key("chatgpt_codex", medium) != provider_service._cache_key(
        "chatgpt_codex",
        high,
    )


def test_shared_factory_builds_codex_from_typed_profile(monkeypatch):
    captured: dict[str, object] = {}
    provider = SimpleNamespace(close=lambda: None)

    class Registry:
        def create_provider(self, name, provider_config=None):
            captured["name"] = name
            captured["config"] = provider_config
            return provider

    monkeypatch.setattr(
        provider_service,
        "load_settings",
        lambda: {
            "provider": "chatgpt_codex",
            "settings_control_center": {
                "providerConfigs": {
                    "chatgptCodex": {
                        "model": "gpt-test",
                        "reasoningEffort": "low",
                        "fastMode": True,
                        "codexPath": "C:/tools/codex.exe",
                        "transport": "app_server",
                    }
                }
            },
        },
    )
    monkeypatch.setattr(provider_service, "load_secrets", lambda: {"api_keys": {}})
    monkeypatch.setattr(provider_service, "get_registry", lambda: Registry())
    previous = provider_service._PROVIDER_CACHE
    provider_service._PROVIDER_CACHE = (None, None, 0.0)
    try:
        assert provider_service.get_provider("chatgpt_codex") is provider
        config = captured["config"]
        assert captured["name"] == "chatgpt_codex"
        assert isinstance(config, ProviderConfig)
        assert config.provider_type == "chatgpt_codex"
        assert config.model == "gpt-test"
        assert config.extra_params == {
            "reasoning_effort": "low",
            "fast_mode": True,
            "codex_path": "C:/tools/codex.exe",
            "transport": "app_server",
        }
    finally:
        provider_service.invalidate_provider_cache()
        provider_service._PROVIDER_CACHE = previous
