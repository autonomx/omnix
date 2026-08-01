from __future__ import annotations

import json
from pathlib import Path

from app.assets import (
    AssetListResponse,
    AssetRecord,
    AssetType,
    SharedAssetStore,
    canonical_voice_clones,
)
from app.characters import (
    CharacterRepository,
    CreateCharacterRequest,
    SetSessionInteractionRequest,
    UpdateCharacterRequest,
)
from app.characters.live_call import normalize_speech_style, resolve_live_call_runtime
from app.characters.service import CharacterService
from app.characters.voice_consent import (
    UpdateVoiceProfileGovernanceRequest,
    VoiceProfileGovernanceService,
)
from app.chat import CreateChatSessionRequest, default_chat_store


class _EmptyAssetStore:
    def list_assets(self) -> AssetListResponse:
        return AssetListResponse(assets=[])


def _configure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    canonical_resources = tmp_path / "canonical-resources"
    (canonical_resources / "voice_clones").mkdir(parents=True)
    monkeypatch.setattr(
        canonical_voice_clones,
        "resources_root",
        lambda: canonical_resources,
    )
    manifest = tmp_path / "assets.json"
    assets = SharedAssetStore(manifest)
    for voice_id in ("maya", "alternate"):
        audio = tmp_path / f"{voice_id}.wav"
        audio.write_bytes(f"RIFF-{voice_id}".encode())
        speaker_id = voice_id.title()
        assets.upsert_asset(
            AssetRecord(
                id=f"voice-cloning:{voice_id}",
                owner_id="user:local",
                module="voice-cloning",
                type=AssetType.VOICE_PROFILE,
                mime_type="audio/wav",
                storage_path=str(audio),
                metadata={
                    "profile_name": speaker_id,
                    "voice_id": speaker_id,
                    "voice_clone_id": speaker_id,
                    "speaker": speaker_id,
                },
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
        VoiceProfileGovernanceService(asset_store_factory=lambda: assets).update(
            f"voice-cloning:{voice_id}",
            UpdateVoiceProfileGovernanceRequest(
                subject_owner=f"{voice_id} voice subject",
                source_type="test_recording",
                source_reference=f"test:{voice_id}",
                creator_id="user:local",
                consent_status="granted",
                allowed_uses=["character", "live_call"],
                deletion_state="active",
            ),
        )
    monkeypatch.setenv("OMNIX_ASSETS_MANIFEST_PATH", str(manifest))
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


def _configure_lowercase_canonical_maya(tmp_path: Path, monkeypatch) -> CharacterService:
    canonical_resources = tmp_path / "lowercase-canonical"
    clone_root = canonical_resources / "voice_clones"
    clone_root.mkdir(parents=True)
    (clone_root / "maya.wav").write_bytes(b"RIFF-maya")
    (clone_root / "voice_clones.json").write_text(
        json.dumps(
            {
                "Maya": {
                    "profile_name": "Maya",
                    "voice_id": "Maya",
                    "voice_clone_id": "Maya",
                    "speaker": "Maya",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        canonical_voice_clones,
        "resources_root",
        lambda: canonical_resources,
    )
    return CharacterService(
        asset_store_factory=lambda: _EmptyAssetStore(),  # type: ignore[arg-type]
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
    assert runtime.voice_speaker_id == "Maya"
    assert runtime.greeting == ""
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
    assert runtime.preload.voice_error is None
    assert runtime.preload.preload_ms >= 0


def test_character_default_voice_overrides_stale_session_voice_for_live_call(tmp_path: Path, monkeypatch) -> None:
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
    assert runtime.voice_asset_id == "voice-cloning:maya"
    assert runtime.voice_speaker_id == "Maya"
    assert runtime.character_profile_version == 1


def test_character_service_canonicalizes_legacy_voice_asset_casing(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    service = _configure_lowercase_canonical_maya(tmp_path, monkeypatch)
    current = service.get("maya")

    updated = service.update(
        "maya",
        UpdateCharacterRequest(
            expected_version=current.active_version,
            default_voice_asset_id="voice-cloning:Maya",
        ),
    )

    assert updated.default_voice_asset_id == "voice-cloning:maya"


def test_live_call_runtime_recovers_legacy_voice_asset_casing(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    service = _configure_lowercase_canonical_maya(tmp_path, monkeypatch)
    repository = CharacterRepository()
    current = repository.get("maya")
    assert current is not None
    repository.update(
        "maya",
        UpdateCharacterRequest(
            expected_version=current.active_version,
            default_voice_asset_id="voice-cloning:Maya",
        ),
    )
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Legacy Maya casing"))
    session = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(
            interaction_mode="character",
            character_id="maya",
        ),
    )
    assert session is not None

    runtime = resolve_live_call_runtime(
        session,
        character_service_factory=lambda: service,
    )

    assert runtime.voice_asset_id == "voice-cloning:maya"
    assert runtime.voice_speaker_id == "Maya"
    assert runtime.preload.voice_resolved is True
    assert runtime.preload.voice_error is None


def test_live_call_runtime_reads_canonical_library_when_store_is_empty(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    canonical_resources = tmp_path / "canonical-only"
    clone_root = canonical_resources / "voice_clones"
    clone_root.mkdir(parents=True)
    (clone_root / "Jinx.wav").write_bytes(b"RIFF-jinx")
    (clone_root / "voice_clones.json").write_text(
        json.dumps(
            {
                "Jinx": {
                    "profile_name": "Jinx",
                    "voice_id": "Jinx",
                    "voice_clone_id": "Jinx",
                    "speaker": "Jinx",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        canonical_voice_clones,
        "resources_root",
        lambda: canonical_resources,
    )
    CharacterRepository().create(
        CreateCharacterRequest(
            id="jinx",
            display_name="Jinx",
            personality_prompt="Be volatile and energetic.",
            default_greeting="Hey.",
            default_voice_asset_id="voice-cloning:Jinx",
        )
    )
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Canonical Jinx"))
    session = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(
            interaction_mode="character",
            character_id="jinx",
        ),
    )
    assert session is not None
    service = CharacterService(
        asset_store_factory=lambda: _EmptyAssetStore(),  # type: ignore[arg-type]
    )

    runtime = resolve_live_call_runtime(
        session,
        character_service_factory=lambda: service,
    )

    assert runtime.voice_asset_id == "voice-cloning:Jinx"
    assert runtime.voice_speaker_id == "Jinx"
    assert runtime.preload.voice_resolved is True
    assert runtime.preload.voice_error is None


def test_character_runtime_keeps_identity_when_linked_voice_is_missing(tmp_path: Path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    service = CharacterService(
        asset_store_factory=lambda: _EmptyAssetStore(),  # type: ignore[arg-type]
    )
    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Maya without voice"))
    session = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(
            interaction_mode="character",
            character_id="maya",
        ),
    )
    assert session is not None

    runtime = resolve_live_call_runtime(
        session,
        character_service_factory=lambda: service,
    )

    assert runtime.interaction_mode == "character"
    assert runtime.character_id == "maya"
    assert runtime.display_name == "Maya"
    assert runtime.voice_asset_id is None
    assert runtime.voice_speaker_id is None
    assert runtime.preload.profile_loaded is True
    assert runtime.preload.voice_resolved is False
    assert runtime.preload.voice_error is not None
    assert "voice asset not found" in runtime.preload.voice_error


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
    assert runtime.voice_speaker_id == "Maya"
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
