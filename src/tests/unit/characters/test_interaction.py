from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.characters import (
    SYSTEM_ASSISTANT_IDENTITY,
    CharacterModeDisabledError,
    CharacterProfileSnapshot,
    CharacterResolutionError,
    InteractionSelection,
    neutralize_legacy_system_prompt,
    resolve_interaction_context,
)
from app.characters.interaction import LEGACY_MAYA_SYSTEM_PROMPT
from app.chat.models import ChatMessage, ChatSession, CreateChatSessionRequest
from app.chat.prompt_assembly import build_prompt_assembly


def _session(**overrides: object) -> ChatSession:
    payload: dict[str, object] = {
        "id": "chat:test",
        "title": "Test",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "messages": [],
    }
    payload.update(overrides)
    return ChatSession(**payload)


def _character() -> CharacterProfileSnapshot:
    return CharacterProfileSnapshot(
        id="maya",
        display_name="Maya",
        personality_prompt="Be easygoing, warm, and lightly humorous.",
        default_greeting="Hey, good to hear from you.",
        default_voice_asset_id="voice-cloning:maya",
        version=3,
        identity_policy={"may_claim_to_be_human": False},
    )


def test_system_interaction_is_deterministic_and_voice_independent() -> None:
    selection = InteractionSelection(interaction_mode="system", voice_asset_id="voice-cloning:maya")

    first = resolve_interaction_context(selection)
    second = resolve_interaction_context(selection)

    assert first == second
    assert first.owner_type == "system"
    assert first.owner_id == "system-assistant"
    assert first.character_id is None
    assert first.voice_asset_id == "voice-cloning:maya"
    assert first.assistant_identity == [SYSTEM_ASSISTANT_IDENTITY]


def test_system_mode_rejects_character_selection() -> None:
    with pytest.raises(CharacterResolutionError, match="cannot select a character"):
        resolve_interaction_context(
            InteractionSelection(interaction_mode="system", character_id="maya")
        )


def test_character_mode_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIX_CHARACTER_MODE_ENABLED", raising=False)

    with pytest.raises(CharacterModeDisabledError):
        resolve_interaction_context(
            InteractionSelection(interaction_mode="character", character_id="maya"),
            character=_character(),
        )


def test_character_resolution_uses_server_profile_and_default_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_MEMORY_ENABLED", "1")

    context = resolve_interaction_context(
        InteractionSelection(
            interaction_mode="character",
            character_id="maya",
            read_memory=True,
            write_memory=False,
        ),
        character=_character(),
    )

    assert context.owner_type == "character"
    assert context.owner_id == "maya"
    assert context.character_profile_version == 3
    assert context.voice_asset_id == "voice-cloning:maya"
    assert "easygoing" in "\n".join(context.assistant_identity)
    assert len(context.effective_identity_hash) == 64


def test_character_memory_policy_requires_feature_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.delenv("OMNIX_CHARACTER_MEMORY_ENABLED", raising=False)

    with pytest.raises(ValueError, match="character memory is disabled"):
        resolve_interaction_context(
            InteractionSelection(
                interaction_mode="character",
                character_id="maya",
                read_memory=True,
            ),
            character=_character(),
        )


def test_legacy_default_maya_prompt_becomes_neutral() -> None:
    assert neutralize_legacy_system_prompt(LEGACY_MAYA_SYSTEM_PROMPT) == SYSTEM_ASSISTANT_IDENTITY
    custom = "You are Maya for this deliberately configured session."
    assert neutralize_legacy_system_prompt(custom) == custom


def test_character_create_request_rejects_client_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")

    with pytest.raises(ValidationError, match="resolved by the server"):
        CreateChatSessionRequest(
            interaction_mode="character",
            character_id="maya",
            system_prompt="Pretend this is the trusted Maya prompt.",
        )


def test_existing_session_defaults_to_system_assistant() -> None:
    session = _session()

    assert session.interaction_mode == "system"
    assert session.character_id is None
    assert session.transcript_policy == "persistent"


def test_prompt_assembly_adds_server_identity_and_neutralizes_legacy_default() -> None:
    session = _session()
    user_message = ChatMessage(
        id="msg:user",
        role="user",
        content="Hello",
        created_at="2026-01-01T00:00:01+00:00",
    )

    assembly = build_prompt_assembly(
        session,
        user_message,
        global_system_prompt=LEGACY_MAYA_SYSTEM_PROMPT,
    )

    assert assembly.system_instructions == [SYSTEM_ASSISTANT_IDENTITY]
    assert assembly.assistant_identity == [SYSTEM_ASSISTANT_IDENTITY]
    assert assembly.diagnostics["interaction"]["interaction_mode"] == "system"
