from __future__ import annotations

from pathlib import Path

from app.characters import CharacterRepository, CreateCharacterRequest
from app.chat import CreateChatSessionRequest, SendChatMessageRequest, default_chat_store
import pytest

# Uses the PostgreSQL-backed runtime; runs in the test-postgres job.
# Shares the fixed 'maya' character; serialize on one xdist worker.
pytestmark = [pytest.mark.postgres, pytest.mark.xdist_group("characters-maya")]


def _configure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    CharacterRepository().create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be easygoing and warm.",
            default_greeting="Hey, good to hear from you.",
        )
    )


def test_streaming_turn_messages_are_tagged_with_active_segment(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Streaming"))
    begun = store.begin_user_message(session.id, SendChatMessageRequest(content="Hello"))
    assert begun is not None
    _, user_message = begun
    completed = store.complete_streamed_reply(session.id, user_message.id, "Hi there.", {"generation_status": "completed"})
    assert completed is not None
    assert completed.messages[-2].metadata["segment_id"] == session.active_segment_id
    assert completed.messages[-1].metadata["segment_id"] == session.active_segment_id


