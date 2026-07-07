from app.assistant_context.models import AssistantContextItem
from app.research.quick_search import QuickSearchService, is_transient_search_error, provider_coverage


class FakeSearchClient:
    def __init__(self, provider: str, outcomes: list[object]) -> None:
        self.provider = provider
        self.outcomes = outcomes

    def search(self, query: str, max_results: int):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def result_item() -> AssistantContextItem:
    return AssistantContextItem(
        source_id="web_search",
        title="Current result",
        content="A bounded search result.",
        url="https://example.test/result",
        metadata={"provider": "brave"},
    )


def quick_service(**kwargs) -> QuickSearchService:
    return QuickSearchService(
        cache_store_factory=None,
        rate_limiter_factory=None,
        **kwargs,
    )


def test_quick_search_uses_one_logical_query_and_retries_one_transient_failure() -> None:
    outcomes: list[object] = [RuntimeError("503 temporary provider failure"), [result_item()]]
    timeouts: list[float] = []

    def factory(timeout_seconds: float):
        timeouts.append(timeout_seconds)
        return FakeSearchClient("brave", outcomes)

    result = quick_service(
        client_factory=factory,
        source_store_factory=None,
        deadline_seconds=8,
    ).search("latest Omnix", 5)

    assert len(result.items) == 1
    assert result.diagnostics["logical_queries"] == 1
    assert result.diagnostics["transport_attempts"] == 2
    assert result.diagnostics["status"] == "completed"
    assert len(timeouts) == 2
    assert all(0 < timeout <= 8 for timeout in timeouts)


def test_quick_search_does_not_retry_permanent_configuration_failure() -> None:
    outcomes: list[object] = [RuntimeError("OMNIX_WEB_SEARCH_API_KEY is required for the Brave provider")]
    calls = 0

    def factory(timeout_seconds: float):
        nonlocal calls
        calls += 1
        return FakeSearchClient("brave", outcomes)

    result = quick_service(client_factory=factory, source_store_factory=None).search(
        "current release", 5
    )

    assert calls == 1
    assert result.items == []
    assert result.diagnostics["status"] == "failed"
    assert result.warnings[-1]["code"] == "quick_search_unavailable"


def test_duckduckgo_is_reported_as_limited_fallback() -> None:
    result = quick_service(
        client_factory=lambda timeout: FakeSearchClient("duckduckgo", [[]]),
        source_store_factory=None,
    ).search("niche current topic", 5)

    assert result.diagnostics["coverage"] == "limited reference and instant-answer fallback"
    assert {warning["code"] for warning in result.warnings} == {
        "limited_search_provider",
        "quick_search_empty",
    }


def test_transient_error_policy_is_bounded() -> None:
    assert is_transient_search_error(RuntimeError("429 rate limited")) is True
    assert is_transient_search_error(RuntimeError("request timed out")) is True
    assert is_transient_search_error(RuntimeError("401 authentication failed")) is False
    assert provider_coverage("brave") == "general web search"
