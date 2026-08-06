from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(slots=True)
class CacheEntry:
    value: dict[str, Any]
    expires_at: float
    source: str
    fingerprint: str


class TradingMarketDataCache:
    """Bounded disposable cache with request coalescing; never user authority."""

    def __init__(self, *, max_entries: int = 256, cache_dir: Path | None = None) -> None:
        self.max_entries = max(1, int(max_entries))
        self.cache_dir = cache_dir
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.RLock()

    @staticmethod
    def key(*parts: object) -> str:
        return ":".join(str(part).strip() for part in parts)

    @staticmethod
    def fingerprint(value: dict[str, Any]) -> str:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _disk_name(key: str) -> str:
        return f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def _disk_path(self, key: str) -> Path | None:
        return self.cache_dir / self._disk_name(key) if self.cache_dir else None

    def _read_disk(self, key: str, *, allow_stale: bool) -> CacheEntry | None:
        path = self._disk_path(key)
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("key") != key or not isinstance(payload.get("value"), dict):
                raise ValueError("cache key or value mismatch")
            value = dict(payload["value"])
            fingerprint = str(payload.get("fingerprint") or "")
            if fingerprint != self.fingerprint(value):
                raise ValueError("cache fingerprint mismatch")
            entry = CacheEntry(
                value=value,
                expires_at=float(payload["expires_at"]),
                source=str(payload.get("source") or "unknown"),
                fingerprint=fingerprint,
            )
            if entry.expires_at < time.time() and not allow_stale:
                path.unlink(missing_ok=True)
                return None
            return entry
        except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError):
            path.unlink(missing_ok=True)
            return None

    def _prune_disk_locked(self) -> None:
        if self.cache_dir is None or not self.cache_dir.exists():
            return
        now = time.time()
        valid: list[tuple[float, Path]] = []
        for path in self.cache_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                expires_at = float(payload["expires_at"])
                if expires_at < now:
                    path.unlink(missing_ok=True)
                    continue
                valid.append((path.stat().st_mtime, path))
            except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError):
                path.unlink(missing_ok=True)
        for _, path in sorted(valid)[: max(0, len(valid) - self.max_entries)]:
            path.unlink(missing_ok=True)

    def get(self, key: str, *, allow_stale: bool = False) -> CacheEntry | None:
        with self._guard:
            entry = self._entries.get(key)
            if entry is not None:
                if entry.expires_at < time.time() and not allow_stale:
                    self._entries.pop(key, None)
                    path = self._disk_path(key)
                    if path is not None:
                        path.unlink(missing_ok=True)
                    return None
                self._entries.move_to_end(key)
                return entry
            entry = self._read_disk(key, allow_stale=allow_stale)
            if entry is None:
                return None
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            return entry

    def put(self, key: str, value: dict[str, Any], *, ttl_seconds: float, source: str) -> CacheEntry:
        entry = CacheEntry(
            value=value,
            expires_at=time.time() + max(0.0, ttl_seconds),
            source=source,
            fingerprint=self.fingerprint(value),
        )
        with self._guard:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                evicted_key, _ = self._entries.popitem(last=False)
                evicted_path = self._disk_path(evicted_key)
                if evicted_path is not None:
                    evicted_path.unlink(missing_ok=True)
            if self.cache_dir is not None:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                path = self._disk_path(key)
                assert path is not None
                temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
                temporary.write_text(
                    json.dumps(
                        {
                            "key": key,
                            "value": value,
                            "expires_at": entry.expires_at,
                            "source": source,
                            "fingerprint": entry.fingerprint,
                        },
                        sort_keys=True,
                        default=str,
                    ),
                    encoding="utf-8",
                )
                temporary.replace(path)
                self._prune_disk_locked()
        return entry

    def get_or_load(
        self,
        key: str,
        loader: Callable[[], dict[str, Any]],
        *,
        ttl_seconds: float,
        source: str,
    ) -> tuple[dict[str, Any], CacheEntry, bool]:
        cached = self.get(key)
        if cached is not None:
            return cached.value, cached, True
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        try:
            with lock:
                cached = self.get(key)
                if cached is not None:
                    return cached.value, cached, True
                value = loader()
                entry = self.put(key, value, ttl_seconds=ttl_seconds, source=source)
                return value, entry, False
        finally:
            with self._guard:
                self._locks.pop(key, None)

    def clear(self) -> None:
        with self._guard:
            self._entries.clear()
            self._locks.clear()
            if self.cache_dir and self.cache_dir.exists():
                for path in self.cache_dir.glob("*.json"):
                    path.unlink(missing_ok=True)
                for path in self.cache_dir.glob("*.tmp"):
                    path.unlink(missing_ok=True)
