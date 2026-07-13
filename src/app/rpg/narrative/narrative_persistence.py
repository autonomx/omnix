"""Narrative event persistence compatibility boundary.

PostgreSQL is installed for production. Provider-free tests use an in-memory
store; no SQLite schema or connection remains.
"""
from __future__ import annotations

import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from .narrative_event import NarrativeEvent


_EVENTS: dict[str, list[dict[str, Any]]] = {}
_EVENTS_LOCK = threading.RLock()


class InMemoryNarrativeEventStore:
    def __init__(self, db_path: str | None = None, session_id: str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else Path(":memory:narrative")
        self.session_id = session_id or f"session_{int(time.time())}"
        self._key = str(self.db_path)

    def save_events(
        self,
        events: list[NarrativeEvent],
        session_id: str | None = None,
        tick: int = 0,
    ) -> int:
        sid = session_id or self.session_id
        now = time.time()
        with _EVENTS_LOCK:
            records = _EVENTS.setdefault(self._key, [])
            known = {item["id"] for item in records}
            for event in events:
                if event.id in known:
                    continue
                records.append(
                    {
                        "id": event.id,
                        "session_id": sid,
                        "tick": int(tick),
                        "timestamp": now,
                        "event": deepcopy(event),
                    }
                )
                known.add(event.id)
        return len(events)

    def get_history(
        self,
        limit: int = 100,
        offset: int = 0,
        event_type: str | None = None,
        min_importance: float = 0.0,
    ) -> list[NarrativeEvent]:
        with _EVENTS_LOCK:
            rows = [
                item
                for item in _EVENTS.setdefault(self._key, [])
                if (event_type is None or item["event"].type == event_type)
                and item["event"].importance >= min_importance
            ]
            rows.sort(key=lambda item: (item["timestamp"], item["id"]), reverse=True)
            return [deepcopy(item["event"]) for item in rows[offset : offset + limit]]

    def get_session_events(
        self,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[NarrativeEvent]:
        sid = session_id or self.session_id
        with _EVENTS_LOCK:
            rows = [item for item in _EVENTS.setdefault(self._key, []) if item["session_id"] == sid]
            rows.sort(key=lambda item: (item["timestamp"], item["id"]), reverse=True)
            return [deepcopy(item["event"]) for item in rows[:limit]]

    def get_session_ids(self) -> list[str]:
        with _EVENTS_LOCK:
            return sorted({item["session_id"] for item in _EVENTS.setdefault(self._key, [])})

    def get_event_counts(self, session_id: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        with _EVENTS_LOCK:
            for item in _EVENTS.setdefault(self._key, []):
                if session_id and item["session_id"] != session_id:
                    continue
                kind = item["event"].type
                counts[kind] = counts.get(kind, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def delete_session(self, session_id: str) -> int:
        with _EVENTS_LOCK:
            records = _EVENTS.setdefault(self._key, [])
            before = len(records)
            _EVENTS[self._key] = [item for item in records if item["session_id"] != session_id]
            return before - len(_EVENTS[self._key])

    def clear_all(self) -> None:
        with _EVENTS_LOCK:
            _EVENTS[self._key] = []

    def get_total_count(self) -> int:
        with _EVENTS_LOCK:
            return len(_EVENTS.setdefault(self._key, []))


NarrativeEventStore = InMemoryNarrativeEventStore
