from app.characters.interaction import (
    LEGACY_MAYA_SYSTEM_PROMPT,
    resolve_interaction_context,
)
from app.characters.models import CharacterProfileSnapshot, InteractionSelection
from app.chat import prompt_assembly as prompt_assembly_module
from app.chat.models import ChatMessage, ChatSession
from app.chat.prompt_rendering import render_prompt_assembly


PERSONALITY_PROMPT = """You are Jinx from Arcane: brilliant, chaotic, theatrical, and dangerous.
Stay in character. Never act like a generic personal assistant."""


def _resolved_jinx(monkeypatch):
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    character = CharacterProfileSnapshot(
        id="jinx",
        display_name="Jinx",
        personality_prompt=PERSONALITY_PROMPT,
        default_greeting="Now tell me why you're here.",
        default_voice_asset_id="voice-cloning:Jinx",
        identity_policy={},
        shared_memory_policy={},
        version=5,
        enabled=True,
    )
    selection = InteractionSelection(
        interaction_mode="character",
        character_id="jinx",
        voice_asset_id="voice-cloning:Jinx",
    )
    return resolve_interaction_context(selection, character=character)


def test_character_identity_contains_only_saved_personality_prompt(monkeypatch) -> None:
    resolved = _resolved_jinx(monkeypatch)

    assert resolved.assistant_identity == [PERSONALITY_PROMPT]
    combined = "\n".join(resolved.assistant_identity)
    assert "System Assistant" not in combined
    assert "You are Jinx, an AI character in Omnix" not in combined
    assert "Character identity policy" not in combined


def test_character_prompt_suppresses_all_competing_assistant_prompts(monkeypatch) -> None:
    resolved = _resolved_jinx(monkeypatch)
    current = ChatMessage(
        id="message-current",
        role="user",
        content="What should we do tonight?",
        created_at="2026-08-06T00:00:00+00:00",
    )
    session = ChatSession(
        id="chat:jinx-test",
        title="Jinx",
        interaction_mode="character",
        character_id="jinx",
        voice_asset_id="voice-cloning:Jinx",
        character_profile_version=5,
        effective_identity_hash=resolved.effective_identity_hash,
        messages=[
            ChatMessage(
                id="legacy-system",
                role="system",
                content=LEGACY_MAYA_SYSTEM_PROMPT,
                created_at="2026-08-06T00:00:00+00:00",
            ),
            current,
        ],
        created_at="2026-08-06T00:00:00+00:00",
        updated_at="2026-08-06T00:00:00+00:00",
    )
    monkeypatch.setattr(
        prompt_assembly_module,
        "resolve_system_session_identity",
        lambda _session: resolved,
    )

    assembly = prompt_assembly_module.build_prompt_assembly(
        session,
        current,
        global_system_prompt="You are a helpful personal assistant.",
        assistant_identity=["Injected generic assistant identity."],
    )
    rendered = render_prompt_assembly(assembly)

    assert assembly.system_instructions == []
    assert assembly.assistant_identity == [PERSONALITY_PROMPT]
    assert [
        message.content
        for message in rendered.messages
        if message.role == "system"
    ] == [PERSONALITY_PROMPT]
    assert assembly.diagnostics["character_personality_only"] is True
    assert assembly.diagnostics["global_system_prompt_suppressed"] is True
    assert assembly.diagnostics["session_system_prompt_count_suppressed"] == 1
    assert assembly.diagnostics["caller_identity_override_suppressed"] is True
