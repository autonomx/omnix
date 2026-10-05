"""The curated memory repository, routed by memory authority (WP-8.5).

Memory v1's services, policy, routes, commands and snapshots work against one
repository interface. This repository keeps that interface and decides, per
call, where curated memory records live:

- while v1 is authoritative, every call goes to the v1 repository;
- once v2 is authoritative, records are read from and written to the v2
  observation log (``PostgresMemoryV2CuratedRecords``), and each write
  converges the space (derive and index) so the next prompt sees it.

Candidates (proposals awaiting approval) and session snapshots are not memory
authority; they stay in the v1 repository either way. Approving a candidate
under v2 writes the record to v2, then marks the candidate accepted.
"""
from __future__ import annotations

import logging
from typing import Any

from app.memory_contracts import (
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryRecord,
)
from app.persistence.database import PostgresDatabase, default_database

from .curated_records import (
    MemoryV2CuratedConvergence,
    PostgresMemoryV2CuratedRecords,
    memory_space,
    tenant_principal,
)
from .runtime import PostgresMemoryV2Runtime

logger = logging.getLogger(__name__)


class MemoryAuthorityRoutedRepository:
    """v1 repository interface; records follow the current memory authority."""

    def __init__(
        self,
        legacy: Any,
        *,
        database: PostgresDatabase | None = None,
        runtime: PostgresMemoryV2Runtime | None = None,
        records: PostgresMemoryV2CuratedRecords | None = None,
        convergence: MemoryV2CuratedConvergence | None = None,
    ) -> None:
        self.legacy = legacy
        self.database = database or default_database()
        self.runtime = runtime or PostgresMemoryV2Runtime(self.database)
        self.records = records or PostgresMemoryV2CuratedRecords(self.database, runtime=self.runtime)
        self.convergence = convergence or MemoryV2CuratedConvergence(self.database)

    def __getattr__(self, name: str) -> Any:
        # Candidates, snapshots, events and row helpers stay with v1.
        return getattr(self.legacy, name)

    def v2_authoritative(self) -> bool:
        return self.runtime.current().epoch.authority == "v2"

    def _converge(self, record: MemoryRecord) -> None:
        space = memory_space(tenant_principal(), record.owner_type, record.owner_id)
        try:
            self.convergence.run(space=space, max_steps=10)
        except Exception:  # noqa: BLE001 - the scheduled sweep retries; the write is committed
            logger.warning("memory_v2_inline_convergence_failed", exc_info=True)

    # -- records -------------------------------------------------------------

    def create_record(self, record: MemoryRecord) -> MemoryRecord:
        if not self.v2_authoritative():
            return self.legacy.create_record(record)
        stored = self.records.create(tenant_principal(), record)
        self._converge(stored)
        return stored

    def get_record(self, record_id: str) -> MemoryRecord | None:
        if not self.v2_authoritative():
            return self.legacy.get_record(record_id)
        return self.records.get(tenant_principal(), record_id)

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
        if not self.v2_authoritative():
            return self.legacy.list_records(
                owner_type=owner_type, owner_id=owner_id, scope=scope, scope_id=scope_id,
                status=status, limit=limit, offset=offset,
            )
        return self.records.list(
            tenant_principal(), owner_type=owner_type, owner_id=owner_id, scope=scope,
            scope_id=scope_id, status=status, limit=limit, offset=offset,
        )

    def update_record(self, record: MemoryRecord, *, expected_revision: int) -> MemoryRecord:
        if not self.v2_authoritative():
            return self.legacy.update_record(record, expected_revision=expected_revision)
        stored = self.records.update(tenant_principal(), record, expected_revision=expected_revision)
        self._converge(stored)
        return stored

    def forget_record(self, record_id: str, *, expected_revision: int) -> bool:
        if not self.v2_authoritative():
            return self.legacy.forget_record(record_id, expected_revision=expected_revision)
        principal = tenant_principal()
        record = self.records.get(principal, record_id)
        forgotten = self.records.forget(principal, record_id, expected_revision=expected_revision)
        if forgotten:
            # Snapshot items freeze the text; forgetting removes it there too.
            self.legacy.delete_snapshot_items_for_record(record_id)
            if record is not None:
                self._converge(record)
        return forgotten

    # -- candidates that become records --------------------------------------

    def accept_candidate(
        self,
        candidate_id: str,
        record: MemoryRecord,
        *,
        resolved_at: str,
    ) -> MemoryRecord:
        if not self.v2_authoritative():
            return self.legacy.accept_candidate(candidate_id, record, resolved_at=resolved_at)
        candidate = self.legacy.get_candidate(candidate_id)
        if candidate is None:
            raise MemoryNotFoundError(candidate_id)
        principal = tenant_principal()
        key = f"curated-memory:candidate:{candidate_id}"
        if candidate.status != "pending":
            existing = self.records.find_by_idempotency_key(
                memory_space(principal, record.owner_type, record.owner_id), key,
            )
            if candidate.status == "accepted" and existing is not None:
                return existing
            raise MemoryConflictError(f"candidate {candidate_id} is not pending: {candidate.status}")
        # The record first (idempotent per candidate), then the candidate: a
        # crash between them leaves a pending candidate whose retry returns
        # the same record.
        stored = self.records.create(principal, record, idempotency_key=key)
        try:
            self.legacy.mark_candidate_accepted(candidate_id, resolved_at=resolved_at)
        except (MemoryNotFoundError, MemoryConflictError):
            # Resolved concurrently; only an acceptance is consistent with the record.
            current = self.legacy.get_candidate(candidate_id)
            if current is None or current.status != "accepted":
                raise
        self._converge(stored)
        return stored

    # -- owner reset ---------------------------------------------------------

    def delete_owner(self, *, owner_type: str, owner_id: str) -> tuple[int, int, int]:
        if not self.v2_authoritative():
            return self.legacy.delete_owner(owner_type=owner_type, owner_id=owner_id)
        principal = tenant_principal()
        purged = self.records.purge_owner(principal, owner_type, owner_id)
        # Candidates, snapshots and the frozen pre-cutover v1 rows go too.
        _, candidates, snapshots = self.legacy.delete_owner(owner_type=owner_type, owner_id=owner_id)
        try:
            self.convergence.run(space=memory_space(principal, owner_type, owner_id), max_steps=10)
        except Exception:  # noqa: BLE001 - the scheduled sweep retries
            logger.warning("memory_v2_inline_convergence_failed", exc_info=True)
        return purged, candidates, snapshots


__all__ = ["MemoryAuthorityRoutedRepository"]
