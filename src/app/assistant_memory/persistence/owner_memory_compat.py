"""PostgreSQL authority for owner-isolated assistant memory."""
from __future__ import annotations

from app.persistence.database import PostgresDatabase, default_database
from app.security.tenant_context import RequestTenant
from .owner_memory_candidates import OwnerMemoryCandidateMixin
from .owner_memory_records import OwnerMemoryRecordMixin
from .owner_memory_snapshots import OwnerMemorySnapshotMixin


class PostgresOwnerAwareMemoryRepository(
    OwnerMemoryRecordMixin,
    OwnerMemoryCandidateMixin,
    OwnerMemorySnapshotMixin,
):
    """Persist logical owner and memory scope as independent dimensions."""
    context = RequestTenant()

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        self.context = None  # follows the request tenant

    def delete_owner(
        self,
        *,
        owner_type: str,
        owner_id: str,
    ) -> tuple[int, int, int]:
        with self.database.transaction() as connection:
            snapshot_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM omnix_memory_snapshots "
                    "WHERE workspace_id = %s AND owner_type = %s AND owner_id = %s",
                    (self.workspace_id, owner_type, owner_id),
                ).fetchone()[0]
            )
            connection.execute(
                "UPDATE omnix_chat_sessions SET memory_snapshot_id = NULL "
                "WHERE workspace_id = %s AND memory_snapshot_id IN ("
                "SELECT id FROM omnix_memory_snapshots "
                "WHERE workspace_id = %s AND owner_type = %s AND owner_id = %s)",
                (self.workspace_id, self.workspace_id, owner_type, owner_id),
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
                    "snapshot_count": snapshot_count,
                },
            )
        return record_count, candidate_count, snapshot_count


__all__ = ["PostgresOwnerAwareMemoryRepository"]
