from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.platform.chat.repository import InMemoryChatRepository
from app.composition.gateway.main import create_gateway_app
import pytest

# Uses the PostgreSQL-backed runtime; runs in the test-postgres job.
# Shares the fixed 'maya' character; serialize on one xdist worker.
pytestmark = [pytest.mark.postgres, pytest.mark.xdist_group("characters-maya")]


def _client() -> TestClient:
    return TestClient(
        create_gateway_app(),
        base_url="http://localhost:5173",
        headers={"X-Omnix-Client": "test"},
    )


def _create_maya(client: TestClient) -> None:
    response = client.post(
        "/api/characters",
        json={
            "id": "maya",
            "display_name": "Maya",
            "description": "An easygoing character.",
            "personality_prompt": "Be warm, easygoing, and lightly humorous.",
            "default_greeting": "Hey, good to hear from you.",
            "speech_style": {"speed": 0.94},
        },
    )
    assert response.status_code == 201


def test_chat_runtime_repository_does_not_mutate_legacy_sqlite_source(tmp_path: Path) -> None:
    path = tmp_path / "chat.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE chat_schema_version(version INTEGER NOT NULL);
            INSERT INTO chat_schema_version(version) VALUES (1);
            CREATE TABLE chat_sessions(
                id TEXT PRIMARY KEY, title TEXT NOT NULL, provider_id TEXT, model_id TEXT,
                research_mode_override TEXT, profile_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                project_id TEXT, memory_enabled INTEGER NOT NULL, memory_snapshot_id TEXT,
                memory_snapshot_revision INTEGER, memory_record_count INTEGER NOT NULL,
                memory_last_refreshed_at TEXT, message_count INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE chat_messages(
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, position INTEGER NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL, UNIQUE(session_id, position)
            );
            CREATE TABLE chat_session_metadata(session_id TEXT NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL, PRIMARY KEY(session_id,key));
            CREATE TABLE chat_import_state(source_path TEXT PRIMARY KEY, source_hash TEXT NOT NULL, status TEXT NOT NULL, imported_session_count INTEGER NOT NULL, imported_message_count INTEGER NOT NULL, skipped_session_count INTEGER NOT NULL, errors_json TEXT NOT NULL, updated_at TEXT NOT NULL);
            """
        )

    repository = InMemoryChatRepository(path)
    assert repository.load_sessions() == []

    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(chat_sessions)")}
        version = connection.execute("SELECT version FROM chat_schema_version").fetchone()[0]
    assert version == 1
    assert "interaction_mode" not in columns
