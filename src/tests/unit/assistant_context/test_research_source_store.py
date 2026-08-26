from app.assistant_context.models import AssistantContextItem
from app.research.extraction import ExtractedPage
from app.research.quick_search import QuickSearchService
from app.research.source_store import (
    ResearchSourceStore,
    canonicalize_source_url,
    stable_source_record_id,
)


class FakeSearchClient:
    provider = "brave"

    def search(self, query: str, max_results: int):
        return [
            AssistantContextItem(
                source_id="web_search",
                title="Release",
                content="Current release details.",
                url="HTTPS://Example.TEST:443/news?id=2&utm_source=test&id=1#section",
                metadata={"provider": "brave"},
            ),
            AssistantContextItem(
                source_id="web_search",
                title="Duplicate release",
                content="Duplicate URL result.",
                url="https://example.test/news?id=1&id=2",
                metadata={"provider": "brave"},
            ),
        ]


class FailingExtractionStore(ResearchSourceStore):
    def save_extraction(self, snapshot_id, page):
        raise RuntimeError("asset store unavailable")


class FakeExtractor:
    def extract(self, url: str) -> ExtractedPage:
        return ExtractedPage(
            requested_url=url,
            final_url=url,
            title="Release",
            published_at=None,
            text="Extracted release details.",
            content_hash="hash",
            extractor_version="fixture",
            elapsed_ms=1,
        )


def test_url_canonicalization_removes_tracking_fragment_and_default_port() -> None:
    assert canonicalize_source_url(
        "HTTPS://Example.TEST:443/news?utm_source=test&id=2&id=1#section"
    ) == "https://example.test/news?id=1&id=2"
    assert canonicalize_source_url("file:///tmp/private") is None


def test_stable_source_identity_uses_canonical_url() -> None:
    first = AssistantContextItem(
        source_id="web_search",
        title="One",
        content="First snippet",
        url="https://example.test/news?utm_source=a&id=1",
    )
    second = AssistantContextItem(
        source_id="web_search",
        title="Two",
        content="Second snippet",
        url="https://EXAMPLE.test:443/news?id=1#top",
    )
    first_url = canonicalize_source_url(first.url)
    second_url = canonicalize_source_url(second.url)
    assert stable_source_record_id("brave", first, canonical_url=first_url) == stable_source_record_id(
        "brave", second, canonical_url=second_url
    )


def test_quick_search_persists_manifest_with_stable_citations(tmp_path) -> None:
    ids = iter(("manifest-one", "snapshot-one", "snapshot-two"))
    store = ResearchSourceStore(
        tmp_path / "sources.json",
        clock=lambda: "2026-07-06T00:00:00Z",
        id_factory=lambda: next(ids),
    )
    result = QuickSearchService(
        client_factory=lambda timeout: FakeSearchClient(),
        source_store_factory=lambda: store,
        extractor_factory=None,
        cache_store_factory=None,
    ).search("current release", 5)

    assert len(result.items) == 1
    assert len(result.sources) == 1
    assert len(result.snapshots) == 1
    assert result.source_manifest_id == "manifest:manifest-one"
    assert result.items[0].metadata["citation_label"] == "S1"
    assert result.items[0].metadata["source_record_id"] == result.sources[0].source_record_id
    assert result.items[0].metadata["snapshot_id"] == "snapshot:snapshot-one"
    assert result.diagnostics["source_count"] == 1
    assert result.diagnostics["snapshot_count"] == 1

    restored = ResearchSourceStore(tmp_path / "sources.json").get_manifest(
        "manifest:manifest-one"
    )
    assert restored is not None
    assert restored.manifest.source_record_ids == [result.sources[0].source_record_id]
    assert restored.snapshots[0].citation_label == "S1"
    assert restored.sources[0].model_dump().get("content_hash") is None


def test_extraction_persistence_failure_keeps_search_snippet(tmp_path) -> None:
    store = FailingExtractionStore(tmp_path / "sources.json")
    result = QuickSearchService(
        client_factory=lambda timeout: FakeSearchClient(),
        source_store_factory=lambda: store,
        extractor_factory=FakeExtractor,
        cache_store_factory=None,
    ).search("current release", 5)

    assert len(result.items) == 1
    assert result.items[0].content == "Current release details."
    assert result.items[0].metadata["extraction_status"] == "failed"
    assert result.diagnostics["status"] == "completed"
    assert result.diagnostics["extraction_failures"] == 1
    assert result.warnings[-1]["code"] == "page_extraction_partial"
