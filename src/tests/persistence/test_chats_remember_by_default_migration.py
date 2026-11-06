"""Existing chats join the owner's decision that characters and the System Assistant remember across chats."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import psycopg
import pytest

from app.persistence import migrations as migrations_module
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

MIGRATION = Path(migrations_module.__file__).parent / "migrations" / "0194_chats_remember_by_default.sql"


def _session(admin, mode: str, *, settings: dict | None = None, memory_enabled: bool = False) -> str:
    session_id = f"chat:{uuid.uuid4().hex}"
    admin.execute(
        """INSERT INTO omnix_chat_sessions (id, workspace_id, title, interaction_mode, memory_enabled, settings)
           VALUES (%s, 'workspace:local', 'Test', %s, %s, %s::jsonb)""",
        (session_id, mode, memory_enabled, json.dumps(settings or {})),
    )
    return session_id


def _segment(admin, session_id: str, mode: str, *, ended: bool) -> str:
    segment_id = f"segment:{uuid.uuid4().hex}"
    admin.execute(
        """INSERT INTO omnix_conversation_segments
               (id, workspace_id, session_id, interaction_mode, transcript_policy, ended_at)
           VALUES (%s, 'workspace:local', %s, %s, 'persistent', CASE WHEN %s THEN now() END)""",
        (segment_id, session_id, mode, ended),
    )
    return segment_id


def test_existing_chats_remember_and_nothing_else_changes() -> None:
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("SET session_replication_role = replica")
        character = _session(admin, "character", settings={"read_memory": False, "write_memory": False, "rich": "kept"})
        system = _session(admin, "system", settings={"read_memory": False})
        open_segment = _segment(admin, character, "character", ended=False)
        closed_segment = _segment(admin, character, "character", ended=True)
        system_segment = _segment(admin, system, "system", ended=False)
        message_count = admin.execute("SELECT count(*) FROM omnix_chat_messages").fetchone()[0]

        admin.execute(MIGRATION.read_text(encoding="utf-8"))

        settings, enabled = admin.execute(
            "SELECT settings, memory_enabled FROM omnix_chat_sessions WHERE id = %s", (character,)
        ).fetchone()
        assert settings == {"read_memory": True, "write_memory": True, "rich": "kept"}
        assert enabled is False  # a character's chats use read_memory
        settings, enabled = admin.execute(
            "SELECT settings, memory_enabled FROM omnix_chat_sessions WHERE id = %s", (system,)
        ).fetchone()
        assert settings == {"read_memory": False}
        assert enabled is True

        def flags(segment_id: str) -> tuple[bool, bool]:
            return admin.execute(
                "SELECT read_memory, write_memory FROM omnix_conversation_segments WHERE id = %s", (segment_id,)
            ).fetchone()

        assert flags(open_segment) == (True, True)
        assert flags(closed_segment) == (False, False)  # what a finished segment was stays on record
        assert flags(system_segment) == (False, False)
        # Set directly so no chat gets a new segment and greeting: its transcript is untouched.
        assert admin.execute("SELECT count(*) FROM omnix_chat_messages").fetchone()[0] == message_count

        admin.execute("DELETE FROM omnix_conversation_segments WHERE id = ANY(%s)", ([open_segment, closed_segment, system_segment],))
        admin.execute("DELETE FROM omnix_chat_sessions WHERE id = ANY(%s)", ([character, system],))
