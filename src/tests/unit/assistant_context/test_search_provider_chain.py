from __future__ import annotations

from app.assistant_context.models import AssistantContextItem
from app.research.policy import ResearchPolicy
from app.research.provider_chain import (
    ProviderFallbackSearchClient,
    normalize_provider_chain,
)
from app.research.quick_search import QuickSearchService
from app.research.settings import ResearchRuntimeSettings


class FakeProviderClient:
    def __init__(self, provider: str, outcomes: dict[str, object]) -> None:
        self.provider = provider
        self.outcomes = outcomes

    def search(self, query: str, max_results: int):
        outcome = self.outcomes[self.provider]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def result(provider: str) -> AssistantContextItem:
    return AssistantContextItem(
        source_id="web_search",
        title=f"{provider} result",
        content="usable result",
        url=f"https://example.test/{provider}",
        metadata={"provider": provider},
    )


def test_normalize_provider_chain_preserves_order_and_removes_duplicates() -> None:
    assert normalize_provider_chain(
        "brave",
        ["playwright", "brave", "duckduckgo", "unsupported"],
    ) == ("brave", "playwright", "duckduckgo")
    assert normalize_provider_chain(None, ["duckduckgo", "playwright"]) == (
        "duckduckgo",
        "playwright",
    )


def test_release_availability_uses_any_usable_provider_in_chain(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_WEB_SEARCH_API_KEY", raising=False)
    with_fallbacks = ResearchRuntimeSettings(
        provider="brave",
        provider_fallbacks=("playwright", "duckduckgo"),
        policy=ResearchPolicy(),
    )
    brave_only = ResearchRuntimeSettings(
        provider="brave",
        provider_fallbacks=(),
        policy=ResearchPolicy(),
    )

    assert with_fallbacks.credential_configured is False
    assert with_fallbacks.provider_available is True
    assert brave_only.provider_available is False


def test_missing_brave_credential_skips_to_playwright(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_WEB_SEARCH_API_KEY", raising=False)
    outcomes = {
        "playwright": [result("playwright")],
        "duckduckgo": [result("duckduckgo")],
    }

    client = ProviderFallbackSearchClient(
        providers=["brave", "playwright", "duckduckgo"],
        timeout_seconds=8,
        client_factory=lambda provider, **_: FakeProviderClient(provider, outcomes),
    )

    items = client.search("current release", 5)

    assert client.provider == "playwright"
    assert client.attempted_providers == ["playwright"]
    assert client.provider_errors["brave"] == "credential_not_configured"
    assert items[0].metadata["provider"] == "playwright"


def test_provider_error_falls_through_and_quick_search_records_actual_provider(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_WEB_SEARCH_API_KEY", "fixture-key")
    outcomes = {
        "brave": RuntimeError("503 temporary upstream failure"),
        "playwright": [result("playwright")],
        "duckduckgo": [result("duckduckgo")],
    }

    def chain_factory(timeout: float):
        return ProviderFallbackSearchClient(
            providers=["brave", "playwright", "duckduckgo"],
            timeout_seconds=timeout,
            client_factory=lambda provider, **_: FakeProviderClient(provider, outcomes),
        )

    execution = QuickSearchService(
        client_factory=chain_factory,
        source_store_factory=None,
        cache_store_factory=None,
        deadline_seconds=8,
    ).search("current release", 5)

    assert execution.diagnostics["provider"] == "playwright"
    assert execution.diagnostics["provider_attempts"] == ["brave", "playwright"]
    assert "503" in execution.diagnostics["provider_failures"]["brave"]
    assert execution.items[0].metadata["provider"] == "playwright"


def test_empty_provider_result_falls_through_to_next_provider(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_WEB_SEARCH_API_KEY", "fixture-key")
    outcomes = {
        "brave": [],
        "playwright": [],
        "duckduckgo": [result("duckduckgo")],
    }
    client = ProviderFallbackSearchClient(
        providers=["brave", "playwright", "duckduckgo"],
        timeout_seconds=8,
        client_factory=lambda provider, **_: FakeProviderClient(provider, outcomes),
    )

    items = client.search("niche topic", 5)

    assert client.provider == "duckduckgo"
    assert client.attempted_providers == ["brave", "playwright", "duckduckgo"]
    assert client.provider_errors["brave"] == "empty_result_set"
    assert client.provider_errors["playwright"] == "empty_result_set"
    assert items[0].metadata["provider"] == "duckduckgo"
