"""Curated assistant-memory repository compatibility boundary.

PostgreSQL is installed for production. Provider-free tests use a deterministic
in-memory repository; no SQLite schema or connection remains.
"""
from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import MemoryCandidate, MemoryRecord, MemorySnapshot


class MemoryConflictError(RuntimeError):
    """Raised when an optimistic revision or pending-state check fails."""


class MemoryNotFoundError(KeyError):
    """Raised when a requested memory entity does not exist."""


def default_memory_db_path() -> Path:
    return Path(":memory:assistant-memory")


@dataclass
class _State:
    lock: threading.RLock = field(default_factory=threading.RLock)
    records: dict[str, MemoryRecord] = field(default_factory=dict)
    candidates: dict[str, MemoryCandidate] = field(default_factory=dict)
    snapshots: dict[str, MemorySnapshot] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    next_event_id: int = 1


_STATES: dict[str, _State] = {}
_STATES_LOCK = threading.RLock()


def _state(path: str | Path | None) -> _State:
    key = str(path or default_memory_db_path())
    with _STATES_LOCK:
        return _STATES.setdefault(key, _State())


class InMemoryMemoryRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_memory_db_path()
        self._state = _state(db_path)

    def create_record(self, record: MemoryRecord) -> MemoryRecord:
        with self._state.lock:
            if record.id in self._state.records:
                raise MemoryConflictError(f"memory record already exists: {record.id}")
            self._state.records[record.id] = deepcopy(record)
            self._append_event("record", record.id, "memory.created", {
                "scope": record.scope,
                "scope_id": record.scope_id,
                "revision": record.revision,
            })
            return deepcopy(record)

    def get_record(self, record_id: str) -> MemoryRecord | None:
        with self._state.lock:
            value = self._state.records.get(record_id)
            return deepcopy(value) if value is not None else None

    def list_records(
        self,
        *,
        scope: str | None = None,
        scope_id: str | None = None,
        status: str | None = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        with self._state.lock:
            values = [
                record
                for record in self._state.records.values()
                if (scope is None or record.scope == scope)
                and (scope_id is None or record.scope_id == scope_id)
                and (status is None or record.status == status)
            ]
            values.sort(key=lambda item: (not item.pinned, item.updated_at, item.id))
            start = max(0, int(offset))
            return deepcopy(values[start : start + max(0, min(int(limit), 500))])

    def update_record(self, record: MemoryRecord, *, expected_revision: int) -> MemoryRecord:
        with self._state.lock:
            current = self._state.records.get(record.id)
            if current is None:
                raise MemoryNotFoundError(record.id)
            if current.revision != expected_revision:
                raise MemoryConflictError(
                    f"memory revision conflict for {record.id}: expected {expected_revision}, actual {current.revision}"
                )
            updated = record.model_copy(update={"revision": expected_revision + 1})
            self._state.records[record.id] = deepcopy(updated)
            self._append_event("record", record.id, "memory.updated", {"revision": updated.revision})
            return deepcopy(updated)

    def forget_record(self, record_id: str, *, expected_revision: int) -> bool:
        with self._state.lock:
            current = self._state.records.get(record_id)
            if current is None:
                return False
            if current.revision != expected_revision:
                raise MemoryConflictError(
                    f"memory revision conflict for {record_id}: expected {expected_revision}"
                )
            self._state.records.pop(record_id, None)
            self._state.snapshots = {
                key: snapshot.model_copy(
                    update={
                        "items": [
                            item
                            for item in snapshot.items
                            if item.memory_record_id != record_id
                        ]
                    }
                )
                for key, snapshot in self._state.snapshots.items()
            }
            self._append_event("record", record_id, "memory.forgotten", {
                "forgotten_revision": expected_revision,
            })
            return True

    def create_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate:
        with self._state.lock:
            for existing in self._state.candidates.values():
                if (
                    existing.source_message_id == candidate.source_message_id
                    and existing.candidate_fingerprint == candidate.candidate_fingerprint
                ):
                    return deepcopy(existing)
            self._state.candidates[candidate.id] = deepcopy(candidate)
            self._append_event("candidate", candidate.id, "memory.candidate_created", {})
            return deepcopy(candidate)

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        with self._state.lock:
            value = self._state.candidates.get(candidate_id)
            return deepcopy(value) if value is not None else None

    def list_candidates(self, *, status: str = "pending", limit: int = 100) -> list[MemoryCandidate]:
        with self._state.lock:
            values = [item for item in self._state.candidates.values() if item.status == status]
            values.sort(key=lambda item: (item.created_at, item.id))
            return deepcopy(values[: max(0, min(int(limit), 500))])

    def reject_candidate(self, candidate_id: str, *, resolved_at: str) -> MemoryCandidate:
        return self._resolve_candidate(candidate_id, "rejected", resolved_at)

    def delete_candidate(self, candidate_id: str, *, expected_status: str | None = None) -> bool:
        with self._state.lock:
            current = self._state.candidates.get(candidate_id)
            if current is None:
                return False
            if expected_status is not None and current.status != expected_status:
                raise MemoryConflictError(
                    f"candidate {candidate_id} is {current.status}, expected {expected_status}"
                )
            self._state.candidates.pop(candidate_id, None)
            self._append_event("candidate", candidate_id, "memory.candidate_deleted", {
                "deleted_status": current.status,
            })
            return True

    def accept_candidate(
        self,
        candidate_id: str,
        record: MemoryRecord,
        *,
        resolved_at: str,
    ) -> MemoryRecord:
        with self._state.lock:
            candidate = self._state.candidates.get(candidate_id)
            if candidate is None:
                raise MemoryNotFoundError(candidate_id)
            if candidate.status != "pending":
                raise MemoryConflictError(f"candidate {candidate_id} is already {candidate.status}")
            if record.id in self._state.records:
                raise MemoryConflictError(f"memory record already exists: {record.id}")
            self._state.records[record.id] = deepcopy(record)
            self._state.candidates[candidate_id] = candidate.model_copy(
                update={"status": "accepted", "resolved_at": resolved_at}
            )
            self._append_event("candidate", candidate_id, "memory.candidate_accepted", {
                "memory_record_id": record.id,
            })
            self._append_event("record", record.id, "memory.created", {
                "candidate_id": candidate_id,
                "revision": record.revision,
            })
            return deepcopy(record)

    def create_snapshot(self, snapshot: MemorySnapshot) -> MemorySnapshot:
        with self._state.lock:
            if snapshot.id in self._state.snapshots:
                raise MemoryConflictError(f"memory snapshot already exists: {snapshot.id}")
            self._state.snapshots[snapshot.id] = deepcopy(snapshot)
            self._append_event("snapshot", snapshot.id, "memory.snapshot_created", {
                "session_id": snapshot.session_id,
                "revision": snapshot.revision,
                "record_count": len(snapshot.items),
            })
            return deepcopy(snapshot)

    def get_snapshot(self, snapshot_id: str) -> MemorySnapshot | None:
        with self._state.lock:
            value = self._state.snapshots.get(snapshot_id)
            return deepcopy(value) if value is not None else None

    def latest_snapshot(self, session_id: str) -> MemorySnapshot | None:
        with self._state.lock:
            values = [item for item in self._state.snapshots.values() if item.session_id == session_id]
            values.sort(key=lambda item: (item.revision, item.created_at, item.id), reverse=True)
            return deepcopy(values[0]) if values else None

    def list_events(self, *, entity_id: str | None = None) -> list[dict[str, Any]]:
        with self._state.lock:
            values = [
                item
                for item in self._state.events
                if entity_id is None or item["entity_id"] == entity_id
            ]
            return deepcopy(values)

    def _resolve_candidate(self, candidate_id: str, status: str, resolved_at: str) -> MemoryCandidate:
        with self._state.lock:
            current = self._state.candidates.get(candidate_id)
            if current is None:
                raise MemoryNotFoundError(candidate_id)
            if current.status != "pending":
                raise MemoryConflictError(f"candidate {candidate_id} is already {current.status}")
            updated = current.model_copy(update={"status": status, "resolved_at": resolved_at})
            self._state.candidates[candidate_id] = deepcopy(updated)
            self._append_event("candidate", candidate_id, f"memory.candidate_{status}", {})
            return deepcopy(updated)

    def _append_event(
        self,
        entity_type: str,
        entity_id: str,
        event_type: str,
        metadata: dict[str, Any],
    ) -> None:
        event = {
            "id": self._state.next_event_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_type": event_type,
            "metadata": deepcopy(metadata),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._state.next_event_id += 1
        self._state.events.append(event)


# Backward-compatible import name for callers/tests that predate the PostgreSQL
# migration. This is intentionally an alias to the provider-free in-memory
# compatibility repository; it does not restore SQLite persistence.
SQLiteMemoryRepository = InMemoryMemoryRepository
