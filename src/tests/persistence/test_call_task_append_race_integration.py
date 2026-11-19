"""A call's background result and a live turn's commit on the same chat both land (companion roadmap 1.2)."""
from __future__ import annotations

import json
import os
import threading
import uuid

import psycopg
import pytest

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

_ROUNDS = 8


@pytest.fixture
def chat():
    from app.platform.chat.persistence.chat_runtime import PostgresCharacterChatSessionStore
    from app.platform.chat.persistence.chat_store import PostgresChatRepositoryAdapter

    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=6))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    session_id = f"chat:call-task-race:{uuid.uuid4().hex}"
    rows = []
    for index in range(_ROUNDS):
        rows.append((f"{session_id}:user:{index}", "user", f"turn {index}", {"generation_status": "running"}))
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute(
            "INSERT INTO omnix_chat_sessions (id, workspace_id, title, profile_id, message_count) "
            "VALUES (%s, %s, 'race test', 'default', %s)",
            (session_id, tenant.workspace_id, len(rows)),
        )
        with admin.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO omnix_chat_messages (id, workspace_id, session_id, position, role, content, metadata) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                [(message_id, tenant.workspace_id, session_id, position, role, content, json.dumps(metadata))
                 for position, (message_id, role, content, metadata) in enumerate(rows)],
            )
    from types import SimpleNamespace

    store = PostgresCharacterChatSessionStore(
        memory_settings_factory=lambda: SimpleNamespace(transcript_retention_enabled=True))
    store._repository = PostgresChatRepositoryAdapter(database=database)
    try:
        yield store, session_id, [row[0] for row in rows]
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_chat_messages WHERE session_id = %s", (session_id,))
            admin.execute("DELETE FROM omnix_chat_sessions WHERE id = %s", (session_id,))
        database.close()


def _together(*calls) -> list[BaseException]:
    barrier = threading.Barrier(len(calls))
    errors: list[BaseException] = []

    def run(call) -> None:
        barrier.wait()
        try:
            call()
        except BaseException as error:  # noqa: BLE001 - collected for the assertion
            errors.append(error)

    threads = [threading.Thread(target=run, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return errors


def test_a_background_result_and_a_live_commit_both_land(chat) -> None:
    store, session_id, user_ids = chat

    errors: list[BaseException] = []
    for index, user_id in enumerate(user_ids):
        task_id = f"call-task:{user_id}:0"
        errors += _together(
            lambda user_id=user_id: store.complete_streamed_reply(
                session_id, user_id, "Sure.", {"call_tasks": [], "reply_to_message_id": user_id}),
            lambda index=index, task_id=task_id: store.append_assistant_message(
                session_id, f"Report {index}.", {"turn_id": task_id, "call_task_id": task_id}),
        )

    assert errors == []
    session = store.get_session(session_id)
    replies = {message.metadata.get("reply_to_message_id") for message in session.messages if message.role == "assistant"}
    results = [message.metadata.get("call_task_id") for message in session.messages if message.metadata.get("call_task_id")]
    assert set(user_ids) <= replies
    assert sorted(results) == sorted(f"call-task:{user_id}:0" for user_id in user_ids)

    # A retried append is the same message, never a second one.
    again = store.append_assistant_message(session_id, "Report 0.", {"turn_id": results[0], "call_task_id": results[0]})
    assert again is not None and again[2] is True


def test_a_start_record_and_a_background_result_both_land(chat) -> None:
    store, session_id, user_ids = chat
    for user_id in user_ids:
        store.complete_streamed_reply(session_id, user_id, "Sure.", {
            "call_tasks": [{"index": 0, "allowed": True}], "reply_to_message_id": user_id})
    replies = {message.metadata["reply_to_message_id"]: message.id
               for message in store.get_session(session_id).messages if message.role == "assistant"}

    errors: list[BaseException] = []
    for user_id in user_ids:
        task_id = f"call-task:{user_id}:0"
        errors += _together(
            lambda user_id=user_id: store.update_message_metadata(
                session_id=session_id, message_id=replies[user_id],
                metadata={"call_tasks": [{"index": 0, "allowed": True, "start": "started", "job_id": "job:x"}]}),
            lambda task_id=task_id: store.append_assistant_message(
                session_id, "Report.", {"turn_id": task_id, "call_task_id": task_id}),
        )

    assert errors == []
    session = store.get_session(session_id)
    started = [message.metadata["call_tasks"][0].get("start") for message in session.messages
               if message.role == "assistant" and message.metadata.get("call_tasks")]
    assert started == ["started"] * len(user_ids)
    assert len([message for message in session.messages if message.metadata.get("call_task_id")]) == len(user_ids)
