"""Candidate persistence for PostgreSQL owner-aware memory."""
from __future__ import annotations

import json
from typing import Any

from app.assistant_memory.models import MemoryCandidate, MemoryRecord
from app.assistant_memory.repository import MemoryConflictError, MemoryNotFoundError

from .owner_memory_rows import OwnerMemoryRowSupport


class OwnerMemoryCandidateMixin(OwnerMemoryRowSupport):
    def create_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                INSERT INTO omnix_memory_candidates (
                    id, workspace_id, source_session_id, source_message_id,
                    candidate_fingerprint, proposed_owner_type, proposed_owner_id,
                    proposed_scope, proposed_scope_id, proposed_category,
                    proposed_content, confidence, source, trust_level, sensitivity,
                    extraction_metadata, status, created_at, resolved_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s::jsonb, %s, %s::timestamptz,
                    %s::timestamptz
                )
                RETURNING id, source_session_id, source_message_id,
                          candidate_fingerprint, proposed_owner_type,
                          proposed_owner_id, proposed_scope, proposed_scope_id,
                          proposed_category, proposed_content, confidence, source,
                          trust_level, sensitivity, extraction_metadata, status,
                          created_at, resolved_at
                """,
                (
                    candidate.id,
                    self.workspace_id,
                    candidate.source_session_id,
                    candidate.source_message_id,
                    candidate.candidate_fingerprint,
                    candidate.owner_type,
                    candidate.owner_id,
                    candidate.proposed_scope,
                    candidate.proposed_scope_id,
                    candidate.proposed_category,
                    candidate.proposed_content,
                    candidate.confidence,
                    candidate.source,
                    candidate.trust_level,
                    candidate.sensitivity,
                    json.dumps(candidate.extraction_metadata),
                    candidate.status,
                    candidate.created_at,
                    candidate.resolved_at,
                ),
            ).fetchone()
            self.append_event(
                connection,
                "candidate",
                candidate.id,
                "memory.candidate_created",
                {
                    "owner_type": candidate.owner_type,
                    "scope": candidate.proposed_scope,
                },
            )
        return self.candidate_from_row(row)

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        with self.database.connection() as connection:
            row = connection.execute(
                self.candidate_select()
                + " WHERE id = %s AND workspace_id = %s",
                (candidate_id, self.workspace_id),
            ).fetchone()
        return self.candidate_from_row(row) if row is not None else None

    def list_candidates(
        self,
        *,
        owner_type: str | None = None,
        owner_id: str | None = None,
        status: str = "pending",
        limit: int = 100,
    ) -> list[MemoryCandidate]:
        clauses = ["workspace_id = %s", "status = %s"]
        parameters: list[Any] = [self.workspace_id, status]
        if owner_type is not None:
            clauses.append("proposed_owner_type = %s")
            parameters.append(owner_type)
        if owner_id is not None:
            clauses.append("proposed_owner_id = %s")
            parameters.append(owner_id)
        parameters.append(max(0, min(int(limit), 500)))
        with self.database.connection() as connection:
            rows = connection.execute(
                self.candidate_select()
                + " WHERE "
                + " AND ".join(clauses)
                + " ORDER BY created_at ASC, id ASC LIMIT %s",
                tuple(parameters),
            ).fetchall()
        return [self.candidate_from_row(row) for row in rows]

    def reject_candidate(
        self,
        candidate_id: str,
        *,
        resolved_at: str,
    ) -> MemoryCandidate:
        return self._resolve_candidate(candidate_id, "rejected", resolved_at)

    def delete_candidate(
        self,
        candidate_id: str,
        *,
        expected_status: str | None = None,
    ) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM omnix_memory_candidates "
                "WHERE id = %s AND workspace_id = %s FOR UPDATE",
                (candidate_id, self.workspace_id),
            ).fetchone()
            if row is None:
                return False
            if expected_status is not None and str(row[0]) != expected_status:
                raise MemoryConflictError(
                    f"candidate {candidate_id} expected status {expected_status}"
                )
            connection.execute(
                "DELETE FROM omnix_memory_candidates "
                "WHERE id = %s AND workspace_id = %s",
                (candidate_id, self.workspace_id),
            )
        return True

    def accept_candidate(
        self,
        candidate_id: str,
        record: MemoryRecord,
        *,
        resolved_at: str,
    ) -> MemoryRecord:
        with self.database.transaction() as connection:
            candidate_row = connection.execute(
                self.candidate_select()
                + " WHERE id = %s AND workspace_id = %s FOR UPDATE",
                (candidate_id, self.workspace_id),
            ).fetchone()
            if candidate_row is None:
                raise MemoryNotFoundError(candidate_id)
            candidate = self.candidate_from_row(candidate_row)
            if candidate.status != "pending":
                raise MemoryConflictError(
                    f"candidate {candidate_id} is not pending: {candidate.status}"
                )
            connection.execute(
                """
                INSERT INTO omnix_memory_records (
                    id, workspace_id, owner_type, owner_id, scope, scope_id,
                    category, content, normalized_content, confidence, pinned,
                    trust_level, sensitivity, provenance_type, provenance_id,
                    source, status, revision, created_at, updated_at, expires_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s::timestamptz,
                    %s::timestamptz, %s::timestamptz
                )
                """,
                (
                    record.id,
                    self.workspace_id,
                    record.owner_type,
                    record.owner_id,
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
            connection.execute(
                "UPDATE omnix_memory_candidates "
                "SET status = 'accepted', resolved_at = %s::timestamptz "
                "WHERE id = %s AND workspace_id = %s",
                (resolved_at, candidate_id, self.workspace_id),
            )
            self.append_event(
                connection,
                "candidate",
                candidate_id,
                "memory.candidate_approved",
                {"memory_record_id": record.id},
            )
        return record

    def _resolve_candidate(
        self,
        candidate_id: str,
        status: str,
        resolved_at: str,
    ) -> MemoryCandidate:
        with self.database.transaction() as connection:
            row = connection.execute(
                "UPDATE omnix_memory_candidates SET status = %s, "
                "resolved_at = %s::timestamptz "
                "WHERE id = %s AND workspace_id = %s AND status = 'pending' "
                "RETURNING id, source_session_id, source_message_id, "
                "candidate_fingerprint, proposed_owner_type, proposed_owner_id, "
                "proposed_scope, proposed_scope_id, proposed_category, "
                "proposed_content, confidence, source, trust_level, sensitivity, "
                "extraction_metadata, status, created_at, resolved_at",
                (status, resolved_at, candidate_id, self.workspace_id),
            ).fetchone()
        if row is None:
            raise MemoryNotFoundError(candidate_id)
        return self.candidate_from_row(row)
