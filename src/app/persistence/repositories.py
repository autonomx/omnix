from __future__ import annotations

import json
from typing import Any

from .errors import EntityNotFound, IdempotencyConflict, RevisionConflict
from .tenant import (
    LOCAL_MEMBERSHIP_ID,
    LOCAL_USER_ID,
    LOCAL_WORKSPACE_ID,
    TenantAccessDenied,
    TenantContext,
)


def _workspace(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "name": str(row[1]),
        "status": str(row[2]),
        "revision": int(row[3]),
        "created_by": str(row[4]),
        "created_at": row[5].isoformat(),
        "updated_at": row[6].isoformat(),
        "metadata": dict(row[7] or {}),
    }


class PostgresIdentityRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def ensure_local_identity(self) -> TenantContext:
        self.connection.execute(
            """
            INSERT INTO omnix_users (id, display_name, metadata)
            VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            (LOCAL_USER_ID, "Local Omnix User", json.dumps({"installation_local": True})),
        )
        self.connection.execute(
            """
            INSERT INTO omnix_workspaces (id, name, created_by, metadata)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                LOCAL_WORKSPACE_ID,
                "Local Omnix Workspace",
                LOCAL_USER_ID,
                json.dumps({"installation_local": True}),
            ),
        )
        self.connection.execute(
            """
            INSERT INTO omnix_workspace_memberships
                (id, workspace_id, user_id, roles)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (workspace_id, user_id) DO NOTHING
            """,
            (
                LOCAL_MEMBERSHIP_ID,
                LOCAL_WORKSPACE_ID,
                LOCAL_USER_ID,
                ["owner", "admin", "member"],
            ),
        )
        return self.load_context(user_id=LOCAL_USER_ID, workspace_id=LOCAL_WORKSPACE_ID)

    def load_context(self, *, user_id: str, workspace_id: str) -> TenantContext:
        row = self.connection.execute(
            """
            SELECT m.id, m.user_id, m.workspace_id, m.roles
            FROM omnix_workspace_memberships AS m
            JOIN omnix_users AS u ON u.id = m.user_id AND u.status = 'active'
            JOIN omnix_workspaces AS w ON w.id = m.workspace_id AND w.status = 'active'
            WHERE m.user_id = %s AND m.workspace_id = %s AND m.status = 'active'
            """,
            (user_id, workspace_id),
        ).fetchone()
        if row is None:
            raise TenantAccessDenied(
                f"user {user_id} has no active membership in workspace {workspace_id}"
            )
        return TenantContext(
            membership_id=str(row[0]),
            user_id=str(row[1]),
            workspace_id=str(row[2]),
            roles=frozenset(str(role) for role in row[3]),
        )

    def get_workspace(self, context: TenantContext, workspace_id: str) -> dict[str, Any] | None:
        context.require_workspace(workspace_id)
        row = self.connection.execute(
            """
            SELECT w.id, w.name, w.status, w.revision, w.created_by,
                   w.created_at, w.updated_at, w.metadata
            FROM omnix_workspaces AS w
            JOIN omnix_workspace_memberships AS m
              ON m.workspace_id = w.id
             AND m.user_id = %s
             AND m.status = 'active'
            WHERE w.id = %s AND w.status = 'active'
            """,
            (context.user_id, workspace_id),
        ).fetchone()
        return _workspace(row) if row is not None else None

    def update_workspace_name(
        self,
        context: TenantContext,
        *,
        workspace_id: str,
        name: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        context.require_workspace(workspace_id)
        context.require_role("owner", "admin")
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("workspace name is required")
        row = self.connection.execute(
            """
            UPDATE omnix_workspaces
               SET name = %s,
                   revision = revision + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s
               AND status = 'active'
               AND revision = %s
            RETURNING id, name, status, revision, created_by,
                      created_at, updated_at, metadata
            """,
            (normalized, workspace_id, expected_revision),
        ).fetchone()
        if row is not None:
            return _workspace(row)
        current = self.connection.execute(
            "SELECT revision FROM omnix_workspaces WHERE id = %s",
            (workspace_id,),
        ).fetchone()
        if current is None:
            raise EntityNotFound(workspace_id)
        raise RevisionConflict(
            f"workspace {workspace_id} expected revision {expected_revision}; current {int(current[0])}"
        )


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
            """
            INSERT INTO omnix_audit_events
                (workspace_id, actor_user_id, aggregate_type, aggregate_id,
                 action, trace_id, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                context.workspace_id,
                context.user_id,
                aggregate_type,
                aggregate_id,
                action,
                trace_id,
                json.dumps(payload or {}, sort_keys=True, separators=(",", ":")),
            ),
        ).fetchone()
        return int(row[0])


class PostgresIdempotencyRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def reserve(
        self,
        context: TenantContext,
        *,
        scope: str,
        key: str,
        request_hash: str,
    ) -> dict[str, Any]:
        normalized_scope = str(scope).strip()
        normalized_key = str(key).strip()
        normalized_hash = str(request_hash).strip()
        if not normalized_scope or not normalized_key or not normalized_hash:
            raise ValueError("scope, key, and request_hash are required")
        inserted = self.connection.execute(
            """
            INSERT INTO omnix_idempotency_keys
                (workspace_id, operation_scope, operation_key, request_hash)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING status, request_hash, response, created_at, completed_at
            """,
            (context.workspace_id, normalized_scope, normalized_key, normalized_hash),
        ).fetchone()
        owner = inserted is not None
        row = inserted or self.connection.execute(
            """
            SELECT status, request_hash, response, created_at, completed_at
              FROM omnix_idempotency_keys
             WHERE workspace_id = %s
               AND operation_scope = %s
               AND operation_key = %s
            """,
            (context.workspace_id, normalized_scope, normalized_key),
        ).fetchone()
        if row is None:
            raise RuntimeError("idempotency reservation was not persisted")
        if str(row[1]) != normalized_hash:
            raise IdempotencyConflict(
                f"operation key {normalized_scope}/{normalized_key} was reused with different input"
            )
        return {
            "owner": owner,
            "status": str(row[0]),
            "request_hash": str(row[1]),
            "response": dict(row[2]) if row[2] is not None else None,
            "created_at": row[3].isoformat(),
            "completed_at": row[4].isoformat() if row[4] is not None else None,
        }

    def complete(
        self,
        context: TenantContext,
        *,
        scope: str,
        key: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            UPDATE omnix_idempotency_keys
               SET status = 'completed',
                   response = %s::jsonb,
                   completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
             WHERE workspace_id = %s
               AND operation_scope = %s
               AND operation_key = %s
            RETURNING status, request_hash, response, created_at, completed_at
            """,
            (
                json.dumps(response, sort_keys=True, separators=(",", ":")),
                context.workspace_id,
                scope,
                key,
            ),
        ).fetchone()
        if row is None:
            raise EntityNotFound(f"{scope}/{key}")
        return {
            "owner": False,
            "status": str(row[0]),
            "request_hash": str(row[1]),
            "response": dict(row[2]),
            "created_at": row[3].isoformat(),
            "completed_at": row[4].isoformat(),
        }
