"""PostgreSQL authority for legacy chat-session compatibility."""
from __future__ import annotations

import json
from typing import Any, Callable, TypeVar

from app.persistence.database import default_database
from app.persistence.document_store import PostgresDocumentStore
from app.security.tenant_context import current_tenant

_T = TypeVar("_T")


def load_legacy_chat_sessions() -> dict[str, Any]:
    payload = PostgresDocumentStore().read(
        module="platform",
        record_type="legacy-chat-sessions",
        default={},
    )
    return dict(payload or {})


def save_legacy_chat_sessions(payload: dict[str, Any]) -> None:
    PostgresDocumentStore().write(
        dict(payload),
        module="platform",
        record_type="legacy-chat-sessions",
    )


def mutate_legacy_chat_sessions(
    mutator: Callable[[dict[str, Any]], _T],
) -> tuple[dict[str, Any], _T]:
    database = default_database()
    context = current_tenant()
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO omnix_module_records (
                workspace_id, module, record_type, record_id, owner_user_id, payload
            ) VALUES (%s, 'platform', 'legacy-chat-sessions', 'default', %s, '{}'::jsonb)
            ON CONFLICT (workspace_id, module, record_type, record_id) DO NOTHING
            """,
            (context.workspace_id, context.user_id),
        )
        row = connection.execute(
            """
            SELECT payload
              FROM omnix_module_records
             WHERE workspace_id = %s AND module = 'platform'
               AND record_type = 'legacy-chat-sessions' AND record_id = 'default'
             FOR UPDATE
            """,
            (context.workspace_id,),
        ).fetchone()
        current = dict(row[0] or {}) if row is not None else {}
        result = mutator(current)
        connection.execute(
            """
            UPDATE omnix_module_records
               SET payload = %s::jsonb, status = 'active',
                   revision = revision + 1, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND module = 'platform'
               AND record_type = 'legacy-chat-sessions' AND record_id = 'default'
            """,
            (json.dumps(current), context.workspace_id),
        )
    return current, result


def install_postgresql_legacy_session_callbacks() -> None:
    from app.chat.legacy_session_state import install_legacy_session_callbacks

    install_legacy_session_callbacks(
        load_callback=load_legacy_chat_sessions,
        save_callback=save_legacy_chat_sessions,
        update_callback=mutate_legacy_chat_sessions,
    )
