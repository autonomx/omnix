"""Bounded single-query execution for Quick Search."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from app.assistant_context.models import AssistantContextItem
from app.assistant_context.web_search import WebSearchClient

from .contracts import ResearchSource, ResearchSourceSnapshot
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
        deadline_seconds: float = _DEFAULT_DEADLINE_SECONDS,
        max_transport_attempts: int = _MAX_TRANSPORT_ATTEMPTS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client_factory = client_factory or (
            lambda timeout_seconds: WebSearchClient(timeout_seconds=timeout_seconds)
        )
        self.source_store_factory = source_store_factory
        self.deadline_seconds = max(0.1, float(deadline_seconds))
        self.max_transport_attempts = max(1, min(2, int(max_transport_attempts)))
        self.monotonic = monotonic

    def search(self, query: str, max_results: int = 5) -> QuickSearchExecution:
        clean_query = " ".join(str(query or "").split()).strip()
        started = self.monotonic()
        diagnostics: dict[str, object] = {
            "logical_queries": 1 if clean_query else 0,
            "transport_attempts": 0,
            "deadline_ms": round(self.deadline_seconds * 1000),
            "status": "skipped" if not clean_query else "running",
        }
        warnings: list[dict[str, object]] = []
        if not clean_query:
            return QuickSearchExecution(diagnostics=diagnostics)

        last_error: Exception | None = None
        provider = ""
        for attempt in range(1, self.max_transport_attempts + 1):
            remaining = self.deadline_seconds - (self.monotonic() - started)
            if remaining <= 0:
                warnings.append(
                    {
                        "code": "quick_search_deadline_exhausted",
                        "message": "Quick Search reached its total deadline.",
                    }
                )
                break
            client = self.client_factory(remaining)
            provider = str(getattr(client, "provider", "") or "unknown").strip().lower()
            diagnostics["provider"] = provider
            diagnostics["coverage"] = provider_coverage(provider)
            diagnostics["transport_attempts"] = attempt
            try:
                items = client.search(clean_query, max_results)
                diagnostics["status"] = "completed" if items else "empty"
                diagnostics["results"] = len(items)
                diagnostics["elapsed_ms"] = round((self.monotonic() - started) * 1000)
                self._append_provider_warnings(provider, items, warnings)
                return self._record_sources(
                    clean_query,
                    provider,
                    items,
                    diagnostics=diagnostics,
                    warnings=warnings,
                )
            except Exception as exc:  # provider boundary
                last_error = exc
                if attempt >= self.max_transport_attempts or not is_transient_search_error(exc):
                    break

        diagnostics["status"] = "failed"
        diagnostics["elapsed_ms"] = round((self.monotonic() - started) * 1000)
        if last_error is not None:
            diagnostics["error"] = f"{type(last_error).__name__}: {last_error}"
        warnings.append(
            {
                "code": "quick_search_unavailable",
                "message": "Fresh web context was unavailable; the chat turn can continue without it.",
            }
        )
        return QuickSearchExecution(diagnostics=diagnostics, warnings=warnings)

    def _record_sources(
        self,
        query: str,
        provider: str,
        items: list[AssistantContextItem],
        *,
        diagnostics: dict[str, object],
        warnings: list[dict[str, object]],
    ) -> QuickSearchExecution:
        if not items or self.source_store_factory is None:
            return QuickSearchExecution(items=items, diagnostics=diagnostics, warnings=warnings)
        try:
            recorded = self.source_store_factory().record_quick_search(query, provider, items)
        except Exception as exc:
            diagnostics["source_manifest_status"] = "failed"
            diagnostics["source_manifest_error"] = f"{type(exc).__name__}: {exc}"
            warnings.append(
                {
                    "code": "source_manifest_unavailable",
                    "message": "Search results were usable, but their durable source manifest could not be saved.",
                }
            )
            return QuickSearchExecution(items=items, diagnostics=diagnostics, warnings=warnings)
        diagnostics["source_manifest_status"] = "completed"
        diagnostics["source_manifest_id"] = recorded.manifest.manifest_id
        diagnostics["source_count"] = len(recorded.sources)
        diagnostics["snapshot_count"] = len(recorded.snapshots)
        return QuickSearchExecution(
            items=recorded.items,
            sources=recorded.sources,
            snapshots=recorded.snapshots,
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
            warnings.append(
                {
                    "code": "limited_search_provider",
                    "message": "DuckDuckGo Instant Answer provides limited reference coverage.",
                }
            )
        if not items:
            warnings.append(
                {
                    "code": "quick_search_empty",
                    "message": "The configured provider returned no usable results; this does not prove the web has no answer.",
                }
            )


def provider_coverage(provider: str) -> str:
    return _PROVIDER_COVERAGE.get(str(provider or "").strip().lower(), "provider-defined web coverage")


def is_transient_search_error(error: Exception) -> bool:
    text = f"{type(error).__name__}: {error}".lower()
    permanent_markers = (
        "401",
        "403",
        "authentication",
        "api key is required",
        "unsupported provider",
        "policy",
        "malformed",
    )
    if any(marker in text for marker in permanent_markers):
        return False
    transient_markers = (
        "timeout",
        "timed out",
        "temporar",
        "connection",
        "429",
        "500",
        "502",
        "503",
        "504",
    )
    return any(marker in text for marker in transient_markers)
