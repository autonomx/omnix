from __future__ import annotations

from app.assistant_context import web_search
from app.persistence import provider_secret_store as secret_store
from app.research import provider_chain


def test_default_search_client_factory_uses_provider_specific_api_key(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    class CapturingClient:
        def __init__(self, **kwargs) -> None:
            captured.append(dict(kwargs))

    monkeypatch.setattr(web_search, "WebSearchClient", CapturingClient)
    monkeypatch.setattr(
        secret_store,
        "load_research_provider_secrets",
        lambda: {"brave": "brave-key", "tavily": "tavily-key"},
    )

    provider_chain._default_client_factory(provider="brave", timeout_seconds=3.0)
    provider_chain._default_client_factory(provider="tavily", timeout_seconds=4.0)
    provider_chain._default_client_factory(provider="duckduckgo", timeout_seconds=5.0)

    assert captured == [
        {"provider": "brave", "timeout_seconds": 3.0, "api_key": "brave-key"},
        {"provider": "tavily", "timeout_seconds": 4.0, "api_key": "tavily-key"},
        {"provider": "duckduckgo", "timeout_seconds": 5.0},
    ]


def test_provider_credential_configured_checks_each_provider_independently(monkeypatch) -> None:
    monkeypatch.setattr(
        secret_store,
        "load_research_provider_secrets",
        lambda: {"brave": "brave-key", "tavily": ""},
    )

    assert provider_chain.provider_credential_configured("brave") is True
    assert provider_chain.provider_credential_configured("tavily") is False
    assert provider_chain.provider_credential_configured("playwright") is True
    assert provider_chain.provider_credential_configured("duckduckgo") is True