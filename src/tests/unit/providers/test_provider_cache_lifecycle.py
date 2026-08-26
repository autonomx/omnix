"""Lifecycle regressions for process-backed LLM providers."""
from __future__ import annotations

from types import SimpleNamespace

import app.shared as shared
from app.providers import ProviderConfig


def test_invalidate_provider_cache_closes_cached_process_provider():
    closed: list[bool] = []
    provider = SimpleNamespace(close=lambda: closed.append(True))
    previous = dict(shared._PROVIDER_CACHE)
    try:
        shared._PROVIDER_CACHE["key"] = "chatgpt_codex|cached"
        shared._PROVIDER_CACHE["instance"] = provider

        shared.invalidate_provider_cache()

        assert closed == [True]
        assert shared._PROVIDER_CACHE == {"key": None, "instance": None}
    finally:
        shared._PROVIDER_CACHE.update(previous)


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

    assert shared._build_provider_cache_key("chatgpt_codex", medium) != shared._build_provider_cache_key(
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
        shared,
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
    monkeypatch.setattr(shared, "load_secrets", lambda: {"api_keys": {}})
    monkeypatch.setattr(shared, "get_registry", lambda: Registry())
    previous = dict(shared._PROVIDER_CACHE)
    shared._PROVIDER_CACHE.update({"key": None, "instance": None})
    try:
        assert shared.get_provider("chatgpt_codex") is provider
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
        shared.invalidate_provider_cache()
        shared._PROVIDER_CACHE.update(previous)
