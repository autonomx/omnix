"""Lifecycle regressions for process-backed LLM providers."""
from __future__ import annotations

from types import SimpleNamespace

import app.providers.service as provider_service
from app.providers import ProviderConfig


def test_invalidate_provider_cache_closes_cached_process_provider():
    closed: list[bool] = []
    provider = SimpleNamespace(close=lambda: closed.append(True))
    provider_service._PROVIDERS["chatgpt_codex|cached"] = provider_service._CachedProvider(provider, 99.0)

    provider_service.invalidate_provider_cache()

    assert closed == [True]
    assert not provider_service._PROVIDERS


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
    provider_service.invalidate_provider_cache()
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


class _Closable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _install_registry(monkeypatch) -> dict[str, list[_Closable]]:
    created: dict[str, list[_Closable]] = {}

    class Registry:
        def create_provider(self, name, provider_config=None):
            instance = _Closable(name)
            created.setdefault(name, []).append(instance)
            return instance

    monkeypatch.setattr(provider_service, "load_settings", lambda: {"provider": "lmstudio"})
    monkeypatch.setattr(provider_service, "load_secrets", lambda: {"api_keys": {}})
    monkeypatch.setattr(provider_service, "get_registry", lambda: Registry())
    provider_service.invalidate_provider_cache()
    return created


def test_getting_another_provider_does_not_close_the_first(monkeypatch):
    _install_registry(monkeypatch)
    try:
        lmstudio = provider_service.get_provider("lmstudio")
        openrouter = provider_service.get_provider("openrouter")

        assert lmstudio is not openrouter
        assert not lmstudio.closed
        assert provider_service.get_provider("lmstudio") is lmstudio
    finally:
        provider_service.invalidate_provider_cache()


def test_a_leased_provider_outlives_invalidation_until_released(monkeypatch):
    created = _install_registry(monkeypatch)
    try:
        with provider_service.provider_lease("lmstudio") as provider:
            provider_service.invalidate_provider_cache()  # e.g. a settings change mid-stream
            assert not provider.closed
            replacement = provider_service.get_provider("lmstudio")
            assert replacement is not provider
        assert provider.closed
        assert not replacement.closed
        assert len(created["lmstudio"]) == 2
    finally:
        provider_service.invalidate_provider_cache()


def test_the_cache_is_bounded_and_evicts_the_least_recent(monkeypatch):
    _install_registry(monkeypatch)
    monkeypatch.setattr(provider_service, "_PROVIDER_CACHE_MAX_ENTRIES", 2)
    try:
        first = provider_service.get_provider("lmstudio")
        provider_service.get_provider("openrouter")
        provider_service.get_provider("cerebras")

        assert first.closed
        assert len(provider_service._PROVIDERS) == 2
    finally:
        provider_service.invalidate_provider_cache()
