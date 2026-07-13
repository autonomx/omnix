"""Tenant-scoped PostgreSQL document records for compatibility surfaces."""

from __future__ import annotations

import json
from typing import Any

from .database import PostgresDatabase, default_database
from .identity_service import bootstrap_local_tenant
from .runtime import ensure_postgresql_runtime_ready


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class PostgresDocumentStore:
    """Small-document facade over ``omnix_module_records``.

    This is for existing feature contracts whose behavior is already expressed
    as read/modify/write over a bounded JSON document. New high-volume or
    independently queried domains should receive dedicated relational tables.
    """

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        ensure_postgresql_runtime_ready(self.database)
        self.context = bootstrap_local_tenant(self.database)

    def read(
        self,
        *,
        module: str,
        record_type: str,
        record_id: str = "default",
        default: Any = None,
    ) -> Any:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT payload FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s AND status = 'active'
                """,
                (self.context.workspace_id, module, record_type, record_id),
            ).fetchone()
        if row is None:
            return default
        value = row[0]
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return list(value)
        return value

    def write(
        self,
        payload: Any,
        *,
        module: str,
        record_type: str,
        record_id: str = "default",
        status: str = "active",
        expires_at: str | None = None,
    ) -> int:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                INSERT INTO omnix_module_records (
                    workspace_id, module, record_type, record_id, owner_user_id,
                    payload, status, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::timestamptz)
                ON CONFLICT (workspace_id, module, record_type, record_id)
                DO UPDATE SET payload = EXCLUDED.payload,
                              status = EXCLUDED.status,
                              expires_at = EXCLUDED.expires_at,
                              revision = omnix_module_records.revision + 1,
                              updated_at = CURRENT_TIMESTAMP
                RETURNING revision
                """,
                (
                    self.context.workspace_id,
                    module,
                    record_type,
                    record_id,
                    self.context.user_id,
                    _json(payload),
                    status,
                    expires_at,
                ),
            ).fetchone()
        return int(row[0])

    def list(
        self,
        *,
        module: str,
        record_type: str,
        limit: int = 500,
    ) -> list[tuple[str, Any, int]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT record_id, payload, revision
                  FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND status = 'active'
                   AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                 ORDER BY updated_at DESC, record_id ASC LIMIT %s
                """,
                (
                    self.context.workspace_id,
                    module,
                    record_type,
                    max(1, min(int(limit), 5000)),
                ),
            ).fetchall()
        return [
            (
                str(row[0]),
                dict(row[1]) if isinstance(row[1], dict) else list(row[1]) if isinstance(row[1], list) else row[1],
                int(row[2]),
            )
            for row in rows
        ]

    def delete(
        self,
        *,
        module: str,
        record_type: str,
        record_id: str,
    ) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s
                """,
                (self.context.workspace_id, module, record_type, record_id),
            )
        return cursor.rowcount == 1

    def clear(self, *, module: str, record_type: str) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM omnix_module_records
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                """,
                (self.context.workspace_id, module, record_type),
            )
        return int(cursor.rowcount)
