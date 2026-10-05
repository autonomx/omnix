from __future__ import annotations

from datetime import datetime, timezone

from app.conversation.contracts import AssistantContextItem
from app.research import cache as research_cache
from app.research.cache import ResearchCacheStore
from app.research.extraction import ExtractedPage, ReadablePageExtractor
from app.research.outbound_web import OutboundWebResponse
from app.research.policy import (
    ResearchPolicy,
    privacy_contract,
)
from app.research.quick_search import QuickSearchService
from app.research.retention import ResearchRetentionService
from app.research.source_store import ResearchSourceStore


class CountingSearchClient:
    provider = "brave"

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def search(self, query: str, max_results: int):
        self.calls.append(query)
        return [
            AssistantContextItem(
                source_id="web_search",
                title="Cached result",
                content="A cacheable result.",
                url="https://example.test/cache",
                metadata={"provider": "brave"},
            )
        ]


class CountingFetchPolicy:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def fetch(self, url: str) -> OutboundWebResponse:
        self.calls.append(url)
        return OutboundWebResponse(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            content=b"<html><title>Cached page</title><body><p>Evidence.</p></body></html>",
            redirect_count=0,
            elapsed_ms=4,
        )


def test_search_cache_hit_skips_provider_call_and_transport_attempt(tmp_path) -> None:
    calls: list[str] = []
    cache = ResearchCacheStore(tmp_path / "cache.sqlite")
    policy = ResearchPolicy(search_cache_ttl_seconds=60)

    def service() -> QuickSearchService:
        return QuickSearchService(
            client_factory=lambda timeout: CountingSearchClient(calls),
            source_store_factory=None,
            extractor_factory=None,
            cache_store_factory=lambda: cache,
            research_policy=policy,
        )

    first = service().search("current cache topic", identity="chat:one")
    second = service().search("current cache topic", identity="chat:one")

    assert calls == ["current cache topic"]
    assert first.diagnostics["cache_hit"] is False
    assert second.diagnostics["cache_hit"] is True
    assert second.diagnostics["transport_attempts"] == 0
    assert len(second.items) == 1


def test_extraction_cache_is_keyed_by_url_and_extractor_version(tmp_path) -> None:
    calls: list[str] = []
    cache = ResearchCacheStore(tmp_path / "cache.sqlite")
    policy = ResearchPolicy(extraction_cache_ttl_seconds=60)

    def extractor() -> ReadablePageExtractor:
        return ReadablePageExtractor(
            policy_factory=lambda: CountingFetchPolicy(calls),
            cache_store_factory=lambda: cache,
            research_policy=policy,
        )

    first = extractor().extract("https://example.test/page#first")
    second = extractor().extract("https://example.test/page#second")

    assert calls == ["https://example.test/page#first"]
    assert first.content_hash == second.content_hash
    assert second.elapsed_ms == 0
    assert "Evidence." in second.text


def test_research_cache_store_registry_and_entries_are_bounded(monkeypatch, tmp_path) -> None:
    research_cache.clear_research_cache_states()
    monkeypatch.setattr(research_cache, "_MAX_CACHE_STORES", 2)
    monkeypatch.setattr(research_cache, "_MAX_CACHE_ENTRIES_PER_TABLE", 2)
    stores = [ResearchCacheStore(tmp_path / f"cache-{index}.json") for index in range(3)]
    for index, store in enumerate(stores):
        store._put("research_search_cache", f"key-{index}", index, ttl_seconds=60)

    assert len(research_cache._CACHE_STATES) == 2
    assert set(research_cache._CACHE_STATES) == {
        str(stores[1].path),
        str(stores[2].path),
    }

    store = stores[2]
    assert store._get("research_search_cache", "key-2") == 2
    store._put("research_search_cache", "next-1", 1, ttl_seconds=60)
    store._put("research_search_cache", "next-2", 2, ttl_seconds=60)
    store._put("research_search_cache", "next-3", 3, ttl_seconds=60)
    assert store._get("research_search_cache", "key-2") is None
    assert store._get("research_search_cache", "next-3") == 3
    research_cache.clear_research_cache_states()


def test_research_cache_ttl_is_capped_and_states_are_invalidatable(monkeypatch, tmp_path) -> None:
    research_cache.clear_research_cache_states()
    monkeypatch.setattr(research_cache, "_MAX_CACHE_TTL_SECONDS", 5)
    now = {"value": 10.0}
    store = ResearchCacheStore(tmp_path / "cache.json", clock=lambda: now["value"])
    store._put("research_extraction_cache", "page", {"text": "cached"}, ttl_seconds=500)

    now["value"] = 16.0
    assert store._get("research_extraction_cache", "page") is None
    store._put("research_extraction_cache", "page", {"text": "cached"}, ttl_seconds=500)
    research_cache.clear_research_cache_states()
    assert store._get("research_extraction_cache", "page") is None


def test_retention_expires_raw_text_but_keeps_referenced_provenance(tmp_path) -> None:
    source_store = ResearchSourceStore(
        tmp_path / "sources.json",
        clock=lambda: "2026-07-01T00:00:00+00:00",
        id_factory=iter(("manifest", "snapshot")).__next__,
    )
    recorded = source_store.record_quick_search(
        "retention topic",
        "brave",
        [
            AssistantContextItem(
                source_id="web_search",
                title="Retention source",
                content="Retained provenance.",
                url="https://example.test/retention",
            )
        ],
    )
    snapshot = recorded.snapshots[0]
    source_store.save_extraction(
        snapshot.snapshot_id,
        ExtractedPage(
            requested_url="https://example.test/retention",
            final_url="https://example.test/retention",
            title="Retention source",
            published_at=None,
            text="Raw extracted text that must expire.",
            content_hash="hash",
            extractor_version="readable-html-v1",
            elapsed_ms=1,
        ),
    )
    raw_path = source_store.get_manifest(recorded.manifest.manifest_id).snapshots[0].extracted_text_ref
    assert raw_path

    result = ResearchRetentionService(
        source_store=source_store,
        cache_store=ResearchCacheStore(tmp_path / "cache.sqlite"),
        policy=ResearchPolicy(raw_snapshot_retention_days=1, source_manifest_retention_days=30),
    ).cleanup(now=datetime(2026, 7, 3, tzinfo=timezone.utc))

    restored = source_store.get_manifest(recorded.manifest.manifest_id)
    assert restored is not None
    assert len(restored.sources) == 1
    assert len(restored.snapshots) == 1
    assert restored.snapshots[0].extracted_text_ref is None
    assert restored.snapshots[0].content_hash is None
    assert restored.snapshots[0].extraction_status == "expired"
    assert result["research_extract_files"] == 1
    assert result["research_snapshots_redacted"] == 1


def test_privacy_contract_excludes_history_raw_pages_and_connected_data() -> None:
    contract = privacy_contract()
    assert contract["planner_receives_conversation_history"] is False
    assert contract["synthesis_receives_raw_page_bodies"] is False
    assert contract["credentials_browser_readable"] is False
    assert contract["unrelated_connected_data_included"] is False
