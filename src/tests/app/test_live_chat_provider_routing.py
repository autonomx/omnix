from __future__ import annotations

from types import SimpleNamespace

from app import shared
from app.gateway.live_chat_provider_routing import (
    resolve_effective_provider_id,
    resolve_provider_route,
)


def test_default_provider_is_concretized_before_metrics_and_retry(monkeypatch) -> None:
    provider = SimpleNamespace(provider_name="lmstudio")
    requested: list[str | None] = []

    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})

    def fake_get_provider(provider_id: str | None):
        requested.append(provider_id)
        return provider

    monkeypatch.setattr(shared, "get_provider", fake_get_provider)

    effective_provider_id, resolved_provider = resolve_provider_route(None)

    assert effective_provider_id == "lmstudio"
    assert resolved_provider is provider
    assert requested == ["lmstudio"]
    assert resolved_provider.provider_name == "lmstudio"


def test_explicit_provider_routing_is_preserved(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": "lmstudio"})

    assert resolve_effective_provider_id("llm:cerebras") == "llm:cerebras"


def test_empty_configured_provider_falls_back_to_lmstudio(monkeypatch) -> None:
    monkeypatch.setattr(shared, "load_settings", lambda: {"provider": ""})

    assert resolve_effective_provider_id(None) == "lmstudio"
