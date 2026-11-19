"""A claim on a message's metadata has one winner, on PostgreSQL too (companion roadmap 1.5)."""
from __future__ import annotations

import json
import os
import threading
import uuid
from types import SimpleNamespace

import psycopg
import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.platform.chat.message_claims import ABSENT
from app.runtime.tenant_context import install_process_tenant
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

_CLAIMERS = 6


@pytest.fixture
def chat():
    from app.platform.chat.persistence.chat_runtime import PostgresCharacterChatSessionStore
    from app.platform.chat.persistence.chat_store import PostgresChatRepositoryAdapter

    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1,
                                                 pool_max=_CLAIMERS + 2))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    session_id = f"chat:message-claim:{uuid.uuid4().hex}"
    message_id = f"{session_id}:proposal"
    metadata = {"governed_tool_execution_status": "pending", "call_task_id": "call-task:x:0", "nothing": None}
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute(
            "INSERT INTO omnix_chat_sessions (id, workspace_id, title, profile_id, message_count) "
            "VALUES (%s, %s, 'claim test', 'default', 1)",
            (session_id, tenant.workspace_id),
        )
        admin.execute(
            "INSERT INTO omnix_chat_messages (id, workspace_id, session_id, position, role, content, metadata) "
            "VALUES (%s, %s, %s, 0, 'assistant', 'Turn off the lamp?', %s::jsonb)",
            (message_id, tenant.workspace_id, session_id, json.dumps(metadata)),
        )
    store = PostgresCharacterChatSessionStore(
        memory_settings_factory=lambda: SimpleNamespace(transcript_retention_enabled=True))
    store._repository = PostgresChatRepositoryAdapter(database=database)
    try:
        yield store, session_id, message_id
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_chat_messages WHERE session_id = %s", (session_id,))
            admin.execute("DELETE FROM omnix_chat_sessions WHERE id = %s", (session_id,))
        database.close()


def _metadata(store, session_id: str, message_id: str) -> dict:
    session = store.get_session(session_id)
    return next(message for message in session.messages if message.id == message_id).metadata


def test_claims_at_once_have_exactly_one_winner(chat) -> None:
    store, session_id, message_id = chat
    barrier = threading.Barrier(_CLAIMERS)
    won: list[int] = []
    errors: list[BaseException] = []

    def claim(index: int) -> None:
        barrier.wait()
        try:
            if store.claim_message_metadata(
                    session_id=session_id, message_id=message_id,
                    require={"governed_tool_execution_status": "pending"},
                    patch={"governed_tool_execution_status": "executing", "claimed_by": index}):
                won.append(index)
        except BaseException as error:  # noqa: BLE001 - collected for the assertion
            errors.append(error)

    threads = [threading.Thread(target=claim, args=(index,)) for index in range(_CLAIMERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)

    assert errors == [] and len(won) == 1
    metadata = _metadata(store, session_id, message_id)
    assert metadata["governed_tool_execution_status"] == "executing" and metadata["claimed_by"] == won[0]
    assert metadata["call_task_id"] == "call-task:x:0"  # merged, not replaced


def test_a_missing_key_and_a_null_are_different_conditions(chat) -> None:
    store, session_id, message_id = chat

    def claim(require: dict) -> bool:
        return store.claim_message_metadata(session_id=session_id, message_id=message_id, require=require,
                                            patch={"stamp": "2026-11-15T10:00:00+00:00"})

    assert not claim({"nothing": ABSENT})  # present, as a null
    assert not claim({"stamp": None})  # missing, which is not a null
    assert not claim({"governed_tool_execution_status": "executed"})
    assert not store.claim_message_metadata(session_id=session_id, message_id=f"{message_id}:other",
                                            require={}, patch={"stamp": "x"})
    assert claim({"stamp": ABSENT, "nothing": None, "governed_tool_execution_status": "pending"})
    assert not claim({"stamp": ABSENT})  # now taken
    assert store.claim_message_metadata(session_id=session_id, message_id=message_id,
                                        require={"stamp": "2026-11-15T10:00:00+00:00"},
                                        patch={"stamp": "2026-11-15T10:00:11+00:00"})
    assert _metadata(store, session_id, message_id)["stamp"] == "2026-11-15T10:00:11+00:00"
