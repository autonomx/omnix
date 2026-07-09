from __future__ import annotations

from pathlib import Path

import pytest

from app.assistant_memory import default_memory_service, resolve_chat_scope
from app.characters import CharacterRepository, CreateCharacterRequest, SetSessionInteractionRequest
from app.characters.management import CharacterDataActionRequest, CharacterManagementService
from app.characters.service import default_character_service
from app.chat import ChatMessage, CreateChatSessionRequest, default_chat_store


def _configure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_ASSISTANT_MEMORY_DB_PATH", str(tmp_path / "memory.sqlite3"))


def _seed(tmp_path: Path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    CharacterRepository().create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be warm and easygoing.",
            default_greeting="Hey.",
        )
    )
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Maya relationship"))
    session = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(interaction_mode="character", character_id="maya"),
    )
    assert session is not None
    session.messages.append(
        ChatMessage(
            id="message:maya",
            role="user",
            content="Remember our rainy hike joke.",
            created_at="2026-01-01T00:00:00Z",
            metadata={"segment_id": session.active_segment_id},
        )
    )
    store._save_sessions([session])
    memory = default_memory_service().create_explicit_memory(
        resolve_chat_scope(session.id, owner_type="character", owner_id="maya"),
        scope="global",
        category="relationship",
        content="Maya and the user joke about rainy hikes.",
        provenance_id="message:maya",
    )
    return store, session, memory


def test_export_reports_only_character_owned_backend_state(tmp_path: Path, monkeypatch) -> None:
    store, session, memory = _seed(tmp_path, monkeypatch)
    service = CharacterManagementService(default_character_service(), store)

    exported = service.export("maya")

    assert exported.character.id == "maya"
    assert exported.versions[0].version == 1
    assert [item["id"] for item in exported.memories] == [memory.id]
    assert exported.sessions[0].id == session.id
    assert exported.sessions[0].character_message_count >= 1


def test_relationship_reset_deletes_memory_and_character_transcript_only(tmp_path: Path, monkeypatch) -> None:
    store, session, _ = _seed(tmp_path, monkeypatch)
    session.messages.append(
        ChatMessage(
            id="message:system",
            role="assistant",
            content="System-owned message.",
            created_at="2026-01-01T00:00:01Z",
            metadata={"segment_id": "segment:other"},
        )
    )
    store._save_sessions([session])
    service = CharacterManagementService(default_character_service(), store)

    result = service.apply(
        "maya",
        CharacterDataActionRequest(
            confirm_character_id="maya",
            delete_memories=True,
            delete_transcripts=True,
        ),
    )

    assert result.deleted_memory_records == 1
    assert result.deleted_transcript_messages >= 2
    exported = service.export("maya")
    assert exported.memories == []
    loaded = store.get_session(session.id)
    assert loaded is not None
    assert [message.id for message in loaded.messages] == ["message:system"]


def test_destructive_actions_require_exact_character_confirmation(tmp_path: Path, monkeypatch) -> None:
    store, _, _ = _seed(tmp_path, monkeypatch)
    service = CharacterManagementService(default_character_service(), store)

    with pytest.raises(ValueError, match="confirmation"):
        service.apply(
            "maya",
            CharacterDataActionRequest(
                confirm_character_id="other",
                delete_memories=True,
            ),
        )


def test_profile_archive_is_independent_from_memory(tmp_path: Path, monkeypatch) -> None:
    store, _, _ = _seed(tmp_path, monkeypatch)
    service = CharacterManagementService(default_character_service(), store)

    result = service.apply(
        "maya",
        CharacterDataActionRequest(
            confirm_character_id="maya",
            archive_profile=True,
        ),
    )

    assert result.profile_archived is True
    exported = service.export("maya")
    assert exported.character.status == "archived"
    assert len(exported.memories) == 1
