from __future__ import annotations

from pathlib import Path

from app.assistant_memory import default_memory_service, resolve_chat_scope
from app.characters import CharacterRepository, CreateCharacterRequest, SetSessionInteractionRequest
from app.chat import ChatMessage, CreateChatSessionRequest, default_chat_store


def _configure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_ASSISTANT_MEMORY_DB_PATH", str(tmp_path / "memory.sqlite3"))
    CharacterRepository().create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be warm and easygoing.",
            default_greeting="Hey.",
        )
    )


def _seed_maya_memory(session_id: str) -> None:
    service = default_memory_service()
    context = resolve_chat_scope(
        session_id,
        owner_type="character",
        owner_id="maya",
    )
    service.create_explicit_memory(
        context,
        scope="global",
        category="relationship",
        content="Maya remembers that the user enjoys rainy hikes.",
        provenance_id="seed",
    )


def test_read_only_character_memory_enters_prompt_but_does_not_enable_writes(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Maya memory"))
    _seed_maya_memory(session.id)

    updated = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(
            interaction_mode="character",
            character_id="maya",
            read_memory=True,
            write_memory=False,
        ),
    )
    assert updated is not None
    assert updated.read_memory is True
    assert updated.write_memory is False
    assert updated.memory_snapshot_id

    user_message = ChatMessage(
        id="user:current",
        role="user",
        content="What do you remember?",
        created_at="2026-01-01T00:00:00Z",
        metadata={"segment_id": updated.active_segment_id},
    )
    assembly, _ = store.build_provider_prompt(updated, user_message)
    assert [item.content for item in assembly.approved_memory] == [
        "Maya remembers that the user enjoys rainy hikes."
    ]


def test_write_only_character_starts_without_prompt_memory(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Maya write only"))
    _seed_maya_memory(session.id)

    updated = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(
            interaction_mode="character",
            character_id="maya",
            read_memory=False,
            write_memory=True,
        ),
    )
    assert updated is not None
    assert updated.memory_snapshot_id is None
    user_message = ChatMessage(
        id="user:current",
        role="user",
        content="Start fresh.",
        created_at="2026-01-01T00:00:00Z",
        metadata={"segment_id": updated.active_segment_id},
    )
    assembly, _ = store.build_provider_prompt(updated, user_message)
    assert assembly.approved_memory == []


def test_memory_off_clears_old_snapshot_and_prompt_context(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Maya toggle"))
    _seed_maya_memory(session.id)
    enabled = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(
            interaction_mode="character",
            character_id="maya",
            read_memory=True,
            write_memory=True,
        ),
    )
    assert enabled and enabled.memory_snapshot_id

    disabled = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(
            interaction_mode="character",
            character_id="maya",
            read_memory=False,
            write_memory=False,
        ),
    )
    assert disabled is not None
    assert disabled.memory_snapshot_id is None
    assert disabled.memory_record_count == 0
    assert disabled.read_memory is False
    assert disabled.write_memory is False
