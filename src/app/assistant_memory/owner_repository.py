"""Owner-aware extension of the canonical SQLite memory repository."""
from __future__ import annotations

import sqlite3
from typing import Any

from .models import MemoryCandidate, MemoryRecord, MemorySnapshot, MemorySnapshotItem
from .repository import SQLiteMemoryRepository, _json_dumps, _json_loads


class OwnerAwareSQLiteMemoryRepository(SQLiteMemoryRepository):
    def list_records(
        self,
        *,
        owner_type: str = "system",
        owner_id: str = "system-assistant",
        scope: str | None = None,
        scope_id: str | None = None,
        status: str | None = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        clauses = ["owner_type = ?", "owner_id = ?"]
        params: list[Any] = [owner_type, owner_id]
        if scope is not None:
            clauses.append("scope = ?")
            params.append(scope)
        if scope_id is not None:
            clauses.append("scope_id = ?")
            params.append(scope_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        query = (
            "SELECT * FROM memory_records WHERE "
            + " AND ".join(clauses)
            + " ORDER BY pinned DESC, updated_at DESC, id ASC LIMIT ? OFFSET ?"
        )
        params.extend([max(0, min(limit, 500)), max(0, offset)])
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def create_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO memory_candidates (
                    id, owner_type, owner_id, source_session_id, source_message_id,
                    candidate_fingerprint, proposed_scope, proposed_scope_id,
                    proposed_category, proposed_content, confidence, source, trust_level,
                    sensitivity, extraction_metadata_json, status, created_at, resolved_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    candidate.id, candidate.owner_type, candidate.owner_id,
                    candidate.source_session_id, candidate.source_message_id,
                    candidate.candidate_fingerprint, candidate.proposed_scope,
                    candidate.proposed_scope_id, candidate.proposed_category,
                    candidate.proposed_content, candidate.confidence, candidate.source,
                    candidate.trust_level, candidate.sensitivity,
                    _json_dumps(candidate.extraction_metadata), candidate.status,
                    candidate.created_at, candidate.resolved_at,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM memory_candidates
                WHERE owner_type = ? AND owner_id = ?
                  AND source_message_id = ? AND candidate_fingerprint = ?
                """,
                (
                    candidate.owner_type, candidate.owner_id,
                    candidate.source_message_id, candidate.candidate_fingerprint,
                ),
            ).fetchone()
            stored = self._row_to_candidate(row)
            if stored.id == candidate.id:
                self._append_event(connection, "candidate", stored.id, "memory.candidate_created", {
                    "owner_type": stored.owner_type,
                    "owner_id": stored.owner_id,
                })
        return stored

    def list_candidates(
        self,
        *,
        owner_type: str = "system",
        owner_id: str = "system-assistant",
        status: str = "pending",
        limit: int = 100,
    ) -> list[MemoryCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memory_candidates
                WHERE owner_type = ? AND owner_id = ? AND status = ?
                ORDER BY created_at ASC, id ASC LIMIT ?
                """,
                (owner_type, owner_id, status, max(0, min(limit, 500))),
            ).fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def create_snapshot(self, snapshot: MemorySnapshot) -> MemorySnapshot:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_snapshots(
                    id, session_id, owner_type, owner_id, revision,
                    token_estimate, created_at, refreshed_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    snapshot.id, snapshot.session_id, snapshot.owner_type,
                    snapshot.owner_id, snapshot.revision, snapshot.token_estimate,
                    snapshot.created_at, snapshot.refreshed_at,
                ),
            )
            for position, item in enumerate(snapshot.items):
                connection.execute(
                    """
                    INSERT INTO memory_snapshot_items(
                        snapshot_id, position, memory_record_id, record_revision,
                        frozen_content, revoked_at
                    ) VALUES (?,?,?,?,?,?)
                    """,
                    (
                        snapshot.id, position, item.memory_record_id,
                        item.record_revision, item.frozen_content, item.revoked_at,
                    ),
                )
            self._append_event(connection, "snapshot", snapshot.id, "memory.snapshot_created", {
                "session_id": snapshot.session_id,
                "owner_type": snapshot.owner_type,
                "owner_id": snapshot.owner_id,
                "revision": snapshot.revision,
                "record_count": len(snapshot.items),
            })
        return snapshot

    def latest_snapshot(
        self,
        session_id: str,
        *,
        owner_type: str = "system",
        owner_id: str = "system-assistant",
    ) -> MemorySnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM memory_snapshots
                WHERE session_id = ? AND owner_type = ? AND owner_id = ?
                ORDER BY revision DESC LIMIT 1
                """,
                (session_id, owner_type, owner_id),
            ).fetchone()
            if row is None:
                return None
            items = connection.execute(
                "SELECT * FROM memory_snapshot_items WHERE snapshot_id = ? ORDER BY position ASC",
                (row["id"],),
            ).fetchall()
        return self._row_to_snapshot(row, items)

    def _insert_record(self, connection: sqlite3.Connection, record: MemoryRecord) -> None:
        connection.execute(
            """
            INSERT INTO memory_records (
                id, owner_type, owner_id, scope, scope_id, category, source,
                content, normalized_content, confidence, pinned, trust_level,
                sensitivity, provenance_type, provenance_id, status, revision,
                created_at, updated_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record.id, record.owner_type, record.owner_id, record.scope,
                record.scope_id, record.category, record.source, record.content,
                record.normalized_content, record.confidence, int(record.pinned),
                record.trust_level, record.sensitivity, record.provenance_type,
                record.provenance_id, record.status, record.revision,
                record.created_at, record.updated_at, record.expires_at,
            ),
        )

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row, items: list[sqlite3.Row]) -> MemorySnapshot:
        return MemorySnapshot(
            id=row["id"], session_id=row["session_id"],
            owner_type=row["owner_type"], owner_id=row["owner_id"],
            revision=int(row["revision"]), token_estimate=int(row["token_estimate"]),
            created_at=row["created_at"], refreshed_at=row["refreshed_at"],
            items=[
                MemorySnapshotItem(
                    memory_record_id=item["memory_record_id"],
                    record_revision=int(item["record_revision"]),
                    frozen_content=item["frozen_content"],
                    revoked_at=item["revoked_at"],
                )
                for item in items
            ],
        )


__all__ = ["OwnerAwareSQLiteMemoryRepository"]
