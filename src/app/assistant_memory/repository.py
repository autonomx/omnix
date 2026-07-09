"""Transactional SQLite repository for curated Chat memory."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.runtime_paths import resources_data_root

from .models import MemoryCandidate, MemoryRecord, MemorySnapshot, MemorySnapshotItem
from .schema import initialize_schema


class MemoryConflictError(RuntimeError):
    """Raised when an optimistic revision or pending-state check fails."""


class MemoryNotFoundError(KeyError):
    """Raised when a requested memory entity does not exist."""


def default_memory_db_path() -> Path:
    override = (os.environ.get("OMNIX_ASSISTANT_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override)
    return resources_data_root() / "omnix_assistant_memory.sqlite3"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None) -> dict[str, Any]:
    return json.loads(value) if value else {}


class SQLiteMemoryRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_memory_db_path()
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            initialize_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def create_record(self, record: MemoryRecord) -> MemoryRecord:
        with self._connect() as connection:
            self._insert_record(connection, record)
            self._append_event(connection, "record", record.id, "memory.created", {
                "scope": record.scope,
                "scope_id": record.scope_id,
                "revision": record.revision,
            })
        return record

    def get_record(self, record_id: str) -> MemoryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_records WHERE id = ?",
                (record_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def list_records(
        self,
        *,
        scope: str | None = None,
        scope_id: str | None = None,
        status: str | None = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope is not None:
            clauses.append("scope = ?")
            params.append(scope)
        if scope_id is not None:
            clauses.append("scope_id = ?")
            params.append(scope_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        query = (
            "SELECT * FROM memory_records"
            + where
            + " ORDER BY pinned DESC, updated_at DESC, id ASC LIMIT ? OFFSET ?"
        )
        params.extend([max(0, min(limit, 500)), max(0, offset)])
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update_record(self, record: MemoryRecord, *, expected_revision: int) -> MemoryRecord:
        updated = record.model_copy(update={"revision": expected_revision + 1})
        values = self._record_values(updated)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE memory_records SET
                    scope = ?, scope_id = ?, category = ?, source = ?, content = ?,
                    normalized_content = ?, confidence = ?, pinned = ?, trust_level = ?,
                    sensitivity = ?, provenance_type = ?, provenance_id = ?, status = ?,
                    revision = ?, created_at = ?, updated_at = ?, expires_at = ?
                WHERE id = ? AND revision = ?
                """,
                (*values[1:], updated.id, expected_revision),
            )
            if cursor.rowcount != 1:
                self._raise_revision_error(connection, updated.id, expected_revision)
            self._append_event(connection, "record", updated.id, "memory.updated", {
                "revision": updated.revision,
            })
        return updated

    def forget_record(self, record_id: str, *, expected_revision: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision FROM memory_records WHERE id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                return False
            if int(row["revision"]) != expected_revision:
                raise MemoryConflictError(
                    f"memory revision conflict for {record_id}: expected {expected_revision}"
                )
            connection.execute(
                "DELETE FROM memory_snapshot_items WHERE memory_record_id = ?",
                (record_id,),
            )
            connection.execute("DELETE FROM memory_records WHERE id = ?", (record_id,))
            self._append_event(connection, "record", record_id, "memory.forgotten", {
                "forgotten_revision": expected_revision,
            })
        return True

    def create_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO memory_candidates (
                    id, source_session_id, source_message_id, candidate_fingerprint,
                    proposed_scope, proposed_scope_id, proposed_category, proposed_content,
                    confidence, source, trust_level, sensitivity, extraction_metadata_json,
                    status, created_at, resolved_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    candidate.id,
                    candidate.source_session_id,
                    candidate.source_message_id,
                    candidate.candidate_fingerprint,
                    candidate.proposed_scope,
                    candidate.proposed_scope_id,
                    candidate.proposed_category,
                    candidate.proposed_content,
                    candidate.confidence,
                    candidate.source,
                    candidate.trust_level,
                    candidate.sensitivity,
                    _json_dumps(candidate.extraction_metadata),
                    candidate.status,
                    candidate.created_at,
                    candidate.resolved_at,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM memory_candidates
                WHERE source_message_id = ? AND candidate_fingerprint = ?
                """,
                (candidate.source_message_id, candidate.candidate_fingerprint),
            ).fetchone()
            stored = self._row_to_candidate(row)
            if stored.id == candidate.id:
                self._append_event(connection, "candidate", stored.id, "memory.candidate_created", {})
        return stored

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return self._row_to_candidate(row) if row else None

    def list_candidates(self, *, status: str = "pending", limit: int = 100) -> list[MemoryCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memory_candidates
                WHERE status = ? ORDER BY created_at ASC, id ASC LIMIT ?
                """,
                (status, max(0, min(limit, 500))),
            ).fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def reject_candidate(self, candidate_id: str, *, resolved_at: str) -> MemoryCandidate:
        return self._resolve_candidate(candidate_id, "rejected", resolved_at)

    def delete_candidate(self, candidate_id: str, *, expected_status: str | None = None) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM memory_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                return False
            if expected_status is not None and row["status"] != expected_status:
                raise MemoryConflictError(
                    f"candidate {candidate_id} is {row['status']}, expected {expected_status}"
                )
            connection.execute("DELETE FROM memory_candidates WHERE id = ?", (candidate_id,))
            self._append_event(connection, "candidate", candidate_id, "memory.candidate_deleted", {
                "deleted_status": row["status"],
            })
        return True

    def accept_candidate(
        self,
        candidate_id: str,
        record: MemoryRecord,
        *,
        resolved_at: str,
    ) -> MemoryRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM memory_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError(candidate_id)
            if row["status"] != "pending":
                raise MemoryConflictError(f"candidate {candidate_id} is already {row['status']}")
            self._insert_record(connection, record)
            connection.execute(
                "UPDATE memory_candidates SET status = 'accepted', resolved_at = ? WHERE id = ?",
                (resolved_at, candidate_id),
            )
            self._append_event(connection, "candidate", candidate_id, "memory.candidate_accepted", {
                "memory_record_id": record.id,
            })
            self._append_event(connection, "record", record.id, "memory.created", {
                "candidate_id": candidate_id,
                "revision": record.revision,
            })
        return record

    def create_snapshot(self, snapshot: MemorySnapshot) -> MemorySnapshot:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_snapshots(
                    id, session_id, revision, token_estimate, created_at, refreshed_at
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    snapshot.id,
                    snapshot.session_id,
                    snapshot.revision,
                    snapshot.token_estimate,
                    snapshot.created_at,
                    snapshot.refreshed_at,
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
                        snapshot.id,
                        position,
                        item.memory_record_id,
                        item.record_revision,
                        item.frozen_content,
                        item.revoked_at,
                    ),
                )
            self._append_event(connection, "snapshot", snapshot.id, "memory.snapshot_created", {
                "session_id": snapshot.session_id,
                "revision": snapshot.revision,
                "record_count": len(snapshot.items),
            })
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> MemorySnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_snapshots WHERE id = ?",
                (snapshot_id,),
            ).fetchone()
            if row is None:
                return None
            items = connection.execute(
                """
                SELECT * FROM memory_snapshot_items
                WHERE snapshot_id = ? ORDER BY position ASC
                """,
                (snapshot_id,),
            ).fetchall()
        return self._row_to_snapshot(row, items)

    def latest_snapshot(self, session_id: str) -> MemorySnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM memory_snapshots
                WHERE session_id = ? ORDER BY revision DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            items = connection.execute(
                """
                SELECT * FROM memory_snapshot_items
                WHERE snapshot_id = ? ORDER BY position ASC
                """,
                (row["id"],),
            ).fetchall()
        return self._row_to_snapshot(row, items)

    def list_events(self, *, entity_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM memory_events"
        params: tuple[Any, ...] = ()
        if entity_id is not None:
            query += " WHERE entity_id = ?"
            params = (entity_id,)
        query += " ORDER BY id ASC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "id": int(row["id"]),
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "event_type": row["event_type"],
                "metadata": _json_loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _resolve_candidate(self, candidate_id: str, status: str, resolved_at: str) -> MemoryCandidate:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE memory_candidates SET status = ?, resolved_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (status, resolved_at, candidate_id),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    "SELECT status FROM memory_candidates WHERE id = ?",
                    (candidate_id,),
                ).fetchone()
                if row is None:
                    raise MemoryNotFoundError(candidate_id)
                raise MemoryConflictError(f"candidate {candidate_id} is already {row['status']}")
            self._append_event(connection, "candidate", candidate_id, f"memory.candidate_{status}", {})
            row = connection.execute(
                "SELECT * FROM memory_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
        return self._row_to_candidate(row)

    def _insert_record(self, connection: sqlite3.Connection, record: MemoryRecord) -> None:
        connection.execute(
            """
            INSERT INTO memory_records (
                id, scope, scope_id, category, source, content, normalized_content,
                confidence, pinned, trust_level, sensitivity, provenance_type,
                provenance_id, status, revision, created_at, updated_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            self._record_values(record),
        )

    @staticmethod
    def _record_values(record: MemoryRecord) -> tuple[Any, ...]:
        return (
            record.id,
            record.scope,
            record.scope_id,
            record.category,
            record.source,
            record.content,
            record.normalized_content,
            record.confidence,
            int(record.pinned),
            record.trust_level,
            record.sensitivity,
            record.provenance_type,
            record.provenance_id,
            record.status,
            record.revision,
            record.created_at,
            record.updated_at,
            record.expires_at,
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        payload = dict(row)
        payload["pinned"] = bool(payload["pinned"])
        return MemoryRecord.model_validate(payload)

    @staticmethod
    def _row_to_candidate(row: sqlite3.Row) -> MemoryCandidate:
        payload = dict(row)
        payload["extraction_metadata"] = _json_loads(payload.pop("extraction_metadata_json"))
        return MemoryCandidate.model_validate(payload)

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row, items: list[sqlite3.Row]) -> MemorySnapshot:
        return MemorySnapshot(
            id=row["id"],
            session_id=row["session_id"],
            revision=int(row["revision"]),
            token_estimate=int(row["token_estimate"]),
            created_at=row["created_at"],
            refreshed_at=row["refreshed_at"],
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

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        entity_type: str,
        entity_id: str,
        event_type: str,
        metadata: dict[str, Any],
    ) -> None:
        from datetime import datetime, timezone

        connection.execute(
            """
            INSERT INTO memory_events(entity_type, entity_id, event_type, metadata_json, created_at)
            VALUES (?,?,?,?,?)
            """,
            (
                entity_type,
                entity_id,
                event_type,
                _json_dumps(metadata),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    @staticmethod
    def _raise_revision_error(
        connection: sqlite3.Connection,
        record_id: str,
        expected_revision: int,
    ) -> None:
        row = connection.execute(
            "SELECT revision FROM memory_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise MemoryNotFoundError(record_id)
        raise MemoryConflictError(
            f"memory revision conflict for {record_id}: expected {expected_revision}, actual {row['revision']}"
        )
