"""TTL-bounded search and extraction caches for web research."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

from app.runtime_paths import resources_data_root


def default_research_cache_path() -> Path:
    override = os.environ.get("OMNIX_RESEARCH_CACHE_DB_PATH")
    return Path(override) if override else resources_data_root() / "research_cache.sqlite"


class ResearchCacheStore:
    def __init__(
        self,
        path: str | Path | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path) if path is not None else default_research_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_search_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_extraction_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_search_expiry "
                "ON research_search_cache(expires_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_extraction_expiry "
                "ON research_extraction_cache(expires_at)"
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
        key = search_cache_key(provider, query, locale, max_results, freshness)
        payload = self._get("research_search_cache", key)
        if not isinstance(payload, list):
            return None
        return [item for item in payload if isinstance(item, dict)]

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
        key = search_cache_key(provider, query, locale, max_results, freshness)
        serializable = [_serializable(item) for item in results]
        self._put("research_search_cache", key, serializable, ttl_seconds)

    def get_extraction(
        self,
        *,
        canonical_url: str,
        extractor_version: str,
    ) -> dict[str, Any] | None:
        key = extraction_cache_key(canonical_url, extractor_version)
        payload = self._get("research_extraction_cache", key)
        return payload if isinstance(payload, dict) else None

    def put_extraction(
        self,
        *,
        canonical_url: str,
        extractor_version: str,
        page: Any,
        ttl_seconds: int,
    ) -> None:
        key = extraction_cache_key(canonical_url, extractor_version)
        payload = _serializable(page)
        content_hash = str(payload.get("content_hash") or "") if isinstance(payload, dict) else ""
        self._put(
            "research_extraction_cache",
            key,
            payload,
            ttl_seconds,
            content_hash=content_hash or None,
        )

    def purge_expired(self) -> dict[str, int]:
        now = self.clock()
        counts: dict[str, int] = {}
        with self._connect() as connection:
            for table in ("research_search_cache", "research_extraction_cache"):
                cursor = connection.execute(f"DELETE FROM {table} WHERE expires_at <= ?", (now,))
                counts[table] = max(0, cursor.rowcount)
        return counts

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM research_search_cache")
            connection.execute("DELETE FROM research_extraction_cache")

    def _get(self, table: str, key: str) -> Any | None:
        now = self.clock()
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT payload_json, expires_at FROM {table} WHERE cache_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            if float(row["expires_at"]) <= now:
                connection.execute(f"DELETE FROM {table} WHERE cache_key = ?", (key,))
                return None
        try:
            return json.loads(str(row["payload_json"]))
        except json.JSONDecodeError:
            return None

    def _put(
        self,
        table: str,
        key: str,
        payload: Any,
        ttl_seconds: int,
        *,
        content_hash: str | None = None,
    ) -> None:
        now = self.clock()
        expires_at = now + max(1, int(ttl_seconds))
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            if table == "research_extraction_cache":
                connection.execute(
                    """
                    INSERT INTO research_extraction_cache(
                        cache_key, payload_json, content_hash, created_at, expires_at
                    ) VALUES(?,?,?,?,?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        payload_json=excluded.payload_json,
                        content_hash=excluded.content_hash,
                        created_at=excluded.created_at,
                        expires_at=excluded.expires_at
                    """,
                    (key, serialized, content_hash, now, expires_at),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO research_search_cache(
                        cache_key, payload_json, created_at, expires_at
                    ) VALUES(?,?,?,?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        payload_json=excluded.payload_json,
                        created_at=excluded.created_at,
                        expires_at=excluded.expires_at
                    """,
                    (key, serialized, now, expires_at),
                )


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
