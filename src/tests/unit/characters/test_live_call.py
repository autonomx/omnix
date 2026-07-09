from __future__ import annotations

from pathlib import Path

from app.characters import CharacterRepository, CreateCharacterRequest, SetSessionInteractionRequest
from app.characters.live_call import normalize_speech_style, resolve_live_call_runtime
from app.chat import CreateChatSessionRequest, default_chat_store


def _configure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    CharacterRepository().create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be warm, relaxed, and lightly humorous.",
            default_greeting="Hey, good to hear from you.",
            default_voice_asset_id="voice-cloning:maya",
            speech_style={
                "speed": 0.94,
                "temperature": 0.52,
                "top_k": 18,
                "top_p": 0.82,
                "repetition_penalty": 1.05,
                "expressiveness": "relaxed",
                "default_emotion": "calm",
                "interruption_style": "patient",
            },
        )
    )


def test_character_live_call_runtime_resolves_profile_voice_and_delivery(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Maya call"))
    session = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(
            interaction_mode="character",
            character_id="maya",
            read_memory=False,
            write_memory=False,
        ),
    )
    assert session is not None

    runtime = resolve_live_call_runtime(session)

    assert runtime.interaction_mode == "character"
    assert runtime.character_id == "maya"
    assert runtime.display_name == "Maya"
    assert runtime.character_profile_version == 1
    assert runtime.voice_asset_id == "voice-cloning:maya"
    assert runtime.greeting == "Hey, good to hear from you."
    assert runtime.speech_style.speed == 0.94
    assert runtime.speech_style.temperature == 0.52
    assert runtime.speech_style.top_k == 18
    assert runtime.speech_style.top_p == 0.82
    assert runtime.speech_style.repetition_penalty == 1.05
    assert runtime.speech_style.expressiveness == "relaxed"
    assert runtime.speech_style.emotion == "calm"
    assert runtime.speech_style.interruption_style == "patient"
    assert runtime.preload.profile_loaded is True
    assert runtime.preload.voice_resolved is True
    assert runtime.preload.preload_ms >= 0


def test_voice_override_changes_renderer_without_changing_character_identity(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Voice override"))
    session = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(
            interaction_mode="character",
            character_id="maya",
            voice_asset_id="voice-cloning:alternate",
        ),
    )
    assert session is not None

    runtime = resolve_live_call_runtime(session)

    assert runtime.character_id == "maya"
    assert runtime.display_name == "Maya"
    assert runtime.voice_asset_id == "voice-cloning:alternate"
    assert runtime.character_profile_version == 1


def test_system_live_call_runtime_stays_identity_neutral(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    store = default_chat_store()
    session = store.create_session(
        CreateChatSessionRequest(
            title="System call",
            voice_asset_id="voice-cloning:maya",
        )
    )

    runtime = resolve_live_call_runtime(session)

    assert runtime.interaction_mode == "system"
    assert runtime.character_id is None
    assert runtime.display_name == "System Assistant"
    assert runtime.voice_asset_id == "voice-cloning:maya"
    assert runtime.greeting == ""
    assert runtime.preload.profile_loaded is False


def test_speech_style_is_bounded_and_deterministic() -> None:
    style = normalize_speech_style(
        {
            "speed": 99,
            "temperature": -2,
            "top_k": 500,
            "top_p": 9,
            "repetition_penalty": 0,
            "expressiveness": "x" * 200,
        }
    )

    assert style.speed == 2.0
    assert style.temperature == 0.1
    assert style.top_k == 100
    assert style.top_p == 1.0
    assert style.repetition_penalty == 0.5
    assert len(style.expressiveness) == 80
