from __future__ import annotations

import json
import sqlite3

import pytest

from app.chat import ChatMessage, ChatSession, CreateChatSessionRequest, SendChatMessageRequest
from app.chat.json_import import LegacyChatImportError
from app.chat.prompt_store import default_chat_store
from app.chat.repository import SQLiteChatRepository
from app.chat.sqlite_store import SQLiteChatSessionStore

NOW = "2026-07-08T00:00:00+00:00"


def legacy_payload() -> dict:
    return {
        "sessions": [
            {
                "id": "chat:legacy",
                "title": "Legacy chat",
                "provider_id": "llm:lmstudio",
                "model_id": "llm:lmstudio:test-model",
                "message_count": 2,
                "created_at": NOW,
                "updated_at": NOW,
                "messages": [
                    {
                        "id": "msg:one",
                        "role": "user",
                        "content": "Hello",
                        "created_at": NOW,
                        "metadata": {},
                    },
                    {
                        "id": "msg:two",
                        "role": "assistant",
                        "content": "Hi",
                        "created_at": NOW,
                        "metadata": {"generation_status": "completed"},
                    },
                ],
            }
        ]
    }


def test_legacy_json_import_is_transactional_idempotent_and_non_destructive(tmp_path):
    legacy = tmp_path / "chat.json"
    raw = json.dumps(legacy_payload(), indent=2).encode("utf-8")
    legacy.write_bytes(raw)
    db = tmp_path / "chat.sqlite3"

    first = SQLiteChatSessionStore(db, legacy_json_path=legacy)
    assert first.repository.counts() == (1, 2)
    imported = first.get_session("chat:legacy")
    assert imported is not None
    assert [message.content for message in imported.messages] == ["Hello", "Hi"]
    assert imported.workspace_id == "workspace:default"
    assert first.import_state is not None
    assert first.import_state.status == "completed"

    created = first.create_session(CreateChatSessionRequest(title="SQLite-native"))
    second = SQLiteChatSessionStore(db, legacy_json_path=legacy)
    assert second.get_session(created.id) is not None
    assert second.repository.counts() == (2, 2)
    assert second.import_state.source_hash == first.import_state.source_hash
    assert legacy.read_bytes() == raw


def test_import_quarantines_invalid_sessions_and_duplicate_message_ids(tmp_path):
    payload = legacy_payload()
    payload["sessions"].append({"id": "chat:invalid"})
    duplicate = legacy_payload()["sessions"][0]
    duplicate["id"] = "chat:second"
    duplicate["messages"] = [dict(duplicate["messages"][0])]
    payload["sessions"].append(duplicate)
    legacy = tmp_path / "chat.json"
    legacy.write_text(json.dumps(payload), encoding="utf-8")

    store = SQLiteChatSessionStore(tmp_path / "chat.sqlite3", legacy_json_path=legacy)

    assert store.import_state.imported_session_count == 2
    assert store.import_state.skipped_session_count == 1
    assert any("duplicate message id skipped" in error for error in store.import_state.errors)
    assert store.repository.counts() == (2, 2)


def test_invalid_json_records_failed_import_without_partial_sessions(tmp_path):
    legacy = tmp_path / "chat.json"
    legacy.write_text("{not-json", encoding="utf-8")
    db = tmp_path / "chat.sqlite3"

    with pytest.raises(LegacyChatImportError):
        SQLiteChatSessionStore(db, legacy_json_path=legacy)

    repository = SQLiteChatRepository(db)
    state = repository.get_import_state(str(legacy.resolve()))
    assert state is not None
    assert state.status == "failed"
    assert repository.counts() == (0, 0)


def test_repository_import_rolls_back_on_message_primary_key_collision(tmp_path):
    repository = SQLiteChatRepository(tmp_path / "chat.sqlite3")
    first = ChatSession(
        id="chat:one",
        title="One",
        created_at=NOW,
        updated_at=NOW,
        messages=[ChatMessage(id="msg:duplicate", role="user", content="One", created_at=NOW)],
    )
    second = ChatSession(
        id="chat:two",
        title="Two",
        created_at=NOW,
        updated_at=NOW,
        messages=[ChatMessage(id="msg:duplicate", role="user", content="Two", created_at=NOW)],
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.import_sessions(
            source_path="collision.json",
            source_hash="hash",
            sessions=[first, second],
            skipped_session_count=0,
            errors=[],
            updated_at=NOW,
        )
    assert repository.counts() == (0, 0)
    assert repository.get_import_state("collision.json") is None


def test_incomplete_streamed_turn_survives_restart_and_can_complete(tmp_path):
    db = tmp_path / "chat.sqlite3"
    store = SQLiteChatSessionStore(db, import_legacy=False)
    session = store.create_session(CreateChatSessionRequest(title="Streaming"))
    appended = store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="Persist me"),
    )
    assert appended is not None
    _, user_message = appended

    restarted = SQLiteChatSessionStore(db, import_legacy=False)
    running = restarted.get_session(session.id)
    assert running.messages[-1].metadata["generation_status"] == "running"
    completed = restarted.complete_streamed_reply(
        session.id,
        user_message.id,
        "Completed answer",
        {"generation_status": "completed"},
    )
    assert completed is not None

    final = SQLiteChatSessionStore(db, import_legacy=False).get_session(session.id)
    assert [message.content for message in final.messages] == ["Persist me", "Completed answer"]


def test_feature_flag_selects_sqlite_store_and_keeps_json_default(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_DB_PATH", str(tmp_path / "chat.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "missing.json"))
    assert isinstance(default_chat_store(), SQLiteChatSessionStore)

    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "0")
    assert not isinstance(default_chat_store(), SQLiteChatSessionStore)
