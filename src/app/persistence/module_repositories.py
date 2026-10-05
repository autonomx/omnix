from __future__ import annotations

import json
from typing import Any

from app.runtime.pagination import page_limit

from .document_schemas import document_matches, validate_document
from .errors import RevisionConflict
from .tenant import TenantContext


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class PostgresModuleRecordRepository:
    """Tenant-scoped durable records for small modules without bespoke schemas."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def get(
        self,
        context: TenantContext,
        *,
        module: str,
        record_type: str,
        record_id: str,
        include_expired: bool = False,
    ) -> dict[str, Any] | None:
        expiry = "" if include_expired else " AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)"
        row = self.connection.execute(
            """
            SELECT module, record_type, record_id, owner_user_id, payload,
                   status, revision, expires_at, created_at, updated_at
              FROM omnix_module_records
             WHERE workspace_id = %s AND module = %s AND record_type = %s
               AND record_id = %s
            """
            + expiry,
            (context.workspace_id, module, record_type, record_id),
        ).fetchone()
        if row is None:
            return None
        record = self._record(row)
        if record["status"] == "active":
            document_matches(module, record_type, record["payload"], record_id=record_id)
        return record

    def put(
        self,
        context: TenantContext,
        *,
        module: str,
        record_type: str,
        record_id: str,
        payload: dict[str, Any],
        status: str = "active",
        expires_at: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        if status == "active":
            # An active document must match its kind's registered shape (WP-5.9).
            validate_document(module, record_type, payload)
        if expected_revision is None:
            row = self.connection.execute(
                """
                INSERT INTO omnix_module_records (
                    workspace_id, module, record_type, record_id, owner_user_id,
                    payload, status, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::timestamptz)
                ON CONFLICT DO NOTHING
                RETURNING module, record_type, record_id, owner_user_id, payload,
                          status, revision, expires_at, created_at, updated_at
                """,
                (
                    context.workspace_id,
                    module,
                    record_type,
                    record_id,
                    context.user_id,
                    _json(payload),
                    status,
                    expires_at,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict(
                    f"module record already exists: {module}/{record_type}/{record_id}"
                )
        else:
            row = self.connection.execute(
                """
                UPDATE omnix_module_records
                   SET payload = %s::jsonb, status = %s,
                       expires_at = %s::timestamptz,
                       revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s AND revision = %s
                RETURNING module, record_type, record_id, owner_user_id, payload,
                          status, revision, expires_at, created_at, updated_at
                """,
                (
                    _json(payload),
                    status,
                    expires_at,
                    context.workspace_id,
                    module,
                    record_type,
                    record_id,
                    expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict(
                    f"module record expected revision {expected_revision}: "
                    f"{module}/{record_type}/{record_id}"
                )
        return self._record(row)

    def list(
        self,
        context: TenantContext,
        *,
        module: str,
        record_type: str,
        status: str = "active",
        limit: int = 100,
        after: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Most recently updated first; ``after`` is the last ``(updated_at, record_id)`` seen."""
        rows = self.connection.execute(
            """
            SELECT module, record_type, record_id, owner_user_id, payload,
                   status, revision, expires_at, created_at, updated_at
              FROM omnix_module_records
             WHERE workspace_id = %s AND module = %s AND record_type = %s
               AND status = %s AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
               AND (%s::timestamptz IS NULL
                    OR updated_at < %s::timestamptz
                    OR (updated_at = %s::timestamptz AND record_id > %s))
             ORDER BY updated_at DESC, record_id LIMIT %s
            """,
            (
                context.workspace_id,
                module,
                record_type,
                status,
                after[0] if after else None,
                after[0] if after else None,
                after[0] if after else None,
                after[1] if after else None,
                page_limit(limit, default=100),
            ),
        ).fetchall()
        return [self._record(row) for row in rows]

    @staticmethod
    def _record(row: Any) -> dict[str, Any]:
        return {
            "module": str(row[0]),
            "record_type": str(row[1]),
            "record_id": str(row[2]),
            "owner_user_id": str(row[3]) if row[3] is not None else None,
            "payload": dict(row[4]),
            "status": str(row[5]),
            "revision": int(row[6]),
            "expires_at": row[7].isoformat() if row[7] is not None else None,
            "created_at": row[8].isoformat(),
            "updated_at": row[9].isoformat(),
        }


class PostgresProjectionRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def put(
        self,
        context: TenantContext,
        *,
        projection_type: str,
        projection_key: str,
        payload: dict[str, Any],
        source_revision: int | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO omnix_runtime_projections (
                workspace_id, projection_type, projection_key, payload,
                source_revision, expires_at
            ) VALUES (%s, %s, %s, %s::jsonb, %s, %s::timestamptz)
            ON CONFLICT (workspace_id, projection_type, projection_key)
            DO UPDATE SET payload = EXCLUDED.payload,
                          source_revision = EXCLUDED.source_revision,
                          observed_at = CURRENT_TIMESTAMP,
                          expires_at = EXCLUDED.expires_at
            RETURNING projection_type, projection_key, payload, source_revision,
                      observed_at, expires_at
            """,
            (
                context.workspace_id,
                projection_type,
                projection_key,
                _json(payload),
                source_revision,
                expires_at,
            ),
        ).fetchone()
        return self._record(row)

    def get(
        self,
        context: TenantContext,
        *,
        projection_type: str,
        projection_key: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT projection_type, projection_key, payload, source_revision,
                   observed_at, expires_at
              FROM omnix_runtime_projections
             WHERE workspace_id = %s AND projection_type = %s AND projection_key = %s
               AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """,
            (context.workspace_id, projection_type, projection_key),
        ).fetchone()
        return self._record(row) if row is not None else None

    @staticmethod
    def _record(row: Any) -> dict[str, Any]:
        return {
            "projection_type": str(row[0]),
            "projection_key": str(row[1]),
            "payload": dict(row[2]),
            "source_revision": int(row[3]) if row[3] is not None else None,
            "observed_at": row[4].isoformat(),
            "expires_at": row[5].isoformat() if row[5] is not None else None,
        }
