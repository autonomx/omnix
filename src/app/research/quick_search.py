"""Bounded single-query execution for Quick Search."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from app.assistant_context.models import AssistantContextItem
from app.assistant_context.web_search import WebSearchClient

from .cache import ResearchCacheStore
from .contracts import ResearchSource, ResearchSourceSnapshot
from .extraction import ReadablePageExtractor
from .policy import (
    ResearchPolicy,
    ResearchRateLimitError,
    ResearchRateLimiter,
    research_policy_from_env,
)
from .source_store import ResearchSourceStore, default_research_source_store

_DEFAULT_DEADLINE_SECONDS = 8.0
_MAX_TRANSPORT_ATTEMPTS = 2

_PROVIDER_COVERAGE = {
    "brave": "general web search",
    "tavily": "general web search",
    "searxng": "general web search",
    "duckduckgo": "limited reference and instant-answer fallback",
}


@dataclass(slots=True)
class QuickSearchExecution:
    items: list[AssistantContextItem] = field(default_factory=list)
    sources: list[ResearchSource] = field(default_factory=list)
    snapshots: list[ResearchSourceSnapshot] = field(default_factory=list)
    source_manifest_id: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)
    warnings: list[dict[str, object]] = field(default_factory=list)


class QuickSearchService:
    """Run one logical query inside one absolute wall-clock budget."""

    def __init__(
        self,
        *,
        client_factory: Callable[[float], WebSearchClient] | None = None,
        source_store_factory: Callable[[], ResearchSourceStore] | None = default_research_source_store,
        extractor_factory: Callable[[], ReadablePageExtractor] | None = ReadablePageExtractor,
        cache_store_factory: Callable[[], ResearchCacheStore] | None = ResearchCacheStore,
        rate_limiter_factory: Callable[[], ResearchRateLimiter] | None = ResearchRateLimiter,
        research_policy: ResearchPolicy | None = None,
        deadline_seconds: float = _DEFAULT_DEADLINE_SECONDS,
        max_transport_attempts: int = _MAX_TRANSPORT_ATTEMPTS,
        max_extracts: int = 2,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client_factory = client_factory or (
            lambda timeout_seconds: WebSearchClient(timeout_seconds=timeout_seconds)
        )
        self.source_store_factory = source_store_factory
        self.extractor_factory = extractor_factory
        self.cache_store_factory = cache_store_factory
        self.rate_limiter_factory = rate_limiter_factory
        self.research_policy = research_policy or research_policy_from_env()
        self.deadline_seconds = max(0.1, float(deadline_seconds))
        self.max_transport_attempts = max(1, min(2, int(max_transport_attempts)))
        self.max_extracts = max(0, min(3, int(max_extracts)))
        self.monotonic = monotonic

    def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        identity: str = "anonymous",
        locale: str = "default",
        freshness: str = "default",
    ) -> QuickSearchExecution:
        clean_query = " ".join(str(query or "").split()).strip()
        started = self.monotonic()
        diagnostics: dict[str, object] = {
            "logical_queries": 1 if clean_query else 0,
            "transport_attempts": 0,
            "deadline_ms": round(self.deadline_seconds * 1000),
            "status": "skipped" if not clean_query else "running",
            "cache_hit": False,
        }
        warnings: list[dict[str, object]] = []
        if not clean_query:
            return QuickSearchExecution(diagnostics=diagnostics)

        cache = self.cache_store_factory() if self.cache_store_factory else None
        limiter = self.rate_limiter_factory() if self.rate_limiter_factory else None
        last_error: Exception | None = None
        provider = ""
        for attempt in range(1, self.max_transport_attempts + 1):
            remaining = self.deadline_seconds - (self.monotonic() - started)
            if remaining <= 0:
                warnings.append({
                    "code": "quick_search_deadline_exhausted",
                    "message": "Quick Search reached its total deadline.",
                })
                break
            client = self.client_factory(remaining)
            provider = str(getattr(client, "provider", "") or "unknown").strip().lower()
            diagnostics["provider"] = provider
            diagnostics["coverage"] = provider_coverage(provider)

            if attempt == 1 and cache is not None:
                try:
                    cached = cache.get_search(
                        provider=provider,
                        query=clean_query,
                        locale=locale,
                        max_results=max_results,
                        freshness=freshness,
                    )
                except Exception as exc:
                    diagnostics["cache_error"] = f"{type(exc).__name__}: {exc}"
                    cached = None
                if cached is not None:
                    items = [AssistantContextItem.model_validate(item) for item in cached]
                    diagnostics.update({
                        "status": "cached" if items else "cached_empty",
                        "cache_hit": True,
                        "results": len(items),
                        "elapsed_ms": round((self.monotonic() - started) * 1000),
                    })
                    self._append_provider_warnings(provider, items, warnings)
                    return self._record_sources(clean_query, provider, items, diagnostics, warnings)

            diagnostics["transport_attempts"] = attempt
            try:
                if limiter is not None:
                    limiter.provider_request(identity, provider, self.research_policy)
                items = client.search(clean_query, max_results)
                if cache is not None:
                    cache.put_search(
                        provider=provider,
                        query=clean_query,
                        locale=locale,
                        max_results=max_results,
                        freshness=freshness,
                        results=items,
                        ttl_seconds=self.research_policy.search_cache_ttl_seconds,
                    )
                diagnostics["status"] = "completed" if items else "empty"
                diagnostics["results"] = len(items)
                diagnostics["elapsed_ms"] = round((self.monotonic() - started) * 1000)
                self._append_provider_warnings(provider, items, warnings)
                return self._record_sources(clean_query, provider, items, diagnostics, warnings)
            except ResearchRateLimitError as exc:
                diagnostics.update({
                    "status": "rate_limited",
                    "retry_after_seconds": exc.retry_after_seconds,
                    "elapsed_ms": round((self.monotonic() - started) * 1000),
                })
                warnings.append({
                    "code": "provider_rate_limited",
                    "message": "The research provider request limit was reached.",
                    "details": {"retry_after_seconds": exc.retry_after_seconds},
                })
                return QuickSearchExecution(diagnostics=diagnostics, warnings=warnings)
            except Exception as exc:  # provider boundary
                last_error = exc
                if attempt >= self.max_transport_attempts or not is_transient_search_error(exc):
                    break

        diagnostics["status"] = "failed"
        diagnostics["elapsed_ms"] = round((self.monotonic() - started) * 1000)
        if last_error is not None:
            diagnostics["error"] = f"{type(last_error).__name__}: {last_error}"
        warnings.append({
            "code": "quick_search_unavailable",
            "message": "Fresh web context was unavailable; the chat turn can continue without it.",
        })
        return QuickSearchExecution(diagnostics=diagnostics, warnings=warnings)

    def _record_sources(
        self,
        query: str,
        provider: str,
        items: list[AssistantContextItem],
        diagnostics: dict[str, object],
        warnings: list[dict[str, object]],
    ) -> QuickSearchExecution:
        if not items or self.source_store_factory is None:
            return QuickSearchExecution(items=items, diagnostics=diagnostics, warnings=warnings)
        store = self.source_store_factory()
        try:
            recorded = store.record_quick_search(query, provider, items)
        except Exception as exc:
            diagnostics["source_manifest_status"] = "failed"
            diagnostics["source_manifest_error"] = f"{type(exc).__name__}: {exc}"
            warnings.append({
                "code": "source_manifest_unavailable",
                "message": "Search results were usable, but their durable source manifest could not be saved.",
            })
            return QuickSearchExecution(items=items, diagnostics=diagnostics, warnings=warnings)

        snapshots = list(recorded.snapshots)
        extracted = 0
        extraction_failures = 0
        if self.extractor_factory is not None and self.max_extracts:
            extractor = self.extractor_factory()
            for index, (item, snapshot) in enumerate(zip(recorded.items, snapshots, strict=False)):
                if extracted >= self.max_extracts or not item.url:
                    continue
                try:
                    page = extractor.extract(item.url)
                    updated = store.save_extraction(snapshot.snapshot_id, page)
                    snapshots[index] = updated
                    item.metadata.update({
                        "extraction_status": "completed",
                        "extractor_version": page.extractor_version,
                        "content_hash": page.content_hash,
                        "extracted_text_ref": updated.extracted_text_ref,
                        "extracted_title": page.title,
                        "extracted_excerpt": page.text[:4000],
                    })
                    extracted += 1
                except Exception as exc:
                    snapshots[index] = store.mark_extraction_failed(snapshot.snapshot_id) or snapshot
                    item.metadata["extraction_status"] = "failed"
                    item.metadata["extraction_error"] = f"{type(exc).__name__}: {exc}"
                    extraction_failures += 1
            if extraction_failures:
                warnings.append({
                    "code": "page_extraction_partial",
                    "message": "Some search results could not be safely extracted; snippets remain available.",
                    "details": {"failures": extraction_failures},
                })
        diagnostics.update({
            "source_manifest_status": "completed",
            "source_manifest_id": recorded.manifest.manifest_id,
            "source_count": len(recorded.sources),
            "snapshot_count": len(snapshots),
            "extracted_pages": extracted,
            "extraction_failures": extraction_failures,
        })
        return QuickSearchExecution(
            items=recorded.items,
            sources=recorded.sources,
            snapshots=snapshots,
            source_manifest_id=recorded.manifest.manifest_id,
            diagnostics=diagnostics,
            warnings=warnings,
        )

    @staticmethod
    def _append_provider_warnings(
        provider: str,
        items: list[AssistantContextItem],
        warnings: list[dict[str, object]],
    ) -> None:
        if provider == "duckduckgo":
            warnings.append({
                "code": "limited_search_provider",
                "message": "DuckDuckGo Instant Answer provides limited reference coverage.",
            })
        if not items:
            warnings.append({
                "code": "quick_search_empty",
                "message": "The configured provider returned no usable results; this does not prove the web has no answer.",
            })


def provider_coverage(provider: str) -> str:
    return _PROVIDER_COVERAGE.get(str(provider or "").strip().lower(), "provider-defined web coverage")


def is_transient_search_error(error: Exception) -> bool:
    text = f"{type(error).__name__}: {error}".lower()
    permanent_markers = (
        "401", "403", "authentication", "api key is required",
        "unsupported provider", "policy", "malformed",
    )
    if any(marker in text for marker in permanent_markers):
        return False
    transient_markers = (
        "timeout", "timed out", "temporar", "connection",
        "429", "500", "502", "503", "504",
    )
    return any(marker in text for marker in transient_markers)
