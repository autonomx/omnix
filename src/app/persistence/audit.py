"""Kernel-owned durable audit event repository."""
from __future__ import annotations

import json
from typing import Any

from .tenant import TenantContext


class PostgresAuditRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def append(
        self,
        context: TenantContext,
        *,
        aggregate_type: str,
        aggregate_id: str,
        action: str,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> int:
        row = self.connection.execute(
            """INSERT INTO omnix_audit_events
                   (workspace_id, actor_user_id, aggregate_type, aggregate_id,
                    action, trace_id, payload)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
               RETURNING id""",
            (context.workspace_id, context.user_id, aggregate_type, aggregate_id,
             action, trace_id,
             json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))),
        ).fetchone()
        return int(row[0])

    def count_events(self) -> int:
        return int(self.connection.execute(
            "SELECT count(*) FROM omnix_audit_events"
        ).fetchone()[0])
