from __future__ import annotations

from app.characters.interaction import (
    LEGACY_MAYA_SYSTEM_PROMPT,
    resolve_interaction_context,
)
from app.characters.models import CharacterProfileSnapshot, InteractionSelection
from app.chat import prompt_assembly as prompt_assembly_module
from app.chat.models import ChatMessage, ChatSession
from app.chat.prompt_assembly import build_prompt_assembly
from app.chat.prompt_rendering import render_prompt_assembly
from app.gateway.live_chat_prompt_window import _build_prompt_assembly_with_window

_NOW = "2026-08-04T00:00:00+00:00"
_CHARACTER_PERSONALITY = """You are Jinx from Arcane: brilliant, chaotic, theatrical, and dangerous.
Stay in character. Never act like a generic personal assistant."""


def _message(index: int, *, segment_id: str = "segment:main") -> ChatMessage:
    return ChatMessage(
        id=f"msg:{index}",
        role="user" if index % 2 == 0 else "assistant",
        content=f"history detail {index}",
        created_at=_NOW,
        metadata={"segment_id": segment_id},
    )


def _session(
    messages: list[ChatMessage],
    *,
    active_segment_id: str | None = None,
    transcript_policy: str = "persistent",
) -> ChatSession:
    return ChatSession(
        id="chat:prompt-window",
        title="Prompt window test",
        active_segment_id=active_segment_id,
        transcript_policy=transcript_policy,
        messages=messages,
        message_count=len(messages),
        created_at=_NOW,
        updated_at=_NOW,
    )


def _build(
    session: ChatSession,
    current: ChatMessage,
    *,
    session_summary: str | None = None,
):
    return _build_prompt_assembly_with_window(
        build_prompt_assembly,
        session,
        current,
        global_system_prompt="System instructions",
        context_items=[],
        approved_memory=[],
        retrieved_history=[],
        session_summary=session_summary,
        recent_message_limit=None,
    )


def _resolved_character(monkeypatch):
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    character = CharacterProfileSnapshot(
        id="jinx",
        display_name="Jinx",
        personality_prompt=_CHARACTER_PERSONALITY,
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


def test_long_chat_uses_summary_plus_latest_twenty_four(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_CHAT_PROMPT_WINDOW_ENABLED", raising=False)
    monkeypatch.delenv("OMNIX_CHAT_PROMPT_RECENT_MESSAGE_LIMIT", raising=False)
    history = [_message(index) for index in range(60)]
    current = ChatMessage(
        id="msg:current",
        role="user",
        content="current request",
        created_at=_NOW,
        metadata={"segment_id": "segment:main"},
    )
    session = _session([*history, current])

    assembly = _build(session, current)

    assert len(assembly.recent_messages) == 24
    assert assembly.recent_messages[0].message_id == "msg:36"
    assert assembly.recent_messages[-1].message_id == "msg:59"
    assert assembly.session_summary is not None
    assert "history detail 0" in assembly.session_summary
    assert "history detail 35" in assembly.session_summary
    assert "history detail 36" not in assembly.session_summary
    assert assembly.diagnostics["prompt_window"] == {
        "enabled": True,
        "recent_message_limit": 24,
        "eligible_message_count": 60,
        "recent_message_count": 24,
        "summarized_message_count": 36,
        "bounded": True,
        "summary_source": "ephemeral_exact",
        "summary_through_message_id": "msg:35",
        "persisted_summary_supplied": False,
        "persisted_summary_reused": False,
        "summary_error_type": None,
    }


def test_exact_persisted_summary_is_reused_but_stale_summary_is_replaced(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OMNIX_CHAT_PROMPT_WINDOW_ENABLED", raising=False)
    history = [_message(index) for index in range(40)]
    current = ChatMessage(
        id="msg:current",
        role="user",
        content="current request",
        created_at=_NOW,
        metadata={"segment_id": "segment:main"},
    )
    session = _session([*history, current])
    fresh = _build(session, current)
    assert fresh.session_summary is not None

    reused = _build(session, current, session_summary=fresh.session_summary)
    stale = _build(session, current, session_summary="stale summary")

    assert reused.session_summary == fresh.session_summary
    assert reused.diagnostics["prompt_window"]["summary_source"] == "persisted_exact"
    assert reused.diagnostics["prompt_window"]["persisted_summary_reused"] is True
    assert stale.session_summary == fresh.session_summary
    assert stale.session_summary != "stale summary"
    assert stale.diagnostics["prompt_window"]["summary_source"] == "ephemeral_exact"
    assert stale.diagnostics["prompt_window"]["persisted_summary_reused"] is False


def test_prompt_window_only_uses_the_active_identity_segment(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_CHAT_PROMPT_WINDOW_ENABLED", raising=False)
    old = [_message(index, segment_id="segment:old") for index in range(50)]
    active = [
        _message(index + 50, segment_id="segment:new")
        for index in range(6)
    ]
    current = ChatMessage(
        id="msg:current",
        role="user",
        content="current request",
        created_at=_NOW,
        metadata={"segment_id": "segment:new"},
    )
    session = _session(
        [*old, *active, current],
        active_segment_id="segment:new",
    )

    assembly = _build(session, current)

    assert [message.message_id for message in assembly.recent_messages] == [
        f"msg:{index}" for index in range(50, 56)
    ]
    assert assembly.session_summary is None
    assert assembly.diagnostics["prompt_window"]["eligible_message_count"] == 6
    assert assembly.diagnostics["prompt_window"]["summary_source"] == "not_needed"


def test_private_chat_is_bounded_without_creating_summary(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_CHAT_PROMPT_WINDOW_ENABLED", raising=False)
    history = [_message(index) for index in range(40)]
    current = ChatMessage(
        id="msg:current",
        role="user",
        content="current request",
        created_at=_NOW,
        metadata={"segment_id": "segment:main"},
    )
    session = _session([*history, current], transcript_policy="temporary")

    assembly = _build(session, current)

    assert len(assembly.recent_messages) == 24
    assert assembly.session_summary is None
    assert (
        assembly.diagnostics["prompt_window"]["summary_source"]
        == "omitted_by_retention_policy"
    )


def test_prompt_window_limit_is_configurable_and_can_be_disabled(monkeypatch) -> None:
    history = [_message(index) for index in range(30)]
    current = ChatMessage(
        id="msg:current",
        role="user",
        content="current request",
        created_at=_NOW,
        metadata={"segment_id": "segment:main"},
    )
    session = _session([*history, current])

    monkeypatch.setenv("OMNIX_CHAT_PROMPT_RECENT_MESSAGE_LIMIT", "10")
    bounded = _build(session, current)
    assert len(bounded.recent_messages) == 10
    assert bounded.diagnostics["prompt_window"]["summarized_message_count"] == 20

    monkeypatch.setenv("OMNIX_CHAT_PROMPT_WINDOW_ENABLED", "0")
    full = _build(session, current, session_summary="legacy summary")
    assert len(full.recent_messages) == 30
    assert full.session_summary == "legacy summary"
    assert full.diagnostics["prompt_window"] == {
        "enabled": False,
        "reason": "disabled_by_configuration",
        "eligible_message_count": 30,
    }


def test_character_identity_is_only_the_saved_personality_prompt(monkeypatch) -> None:
    resolved = _resolved_character(monkeypatch)

    assert resolved.assistant_identity == [_CHARACTER_PERSONALITY]
    combined = "\n".join(resolved.assistant_identity)
    assert "System Assistant" not in combined
    assert "You are Jinx, an AI character in Omnix" not in combined
    assert "Character identity policy" not in combined


def test_character_prompt_suppresses_competing_assistant_prompts(monkeypatch) -> None:
    resolved = _resolved_character(monkeypatch)
    current = ChatMessage(
        id="message-current",
        role="user",
        content="What should we do tonight?",
        created_at=_NOW,
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
                created_at=_NOW,
            ),
            current,
        ],
        created_at=_NOW,
        updated_at=_NOW,
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
    assert assembly.assistant_identity == [_CHARACTER_PERSONALITY]
    assert [
        message.content
        for message in rendered.messages
        if message.role == "system"
    ] == [_CHARACTER_PERSONALITY]
    assert assembly.diagnostics["character_personality_only"] is True
    assert assembly.diagnostics["global_system_prompt_suppressed"] is True
    assert assembly.diagnostics["session_system_prompt_count_suppressed"] == 1
    assert assembly.diagnostics["caller_identity_override_suppressed"] is True
