"""Owner-isolated provider-free memory repository.

Production installs the tenant-scoped PostgreSQL adapter. Tests use the
in-memory canonical repository with owner-aware filtering; no SQLite behavior
or schema remains.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .models import MemoryCandidate, MemoryRecord, MemorySnapshot
from .repository import InMemoryMemoryRepository


class OwnerAwareInMemoryMemoryRepository(InMemoryMemoryRepository):
    def __init__(self, db_path: str | Path | None = None) -> None:
        super().__init__(db_path)

    def list_records(
        self,
        *,
        owner_type: str | None = None,
        owner_id: str | None = None,
        scope: str | None = None,
        scope_id: str | None = None,
        status: str | None = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        values = super().list_records(
            scope=scope,
            scope_id=scope_id,
            status=status,
            limit=10_000,
            offset=0,
        )
        values = [
            record
            for record in values
            if (owner_type is None or record.owner_type == owner_type)
            and (owner_id is None or record.owner_id == owner_id)
        ]
        start = max(0, int(offset))
        return deepcopy(values[start : start + max(0, min(int(limit), 500))])

    def create_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate:
        return super().create_candidate(candidate)

    def list_candidates(
        self,
        *,
        owner_type: str | None = None,
        owner_id: str | None = None,
        status: str = "pending",
        limit: int = 100,
    ) -> list[MemoryCandidate]:
        values = super().list_candidates(status=status, limit=10_000)
        values = [
            candidate
            for candidate in values
            if (owner_type is None or candidate.owner_type == owner_type)
            and (owner_id is None or candidate.owner_id == owner_id)
        ]
        return deepcopy(values[: max(0, min(int(limit), 500))])

    def latest_snapshot(
        self,
        session_id: str,
        *,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> MemorySnapshot | None:
        with self._state.lock:
            values = [
                snapshot
                for snapshot in self._state.snapshots.values()
                if snapshot.session_id == session_id
                and (owner_type is None or snapshot.owner_type == owner_type)
                and (owner_id is None or snapshot.owner_id == owner_id)
            ]
            values.sort(
                key=lambda item: (item.revision, item.created_at, item.id),
                reverse=True,
            )
            return deepcopy(values[0]) if values else None


# Transitional historical symbol. It is in-memory and contains no SQLite code.
OwnerAwareSQLiteMemoryRepository = OwnerAwareInMemoryMemoryRepository


__all__ = [
    "OwnerAwareInMemoryMemoryRepository",
    "OwnerAwareSQLiteMemoryRepository",
]
