"""Record persistence for PostgreSQL owner-aware memory."""
from __future__ import annotations

from typing import Any

from app.assistant_memory.models import MemoryRecord
from app.assistant_memory.repository import MemoryConflictError, MemoryNotFoundError

from .owner_memory_rows import OwnerMemoryRowSupport


class OwnerMemoryRecordMixin(OwnerMemoryRowSupport):
    def create_record(self, record: MemoryRecord) -> MemoryRecord:
        with self.database.transaction() as connection:
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
            self.append_event(
                connection,
                "record",
                record.id,
                "memory.created",
                {
                    "owner_type": record.owner_type,
                    "scope": record.scope,
                    "revision": record.revision,
                },
            )
        return record

    def get_record(self, record_id: str) -> MemoryRecord | None:
        with self.database.connection() as connection:
            row = connection.execute(
                self.record_select() + " WHERE id = %s AND workspace_id = %s",
                (record_id, self.workspace_id),
            ).fetchone()
        return self.record_from_row(row) if row is not None else None

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
        clauses = ["workspace_id = %s"]
        parameters: list[Any] = [self.workspace_id]
        for column, value in (
            ("owner_type", owner_type),
            ("owner_id", owner_id),
            ("scope", scope),
            ("scope_id", scope_id),
            ("status", status),
        ):
            if value is not None:
                clauses.append(f"{column} = %s")
                parameters.append(value)
        parameters.extend([max(0, min(int(limit), 500)), max(0, int(offset))])
        with self.database.connection() as connection:
            rows = connection.execute(
                self.record_select()
                + " WHERE "
                + " AND ".join(clauses)
                + " ORDER BY pinned DESC, updated_at DESC, id ASC "
                + "LIMIT %s OFFSET %s",
                tuple(parameters),
            ).fetchall()
        return [self.record_from_row(row) for row in rows]

    def update_record(
        self,
        record: MemoryRecord,
        *,
        expected_revision: int,
    ) -> MemoryRecord:
        with self.database.transaction() as connection:
            current = connection.execute(
                "SELECT revision FROM omnix_memory_records "
                "WHERE id = %s AND workspace_id = %s FOR UPDATE",
                (record.id, self.workspace_id),
            ).fetchone()
            if current is None:
                raise MemoryNotFoundError(record.id)
            actual_revision = int(current[0])
            if actual_revision != expected_revision:
                raise MemoryConflictError(
                    f"memory revision conflict for {record.id}: "
                    f"expected {expected_revision}, actual {actual_revision}"
                )
            next_revision = expected_revision + 1
            row = connection.execute(
                """
                UPDATE omnix_memory_records
                   SET owner_type = %s, owner_id = %s, scope = %s, scope_id = %s,
                       category = %s, content = %s, normalized_content = %s,
                       confidence = %s, pinned = %s, trust_level = %s,
                       sensitivity = %s, provenance_type = %s, provenance_id = %s,
                       source = %s, status = %s, revision = %s,
                       updated_at = %s::timestamptz, expires_at = %s::timestamptz
                 WHERE id = %s AND workspace_id = %s
                 RETURNING id, workspace_id, owner_type, owner_id, scope, scope_id,
                           category, content, normalized_content, confidence, pinned,
                           trust_level, sensitivity, provenance_type, provenance_id,
                           source, status, revision, created_at, updated_at, expires_at
                """,
                (
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
                    next_revision,
                    record.updated_at,
                    record.expires_at,
                    record.id,
                    self.workspace_id,
                ),
            ).fetchone()
            self.append_event(
                connection,
                "record",
                record.id,
                "memory.updated",
                {"revision": next_revision},
            )
        if row is None:
            raise MemoryNotFoundError(record.id)
        return self.record_from_row(row)

    def forget_record(self, record_id: str, *, expected_revision: int) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT revision FROM omnix_memory_records "
                "WHERE id = %s AND workspace_id = %s FOR UPDATE",
                (record_id, self.workspace_id),
            ).fetchone()
            if row is None:
                return False
            actual_revision = int(row[0])
            if actual_revision != expected_revision:
                raise MemoryConflictError(
                    f"memory revision conflict for {record_id}: "
                    f"expected {expected_revision}, actual {actual_revision}"
                )
            connection.execute(
                "DELETE FROM omnix_memory_snapshot_items "
                "WHERE memory_record_id = %s",
                (record_id,),
            )
            connection.execute(
                "DELETE FROM omnix_memory_records "
                "WHERE id = %s AND workspace_id = %s",
                (record_id, self.workspace_id),
            )
            self.append_event(
                connection,
                "record",
                record_id,
                "memory.forgotten",
                {"forgotten_revision": expected_revision},
            )
        return True
