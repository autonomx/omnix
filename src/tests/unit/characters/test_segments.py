from __future__ import annotations

from pathlib import Path

from app.characters import CharacterRepository, CreateCharacterRequest, SetSessionInteractionRequest
from app.chat import ChatMessage, CreateChatSessionRequest, SendChatMessageRequest, default_chat_store


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


def test_identity_switch_closes_old_segment_and_filters_prompt_history(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Segments"))
    first_segment = session.active_segment_id
    assert first_segment
    session.messages.extend([
        ChatMessage(id="u1", role="user", content="We were discussing hiking plans.", created_at="2026-01-01T00:00:00Z", metadata={"segment_id": first_segment}),
        ChatMessage(id="a1", role="assistant", content="Old system assistant style response.", created_at="2026-01-01T00:00:01Z", metadata={"segment_id": first_segment}),
    ])
    store._save_sessions([session])

    switched = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(interaction_mode="character", character_id="maya", continue_topic=True),
    )
    assert switched is not None
    assert switched.active_segment_id != first_segment
    segments = CharacterRepository().segments(session.id)
    assert len(segments) == 2
    assert segments[0].ended_at is not None
    assert segments[1].carryover_summary == "User topics carried from the previous identity segment:\n- We were discussing hiking plans."

    current = ChatMessage(id="u2", role="user", content="Continue.", created_at="2026-01-01T00:00:02Z", metadata={"segment_id": switched.active_segment_id})
    assembly, _ = store.build_provider_prompt(switched, current)
    recent = [turn.content for turn in assembly.recent_messages]
    assert recent == ["Hey, good to hear from you."]
    assert "Old system assistant style response" not in "\n".join(recent)
    assert assembly.session_summary and "hiking plans" in assembly.session_summary


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


def test_voice_change_alone_does_not_split_context_segment(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Voice only"))
    updated = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(interaction_mode="system", voice_asset_id="voice-cloning:maya"),
    )
    assert updated is not None
    assert updated.active_segment_id == session.active_segment_id
    assert len(CharacterRepository().segments(session.id)) == 1
