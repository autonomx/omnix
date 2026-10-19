"""Chat generative UI on PostgreSQL: the rich-replies setting and history recall (GUI-3.1, GUI-1.5)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from app.platform.chat.generative_ui import CompileScope, compile_chat_ui
from app.platform.chat.persistence.chat_runtime import PostgresHistorySearchService
from app.platform.chat.persistence.chat_store import PostgresChatRepositoryAdapter
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.runtime.tenant_context import install_process_tenant
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

FENCE = "```"
REPLY = f'Quarterly revenue held.\n\n{FENCE}omnix-ui\n{{"type": "stats", "items": [{{"label": "Revenue", "value": "$6,930"}}]}}\n{FENCE}'


@pytest.fixture
def chat():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    session_id = f"chat:gui-test:{uuid.uuid4().hex}"
    profile = f"profile-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute(
            "INSERT INTO omnix_chat_sessions (id, workspace_id, title, profile_id) VALUES (%s, %s, 'gui test', %s)",
            (session_id, tenant.workspace_id, profile),
        )
    try:
        yield database, tenant, session_id, profile
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_chat_messages WHERE session_id = %s", (session_id,))
            admin.execute("DELETE FROM omnix_chat_sessions WHERE id = %s", (session_id,))
        database.close()


def test_rich_replies_round_trips_and_unset_reads_as_none(chat) -> None:
    database, _tenant, session_id, _ = chat
    adapter = PostgresChatRepositoryAdapter(database)

    session = adapter.get_session(session_id)
    assert session is not None and session.rich_replies is None
    session.rich_replies = "on"
    adapter.save_session(session)
    assert adapter.get_session(session_id).rich_replies == "on"

    session = adapter.get_session(session_id)
    session.rich_replies = None
    adapter.save_session(session)
    assert adapter.get_session(session_id).rich_replies is None


def test_history_search_recalls_a_block_reply_as_its_text(chat) -> None:
    database, tenant, session_id, profile = chat
    ui = compile_chat_ui(REPLY, CompileScope(clock=lambda: datetime(2026, 10, 11, tzinfo=timezone.utc)))
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute(
            "INSERT INTO omnix_chat_messages (id, workspace_id, session_id, position, role, content, metadata) "
            "VALUES (%s, %s, %s, 0, 'assistant', %s, %s::jsonb)",
            (f"{session_id}:0", tenant.workspace_id, session_id, REPLY, json.dumps({"ui": ui})),
        )

    result = PostgresHistorySearchService(database).search(
        "quarterly revenue", profile_id=profile, workspace_id=tenant.workspace_id, project_id=None,
    )

    assert [item.content for item in result.items] == ["Quarterly revenue held.\n\nRevenue: $6,930."]
