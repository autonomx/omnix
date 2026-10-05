"""What the kernel reads about the RPG module without loading it (ADR-0016, PA-2.2): kernel imports only."""
from __future__ import annotations

from typing import Any

from app.persistence.declarations import CapacityCount, RetentionDeclaration


def _delete_narration_events(connection: Any, retention_days: int, batch_size: int) -> int:
    return int(connection.execute(
        """
        DELETE FROM omnix_rpg_narration_events
         WHERE event_id IN (
             SELECT event_id
               FROM omnix_rpg_narration_events
              WHERE created_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
              ORDER BY created_at, event_id
              LIMIT %s
         )
        """,
        (max(1, int(retention_days)), max(1, int(batch_size))),
    ).rowcount)


def _count(table: str) -> Any:
    def count(connection: Any) -> int:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    return count


RETENTION = (
    RetentionDeclaration("rpg_narration_events", delete=_delete_narration_events, capacity_cleanup=True),
)
CAPACITY = (
    CapacityCount("rpg_turns", count=_count("omnix_rpg_turns")),
    CapacityCount("rpg_narration_events", count=_count("omnix_rpg_narration_events")),
)
