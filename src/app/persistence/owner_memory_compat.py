"""PostgreSQL authority for owner-isolated assistant memory."""
from __future__ import annotations

from .database import PostgresDatabase, default_database
from .identity_service import bootstrap_local_tenant
from .owner_memory_candidates import OwnerMemoryCandidateMixin
from .owner_memory_records import OwnerMemoryRecordMixin
from .owner_memory_snapshots import OwnerMemorySnapshotMixin
from .runtime import ensure_postgresql_runtime_ready


class PostgresOwnerAwareMemoryRepository(
    OwnerMemoryRecordMixin,
    OwnerMemoryCandidateMixin,
    OwnerMemorySnapshotMixin,
):
    """Persist logical owner and memory scope as independent dimensions."""

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        ensure_postgresql_runtime_ready(self.database)
        self.context = bootstrap_local_tenant(self.database)

    def delete_owner(
        self,
        *,
        owner_type: str,
        owner_id: str,
    ) -> tuple[int, int, int]:
        with self.database.transaction() as connection:
            snapshot_rows = connection.execute(
                "SELECT id FROM omnix_memory_snapshots "
                "WHERE workspace_id = %s AND owner_type = %s AND owner_id = %s",
                (self.workspace_id, owner_type, owner_id),
            ).fetchall()
            snapshot_ids = [str(row[0]) for row in snapshot_rows]
            if snapshot_ids:
                connection.execute(
                    "UPDATE omnix_chat_sessions SET memory_snapshot_id = NULL "
                    "WHERE workspace_id = %s AND memory_snapshot_id = ANY(%s)",
                    (self.workspace_id, snapshot_ids),
                )
            candidate_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_memory_candidates "
                    "WHERE workspace_id = %s AND proposed_owner_type = %s "
                    "AND proposed_owner_id = %s",
                    (self.workspace_id, owner_type, owner_id),
                ).fetchone()[0]
            )
            record_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_memory_records "
                    "WHERE workspace_id = %s AND owner_type = %s AND owner_id = %s",
                    (self.workspace_id, owner_type, owner_id),
                ).fetchone()[0]
            )
            connection.execute(
                "DELETE FROM omnix_memory_candidates "
                "WHERE workspace_id = %s AND proposed_owner_type = %s "
                "AND proposed_owner_id = %s",
                (self.workspace_id, owner_type, owner_id),
            )
            connection.execute(
                "DELETE FROM omnix_memory_snapshots "
                "WHERE workspace_id = %s AND owner_type = %s AND owner_id = %s",
                (self.workspace_id, owner_type, owner_id),
            )
            connection.execute(
                "DELETE FROM omnix_memory_records "
                "WHERE workspace_id = %s AND owner_type = %s AND owner_id = %s",
                (self.workspace_id, owner_type, owner_id),
            )
            self.append_event(
                connection,
                "owner",
                f"{owner_type}:{owner_id}",
                "memory.owner_reset",
                {
                    "record_count": record_count,
                    "candidate_count": candidate_count,
                    "snapshot_count": len(snapshot_ids),
                },
            )
        return record_count, candidate_count, len(snapshot_ids)


__all__ = ["PostgresOwnerAwareMemoryRepository"]
