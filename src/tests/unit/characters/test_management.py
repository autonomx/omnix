from __future__ import annotations

from pathlib import Path

import pytest

from app.platform.assistant_memory import (
    OwnerAwareInMemoryMemoryRepository,
    default_memory_service,
    resolve_chat_scope,
)
from app.platform.characters import CharacterRepository, CreateCharacterRequest, SetSessionInteractionRequest
from app.platform.characters.management import CharacterDataActionRequest, CharacterManagementService
from app.platform.characters.service import default_character_service
from app.platform.chat import ChatMessage, CreateChatSessionRequest, default_chat_store


@pytest.fixture(autouse=True)
def legacy_test_persistence(monkeypatch):
    from app.persistence.runtime import reset_persistence_mode_cache
    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.setenv("OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE", "1")
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "1")
    reset_persistence_mode_cache()
    yield
    reset_persistence_mode_cache()


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
    store._save_session(session)
    memory = default_memory_service().create_explicit_memory(
        resolve_chat_scope(session.id, owner_type="character", owner_id="maya"),
        scope="global",
        category="relationship",
        content="Maya and the user joke about rainy hikes.",
        provenance_id="message:maya",
    )
    return store, session, memory


def _memory_repository() -> OwnerAwareInMemoryMemoryRepository:
    return OwnerAwareInMemoryMemoryRepository()


def test_export_reports_only_character_owned_backend_state(tmp_path: Path, monkeypatch) -> None:
    store, session, memory = _seed(tmp_path, monkeypatch)
    service = CharacterManagementService(default_character_service(), store, _memory_repository())

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
    store._save_session(session)
    service = CharacterManagementService(default_character_service(), store, _memory_repository())

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
    service = CharacterManagementService(default_character_service(), store, _memory_repository())

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
    service = CharacterManagementService(default_character_service(), store, _memory_repository())

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
