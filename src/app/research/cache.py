"""TTL-bounded in-memory caches for web research.

These records are explicitly reconstructible and disposable. Durable research
metadata lives in PostgreSQL; no SQLite cache database remains.
"""
from __future__ import annotations

import threading
import time
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable


_CACHE_STATES: dict[str, dict[str, dict[str, Any]]] = {}
_CACHE_LOCK = threading.RLock()


def default_research_cache_path() -> Path:
    return Path(":memory:research-cache")


class ResearchCacheStore:
    def __init__(
        self,
        path: str | Path | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path) if path is not None else default_research_cache_path()
        self.clock = clock
        with _CACHE_LOCK:
            _CACHE_STATES.setdefault(
                str(self.path),
                {"research_search_cache": {}, "research_extraction_cache": {}},
            )

    def get_search(
        self,
        *,
        provider: str,
        query: str,
        locale: str,
        max_results: int,
        freshness: str,
    ) -> list[dict[str, Any]] | None:
        value = self._get(
            "research_search_cache",
            search_cache_key(provider, query, locale, max_results, freshness),
        )
        if not isinstance(value, list):
            return None
        return [dict(item) for item in value if isinstance(item, dict)]

    def put_search(
        self,
        *,
        provider: str,
        query: str,
        locale: str,
        max_results: int,
        freshness: str,
        results: list[Any],
        ttl_seconds: int,
    ) -> None:
        self._put(
            "research_search_cache",
            search_cache_key(provider, query, locale, max_results, freshness),
            [_serializable(item) for item in results],
            ttl_seconds,
        )

    def get_extraction(
        self,
        *,
        canonical_url: str,
        extractor_version: str,
    ) -> dict[str, Any] | None:
        value = self._get(
            "research_extraction_cache",
            extraction_cache_key(canonical_url, extractor_version),
        )
        return dict(value) if isinstance(value, dict) else None

    def put_extraction(
        self,
        *,
        canonical_url: str,
        extractor_version: str,
        page: Any,
        ttl_seconds: int,
    ) -> None:
        self._put(
            "research_extraction_cache",
            extraction_cache_key(canonical_url, extractor_version),
            _serializable(page),
            ttl_seconds,
        )

    def purge_expired(self) -> dict[str, int]:
        now = self.clock()
        counts: dict[str, int] = {}
        with _CACHE_LOCK:
            state = _CACHE_STATES[str(self.path)]
            for name, values in state.items():
                expired = [key for key, item in values.items() if float(item["expires_at"]) <= now]
                for key in expired:
                    values.pop(key, None)
                counts[name] = len(expired)
        return counts

    def clear(self) -> None:
        with _CACHE_LOCK:
            state = _CACHE_STATES[str(self.path)]
            state["research_search_cache"].clear()
            state["research_extraction_cache"].clear()

    def _get(self, table: str, key: str) -> Any | None:
        now = self.clock()
        with _CACHE_LOCK:
            item = _CACHE_STATES[str(self.path)][table].get(key)
            if item is None:
                return None
            if float(item["expires_at"]) <= now:
                _CACHE_STATES[str(self.path)][table].pop(key, None)
                return None
            return deepcopy(item["payload"])

    def _put(self, table: str, key: str, payload: Any, ttl_seconds: int) -> None:
        now = self.clock()
        with _CACHE_LOCK:
            _CACHE_STATES[str(self.path)][table][key] = {
                "payload": deepcopy(payload),
                "created_at": now,
                "expires_at": now + max(1, int(ttl_seconds)),
            }


def search_cache_key(
    provider: str,
    query: str,
    locale: str,
    max_results: int,
    freshness: str,
) -> str:
    normalized_query = " ".join(str(query or "").lower().split())
    return "|".join(
        (
            str(provider or "unknown").strip().lower(),
            normalized_query,
            str(locale or "default").strip().lower(),
            str(max(1, int(max_results))),
            str(freshness or "default").strip().lower(),
        )
    )


def extraction_cache_key(canonical_url: str, extractor_version: str) -> str:
    return f"{str(canonical_url).strip()}|{str(extractor_version).strip()}"


def _serializable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    return value
