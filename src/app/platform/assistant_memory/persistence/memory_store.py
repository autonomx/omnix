from __future__ import annotations

import json
from typing import Any, cast

from app.conversation.memory_contracts import (
    MemoryCandidate,
    MemoryRecord,
    MemorySnapshot,
)
from app.platform.assistant_memory.repository import MemoryConflictError, MemoryNotFoundError

from app.persistence.database import PostgresDatabase, default_database
from app.persistence.errors import EntityNotFound, RevisionConflict
from app.security.tenant_context import RequestTenant
from app.persistence.unit_of_work import unit_of_work
from app.persistence.repository_registry import install_repository_specs
from app.runtime.pagination import bounded_count
from app.platform.assistant_memory.persistence.repository_specs import (
    ASSISTANT_MEMORY_REPOSITORY_SPECS,
)
from app.platform.assistant_memory.persistence.owner_memory_rows import OwnerMemoryRowSupport


class PostgresMemoryRepositoryAdapter:
    context = RequestTenant()
    def __init__(self, database: PostgresDatabase | None = None) -> None:
        install_repository_specs(ASSISTANT_MEMORY_REPOSITORY_SPECS)
        self.database = database or default_database()
        self.context = None  # follows the request tenant

    def create_record(self, record: MemoryRecord) -> MemoryRecord:
        with unit_of_work(self.database) as work:
            stored = work.memories.create(self.context, self._record_payload(record))
            work.commit()
        return self._record(stored)

    def get_record(self, record_id: str) -> MemoryRecord | None:
        with unit_of_work(self.database) as work:
            record = work.memories.get_memory(self.context, record_id)
            work.rollback()
        return self._record(record) if record is not None else None

    def list_records(
        self,
        *,
        scope: str | None = None,
        scope_id: str | None = None,
        status: str | None = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        if scope is not None and scope_id is not None and status is None:
            status = "active"
        # One SQL path for every filter, paged by LIMIT/OFFSET (WP-5.5).
        with self.database.connection() as connection:
            clauses = ["workspace_id = %s"]
            parameters: list[Any] = [self.context.workspace_id]
            if scope is not None:
                clauses.append("owner_type = %s")
                parameters.append(scope)
            if scope_id is not None:
                clauses.append("owner_id = %s")
                parameters.append(scope_id)
            if status is not None:
                clauses.append("status = %s")
                parameters.append(status)
            parameters.extend([bounded_count(limit), max(0, int(offset))])
            rows = connection.execute(
                """
                SELECT id, workspace_id, owner_type, owner_id, category, content,
                       normalized_content, confidence, pinned, trust_level,
                       sensitivity, provenance_type, provenance_id, source,
                       status, revision, created_at, updated_at, expires_at
                  FROM omnix_memory_records WHERE
                """
                + " AND ".join(clauses)
                + " ORDER BY pinned DESC, updated_at DESC, id ASC LIMIT %s OFFSET %s",
                tuple(parameters),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def update_record(self, record: MemoryRecord, *, expected_revision: int) -> MemoryRecord:
        try:
            with unit_of_work(self.database) as work:
                stored = work.memories.update(
                    self.context,
                    memory_id=record.id,
                    expected_revision=expected_revision,
                    changes=self._record_payload(record),
                )
                work.commit()
        except EntityNotFound as exc:
            raise MemoryNotFoundError(record.id) from exc
        except RevisionConflict as exc:
            raise MemoryConflictError(str(exc)) from exc
        return self._record(stored)

    def forget_record(self, record_id: str, *, expected_revision: int) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT revision FROM omnix_memory_records "
                "WHERE id = %s AND workspace_id = %s FOR UPDATE",
                (record_id, self.context.workspace_id),
            ).fetchone()
            if row is None:
                return False
            if int(row[0]) != expected_revision:
                raise MemoryConflictError(
                    f"memory revision conflict for {record_id}: expected {expected_revision}"
                )
            connection.execute(
                "DELETE FROM omnix_memory_snapshot_items WHERE memory_record_id = %s",
                (record_id,),
            )
            connection.execute(
                "DELETE FROM omnix_memory_records WHERE id = %s AND workspace_id = %s",
                (record_id, self.context.workspace_id),
            )
            connection.execute(
                """
                INSERT INTO omnix_memory_events
                    (workspace_id, entity_type, entity_id, event_type, payload)
                VALUES (%s, 'record', %s, 'memory.forgotten', %s::jsonb)
                """,
                (
                    self.context.workspace_id,
                    record_id,
                    json.dumps({"forgotten_revision": expected_revision}),
                ),
            )
        return True

    def create_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate:
        with unit_of_work(self.database) as work:
            stored = work.memories.create_candidate(
                self.context,
                {
                    "id": candidate.id,
                    "source_session_id": candidate.source_session_id,
                    "source_message_id": candidate.source_message_id,
                    "candidate_fingerprint": candidate.candidate_fingerprint,
                    "proposed_owner_type": candidate.proposed_scope,
                    "proposed_owner_id": candidate.proposed_scope_id,
                    "proposed_category": candidate.proposed_category,
                    "proposed_content": candidate.proposed_content,
                    "confidence": candidate.confidence,
                    "source": candidate.source,
                    "trust_level": candidate.trust_level,
                    "sensitivity": candidate.sensitivity,
                    "extraction_metadata": dict(candidate.extraction_metadata),
                },
            )
            work.commit()
        return self._candidate(stored)

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        with self.database.connection() as connection:
            row = connection.execute(
                self._candidate_select() + " WHERE id = %s AND workspace_id = %s",
                (candidate_id, self.context.workspace_id),
            ).fetchone()
        return self._candidate_from_row(row) if row is not None else None

    def list_candidates(self, *, status: str = "pending", limit: int = 100, offset: int = 0) -> list[MemoryCandidate]:
        with self.database.connection() as connection:
            rows = connection.execute(
                self._candidate_select()
                + " WHERE workspace_id = %s AND status = %s "
                "ORDER BY created_at ASC, id ASC LIMIT %s OFFSET %s",
                (self.context.workspace_id, status, bounded_count(limit), max(0, int(offset))),
            ).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def reject_candidate(self, candidate_id: str, *, resolved_at: str) -> MemoryCandidate:
        return self._resolve_candidate(candidate_id, "rejected", resolved_at)

    def delete_candidate(self, candidate_id: str, *, expected_status: str | None = None) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM omnix_memory_candidates "
                "WHERE id = %s AND workspace_id = %s FOR UPDATE",
                (candidate_id, self.context.workspace_id),
            ).fetchone()
            if row is None:
                return False
            if expected_status is not None and str(row[0]) != expected_status:
                raise MemoryConflictError(
                    f"candidate {candidate_id} expected status {expected_status}"
                )
            connection.execute(
                "DELETE FROM omnix_memory_candidates WHERE id = %s AND workspace_id = %s",
                (candidate_id, self.context.workspace_id),
            )
        return True

    def accept_candidate(self, candidate_id: str, record: MemoryRecord, *, resolved_at: str) -> MemoryRecord:
        """The memory service's name for approving: the stored record."""
        return self.approve_candidate(candidate_id, record, resolved_at=resolved_at)[1]

    def approve_candidate(
        self,
        candidate_id: str,
        record: MemoryRecord,
        *,
        resolved_at: str,
    ) -> tuple[MemoryCandidate, MemoryRecord]:
        with self.database.transaction() as connection:
            row = connection.execute(
                self._candidate_select()
                + " WHERE id = %s AND workspace_id = %s FOR UPDATE",
                (candidate_id, self.context.workspace_id),
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError(candidate_id)
            candidate = self._candidate_from_row(row)
            if candidate.status != "pending":
                raise MemoryConflictError(
                    f"candidate {candidate_id} is not pending: {candidate.status}"
                )
            connection.execute(
                """
                INSERT INTO omnix_memory_records (
                    id, workspace_id, owner_type, owner_id, category, content,
                    normalized_content, confidence, pinned, trust_level,
                    sensitivity, provenance_type, provenance_id, source, status,
                    revision, created_at, updated_at, expires_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s::timestamptz,
                    %s::timestamptz, %s::timestamptz
                )
                """,
                (
                    record.id,
                    self.context.workspace_id,
                    record.scope,
                    record.scope_id,
                    record.category,
                    record.content,
                    record.normalized_content,
                    record.confidence,
                    record.pinned,
                    record.trust_level,
                    record.sensitivity,
                    record.provenance_type,
                    record.provenance_id,
                    record.source,
                    record.status,
                    record.revision,
                    record.created_at,
                    record.updated_at,
                    record.expires_at,
                ),
            )
            resolved = connection.execute(
                self._resolve_candidate_sql(),
                ("approved", resolved_at, candidate_id, self.context.workspace_id),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO omnix_memory_events
                    (workspace_id, entity_type, entity_id, event_type, payload)
                VALUES (%s, 'candidate', %s, 'memory.candidate_approved', %s::jsonb)
                """,
                (
                    self.context.workspace_id,
                    candidate_id,
                    json.dumps({"memory_record_id": record.id}),
                ),
            )
        return self._candidate_from_row(resolved), record

    # Snapshot rows follow today's schema (migration 0010: session, token
    # estimate, frozen item text), read and built the same way as the
    # owner-aware store's (OwnerMemoryRowSupport).
    def create_snapshot(self, snapshot: MemorySnapshot) -> MemorySnapshot:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO omnix_memory_snapshots (
                    id, workspace_id, owner_type, owner_id, revision, status,
                    created_at, session_id, token_estimate, refreshed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, 'active', %s::timestamptz, %s, %s, %s::timestamptz
                )
                """,
                (
                    snapshot.id,
                    self.context.workspace_id,
                    snapshot.owner_type,
                    snapshot.owner_id,
                    snapshot.revision,
                    snapshot.created_at,
                    snapshot.session_id,
                    snapshot.token_estimate,
                    snapshot.refreshed_at,
                ),
            )
            for position, item in enumerate(snapshot.items):
                connection.execute(
                    """
                    INSERT INTO omnix_memory_snapshot_items (
                        snapshot_id, memory_record_id, position, record_revision, frozen_content, revoked_at
                    ) VALUES (%s, %s, %s, %s, %s, %s::timestamptz)
                    """,
                    (snapshot.id, item.memory_record_id, position, item.record_revision,
                     item.frozen_content, item.revoked_at),
                )
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> MemorySnapshot | None:
        with self.database.connection() as connection:
            row = connection.execute(
                OwnerMemoryRowSupport.snapshot_select() + " WHERE id = %s AND workspace_id = %s",
                (snapshot_id, self.context.workspace_id),
            ).fetchone()
            if row is None:
                return None
            items = OwnerMemoryRowSupport.snapshot_items(connection, str(row[0]))
        return OwnerMemoryRowSupport.snapshot_from_row(row, items)

    def latest_snapshot(self, session_id: str) -> MemorySnapshot | None:
        with self.database.connection() as connection:
            row = connection.execute(
                OwnerMemoryRowSupport.snapshot_select()
                + " WHERE workspace_id = %s AND session_id = %s AND status = 'active'"
                + " ORDER BY revision DESC, created_at DESC, id DESC LIMIT 1",
                (self.context.workspace_id, session_id),
            ).fetchone()
            if row is None:
                return None
            items = OwnerMemoryRowSupport.snapshot_items(connection, str(row[0]))
        return OwnerMemoryRowSupport.snapshot_from_row(row, items)

    def list_snapshots(
        self,
        *,
        scope: str | None = None,
        scope_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[MemorySnapshot]:
        """``scope``/``scope_id`` select the owner (type and id), as they always have here."""
        clauses = ["workspace_id = %s"]
        parameters: list[Any] = [self.context.workspace_id]
        for column, value in (("owner_type", scope), ("owner_id", scope_id), ("status", status)):
            if value is not None:
                clauses.append(f"{column} = %s")
                parameters.append(value)
        parameters.append(bounded_count(limit))
        with self.database.connection() as connection:
            rows = connection.execute(
                OwnerMemoryRowSupport.snapshot_select()
                + " WHERE " + " AND ".join(clauses)
                + " ORDER BY created_at DESC, id DESC LIMIT %s",
                tuple(parameters),
            ).fetchall()
            return [
                OwnerMemoryRowSupport.snapshot_from_row(row, OwnerMemoryRowSupport.snapshot_items(connection, str(row[0])))
                for row in rows
            ]

    def set_snapshot_status(self, snapshot_id: str, status: str) -> MemorySnapshot:
        with self.database.transaction() as connection:
            updated = connection.execute(
                "UPDATE omnix_memory_snapshots SET status = %s WHERE id = %s AND workspace_id = %s RETURNING id",
                (status, snapshot_id, self.context.workspace_id),
            ).fetchone()
            if updated is None:
                raise MemoryNotFoundError(snapshot_id)
            row = connection.execute(
                OwnerMemoryRowSupport.snapshot_select() + " WHERE id = %s AND workspace_id = %s",
                (snapshot_id, self.context.workspace_id),
            ).fetchone()
            items = OwnerMemoryRowSupport.snapshot_items(connection, snapshot_id)
        return OwnerMemoryRowSupport.snapshot_from_row(row, items)


    def _resolve_candidate(self, candidate_id: str, status: str, resolved_at: str) -> MemoryCandidate:
        with self.database.transaction() as connection:
            row = connection.execute(
                self._resolve_candidate_sql(),
                (status, resolved_at, candidate_id, self.context.workspace_id),
            ).fetchone()
        if row is None:
            raise MemoryNotFoundError(candidate_id)
        return self._candidate_from_row(row)

    @staticmethod
    def _resolve_candidate_sql() -> str:
        return (
            "UPDATE omnix_memory_candidates SET status = %s, "
            "resolved_at = %s::timestamptz WHERE id = %s AND workspace_id = %s "
            "AND status = 'pending' RETURNING id, source_session_id, "
            "source_message_id, candidate_fingerprint, proposed_owner_type, "
            "proposed_owner_id, proposed_category, proposed_content, confidence, "
            "source, trust_level, sensitivity, extraction_metadata, status, "
            "created_at, resolved_at"
        )

    @staticmethod
    def _candidate_select() -> str:
        return (
            "SELECT id, source_session_id, source_message_id, candidate_fingerprint, "
            "proposed_owner_type, proposed_owner_id, proposed_category, "
            "proposed_content, confidence, source, trust_level, sensitivity, "
            "extraction_metadata, status, created_at, resolved_at "
            "FROM omnix_memory_candidates"
        )

    @staticmethod
    def _record_payload(record: MemoryRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "owner_type": record.scope,
            "owner_id": record.scope_id,
            "category": record.category,
            "content": record.content,
            "normalized_content": record.normalized_content,
            "confidence": record.confidence,
            "pinned": record.pinned,
            "trust_level": record.trust_level,
            "sensitivity": record.sensitivity,
            "provenance_type": record.provenance_type,
            "provenance_id": record.provenance_id,
            "source": record.source,
            "status": record.status,
            "expires_at": record.expires_at,
        }

    @staticmethod
    def _record(value: dict[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            id=value["id"],
            scope=value["owner_type"],
            scope_id=value["owner_id"],
            category=value["category"],
            source=value["source"],
            content=value["content"],
            normalized_content=value["normalized_content"],
            confidence=value["confidence"],
            pinned=value["pinned"],
            trust_level=value["trust_level"],
            sensitivity=value["sensitivity"],
            provenance_type=cast(Any, value.get("provenance_type")),
            provenance_id=value.get("provenance_id"),
            status=value["status"],
            revision=value["revision"],
            created_at=value["created_at"],
            updated_at=value["updated_at"],
            expires_at=value.get("expires_at"),
        )

    @classmethod
    def _record_from_row(cls, row: Any) -> MemoryRecord:
        return cls._record(
            {
                "id": str(row[0]),
                "workspace_id": str(row[1]),
                "owner_type": str(row[2]),
                "owner_id": str(row[3]),
                "category": str(row[4]),
                "content": str(row[5]),
                "normalized_content": str(row[6]),
                "confidence": float(row[7]),
                "pinned": bool(row[8]),
                "trust_level": str(row[9]),
                "sensitivity": str(row[10]),
                "provenance_type": str(row[11]) if row[11] is not None else None,
                "provenance_id": str(row[12]) if row[12] is not None else None,
                "source": str(row[13]),
                "status": str(row[14]),
                "revision": int(row[15]),
                "created_at": row[16].isoformat(),
                "updated_at": row[17].isoformat(),
                "expires_at": row[18].isoformat() if row[18] is not None else None,
            }
        )

    @staticmethod
    def _candidate(value: dict[str, Any]) -> MemoryCandidate:
        return MemoryCandidate(
            id=value["id"],
            source_session_id=cast(str, value.get("source_session_id")),
            source_message_id=value["source_message_id"],
            candidate_fingerprint=value["candidate_fingerprint"],
            proposed_scope=value["proposed_owner_type"],
            proposed_scope_id=value["proposed_owner_id"],
            proposed_category=value["proposed_category"],
            proposed_content=value["proposed_content"],
            confidence=value["confidence"],
            source=value["source"],
            trust_level=value["trust_level"],
            sensitivity=value["sensitivity"],
            extraction_metadata=dict(value.get("extraction_metadata") or {}),
            status=value["status"],
            created_at=value["created_at"],
            resolved_at=value.get("resolved_at"),
        )

    @classmethod
    def _candidate_from_row(cls, row: Any) -> MemoryCandidate:
        return cls._candidate(
            {
                "id": str(row[0]),
                "source_session_id": str(row[1]) if row[1] is not None else None,
                "source_message_id": str(row[2]),
                "candidate_fingerprint": str(row[3]),
                "proposed_owner_type": str(row[4]),
                "proposed_owner_id": str(row[5]),
                "proposed_category": str(row[6]),
                "proposed_content": str(row[7]),
                "confidence": float(row[8]),
                "source": str(row[9]),
                "trust_level": str(row[10]),
                "sensitivity": str(row[11]),
                "extraction_metadata": dict(row[12]),
                "status": str(row[13]),
                "created_at": row[14].isoformat(),
                "resolved_at": row[15].isoformat() if row[15] is not None else None,
            }
        )



def production_memory_repository() -> PostgresMemoryRepositoryAdapter:
    from app.persistence.repository_registry import register_feature_repositories

    register_feature_repositories("assistant-memory")
    return PostgresMemoryRepositoryAdapter()
