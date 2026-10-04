"""A chat turn loads only the part of the transcript its prompt can read (WP-5.7)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from app.chat.models import ChatMessage
from app.chat.persistence.chat_store import PostgresChatRepositoryAdapter
from app.chat.prompt_assembly import build_prompt_assembly
from app.chat.prompt_rendering import render_prompt_assembly
from app.chat.prompt_window import build_prompt_assembly_with_window
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


@pytest.fixture
def chat():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    session_id = f"chat:window-test:{uuid.uuid4().hex}"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute(
            "INSERT INTO omnix_chat_sessions (id, workspace_id, title, profile_id) VALUES (%s, %s, 'window test', 'default')",
            (session_id, tenant.workspace_id),
        )
    try:
        yield database, tenant, session_id
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_chat_messages WHERE session_id = %s", (session_id,))
            admin.execute("DELETE FROM omnix_chat_sessions WHERE id = %s", (session_id,))
            admin.execute("DELETE FROM omnix_conversation_segments WHERE session_id = %s", (session_id,))
        database.close()


def _seed(tenant, session_id: str, rows: list[tuple[str, str, dict]], *, active_segment_id: str | None = None) -> None:
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        with admin.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO omnix_chat_messages (id, workspace_id, session_id, position, role, content, metadata) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                [
                    (f"{session_id}:{index}", tenant.workspace_id, session_id, index, role, content, json.dumps(metadata))
                    for index, (role, content, metadata) in enumerate(rows)
                ],
            )
        if active_segment_id is not None:
            admin.execute(
                "INSERT INTO omnix_conversation_segments (id, workspace_id, session_id, interaction_mode, transcript_policy) "
                "VALUES (%s, %s, %s, 'system', 'persistent')",
                (active_segment_id, tenant.workspace_id, session_id),
            )
        admin.execute(
            "UPDATE omnix_chat_sessions SET message_count = %s, active_segment_id = %s WHERE id = %s",
            (len(rows), active_segment_id, session_id),
        )


def _prompt(session, recent_message_limit: int | None):
    user_message = ChatMessage(
        id=f"msg:{uuid.uuid4().hex}",
        role="user",
        content="what did we decide earlier?",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    assembly = build_prompt_assembly_with_window(
        build_prompt_assembly,
        session,
        user_message,
        global_system_prompt="",
        context_items=[],
        approved_memory=[],
        retrieved_history=[],
        recent_message_limit=recent_message_limit,
    )
    rendered = render_prompt_assembly(assembly)
    return [(message.role, message.content) for message in rendered.messages], assembly.diagnostics["prompt_window"]


def _turns(count: int, content) -> list[tuple[str, str, dict]]:
    return [("user" if index % 2 == 0 else "assistant", content(index), {}) for index in range(count)]


@pytest.mark.parametrize(
    "content",
    [
        lambda index: f"message {index} " + "with ordinary words " * (index % 7),
        lambda index: "ok",  # tiny messages: the summary needs many of them
        lambda index: "a long reply " * 60,  # clipped at 500 characters
    ],
    ids=["mixed", "tiny", "long"],
)
def test_a_window_renders_the_same_prompt_as_the_whole_transcript(chat, content) -> None:
    database, tenant, session_id = chat
    _seed(tenant, session_id, _turns(3_000, content))
    adapter = PostgresChatRepositoryAdapter(database=database)

    full = adapter.get_session(session_id)
    window = adapter.get_session_window(session_id)

    assert window.transcript_is_window
    assert len(window.messages) < len(full.messages)
    assert window.message_count == full.message_count == 3_000
    assert [message.id for message in window.messages] == [message.id for message in full.messages[-len(window.messages):]]
    for limit in (None, 2, 24, 200):
        full_prompt, full_window = _prompt(full, limit)
        window_prompt, window_window = _prompt(window, limit)
        assert window_prompt == full_prompt
        assert window_window["summary_through_message_id"] == full_window["summary_through_message_id"]


def test_messages_outside_the_active_segment_do_not_count_toward_the_window(chat) -> None:
    database, tenant, session_id = chat
    segment = f"segment:{uuid.uuid4().hex}"
    rows = [("user" if index % 2 == 0 else "assistant", f"turn {index} " * 5, {"segment_id": "old" if index < 2_000 else segment})
            for index in range(2_600)]
    _seed(tenant, session_id, rows, active_segment_id=segment)
    adapter = PostgresChatRepositoryAdapter(database=database)

    full = adapter.get_session(session_id)
    window = adapter.get_session_window(session_id)

    assert window.transcript_is_window
    for limit in (24, 200):
        assert _prompt(window, limit)[0] == _prompt(full, limit)[0]


def test_a_short_session_loads_whole(chat) -> None:
    database, tenant, session_id = chat
    _seed(tenant, session_id, _turns(150, lambda index: f"message {index}"))

    window = PostgresChatRepositoryAdapter(database=database).get_session_window(session_id)

    assert not window.transcript_is_window
    assert len(window.messages) == 150


def test_a_window_saves_by_appending_after_its_first_message(chat) -> None:
    database, tenant, session_id = chat
    _seed(tenant, session_id, _turns(2_500, lambda index: f"message {index} about something"))
    adapter = PostgresChatRepositoryAdapter(database=database)
    window = adapter.get_session_window(session_id)
    assert window.transcript_is_window

    window.messages.append(ChatMessage(
        id=f"msg:{uuid.uuid4().hex}", role="user", content="appended", created_at=datetime.now(timezone.utc).isoformat(),
    ))
    adapter.save_session(window)

    full = adapter.get_session(session_id)
    assert len(full.messages) == 2_501
    assert full.messages[-1].content == "appended"
    assert full.messages[0].id == f"{session_id}:0"


def test_a_retried_turn_older_than_the_window_is_found_by_its_turn_id(chat) -> None:
    database, tenant, session_id = chat
    rows = _turns(2_500, lambda index: f"message {index} about something")
    rows[10] = ("user", "the original turn", {"user_turn_id": "turn-early"})
    _seed(tenant, session_id, rows)
    adapter = PostgresChatRepositoryAdapter(database=database)

    window = adapter.get_session_window(session_id)
    assert all(message.metadata.get("user_turn_id") != "turn-early" for message in window.messages)

    found = adapter.find_user_turn(session_id, "turn-early")
    assert found is not None and found.id == f"{session_id}:10"
    assert adapter.find_user_turn(session_id, "turn-unknown") is None


def test_a_generation_window_ends_at_its_own_turn(chat) -> None:
    database, tenant, session_id = chat
    _seed(tenant, session_id, _turns(2_500, lambda index: f"message {index} about something"))
    adapter = PostgresChatRepositoryAdapter(database=database)
    turn_id = f"{session_id}:2400"

    window = adapter.get_session_window(session_id, through_message_id=turn_id)
    full = adapter.get_session(session_id)

    index = next(i for i, message in enumerate(window.messages) if message.id == turn_id)
    full_index = next(i for i, message in enumerate(full.messages) if message.id == turn_id)
    sliced_window = window.model_copy(update={"messages": window.messages[: index + 1]})
    sliced_full = full.model_copy(update={"messages": full.messages[: full_index + 1]})
    for limit in (24, 200):
        assert _prompt(sliced_window, limit)[0] == _prompt(sliced_full, limit)[0]
