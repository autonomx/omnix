"""Chat transcript, history search and summary lookups (WP-5.7)."""
from __future__ import annotations

import json
import os
import uuid

import psycopg
import pytest

from app.chat.persistence.chat_compat import PostgresChatRepositoryAdapter
from app.chat.persistence.chat_runtime_compat import (
    PostgresConversationSummaryRepository,
    PostgresHistorySearchService,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import install_process_tenant
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def chat():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    session_id = f"chat:query-test:{uuid.uuid4().hex}"
    profile = f"profile-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute(
            "INSERT INTO omnix_chat_sessions (id, workspace_id, title, profile_id) VALUES (%s, %s, 'query test', %s)",
            (session_id, tenant.workspace_id, profile),
        )
    try:
        yield database, tenant, session_id, profile
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_chat_messages WHERE session_id = %s", (session_id,))
            admin.execute("DELETE FROM omnix_chat_sessions WHERE id = %s", (session_id,))
            admin.execute("DELETE FROM omnix_module_records WHERE record_id LIKE %s", (f"summary:{session_id}%",))
        database.close()


def _messages(tenant, session_id: str, contents: list[str]) -> None:
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        with admin.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO omnix_chat_messages (id, workspace_id, session_id, position, role, content) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (f"{session_id}:{index}", tenant.workspace_id, session_id, index,
                     "user" if index % 2 == 0 else "assistant", content)
                    for index, content in enumerate(contents)
                ],
            )


def test_the_whole_transcript_loads_past_one_page(chat) -> None:
    database, tenant, session_id, _ = chat
    _messages(tenant, session_id, [f"message {index}" for index in range(450)])
    adapter = PostgresChatRepositoryAdapter(database=database)

    with unit_of_work(database) as work:
        loaded = adapter._list_all_messages(work, session_id)
        work.rollback()

    # The repository returns at most one page per call; the newest turns
    # must still be loaded (they were cut off at 100 before WP-5.7).
    assert [message["position"] for message in loaded] == list(range(450))


def test_history_search_matches_word_prefixes(chat) -> None:
    database, tenant, session_id, profile = chat
    _messages(tenant, session_id, ["We discussed PostgreSQL replication", "Lunch plans", "postgres tuning notes"])
    search = PostgresHistorySearchService(database)

    result = search.search("postgres", profile_id=profile, workspace_id=tenant.workspace_id, project_id=None)

    assert {item.content for item in result.items} == {"We discussed PostgreSQL replication", "postgres tuning notes"}
    assert result.status.reason == "postgresql_full_text"


def test_latest_summary_is_found_by_session(chat) -> None:
    database, tenant, session_id, _ = chat
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        with admin.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO omnix_module_records (workspace_id, module, record_type, record_id, payload) "
                "VALUES (%s, 'chat', 'conversation-summary', %s, %s::jsonb)",
                [
                    (tenant.workspace_id, f"summary:{session_id}:{index}", json.dumps({
                        "id": f"summary:{session_id}:{index}",
                        "session_id": session_id if index % 3 == 0 else f"{session_id}:other",
                        "through_message_id": f"m{index}", "revision": index + 1, "summary": f"s{index}",
                        "source_message_count": index + 1, "token_estimate": 1,
                        "created_at": "2026-10-01T00:00:00+00:00",
                    }))
                    for index in range(10)
                ],
            )
    summaries = PostgresConversationSummaryRepository(database)

    latest = summaries.latest(session_id)

    assert latest is not None and latest.summary == "s9" and latest.session_id == session_id
