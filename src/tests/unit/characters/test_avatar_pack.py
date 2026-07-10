from __future__ import annotations

from pathlib import Path

import pytest

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.characters import CharacterRepository, CreateCharacterRequest, SetSessionInteractionRequest
from app.characters.avatar_models import UpsertCharacterAvatarPackRequest
from app.characters.avatar_repository import CharacterAvatarRepository
from app.characters.avatar_service import CharacterAvatarAssetError, CharacterAvatarService
from app.characters.live_call import resolve_live_call_runtime
from app.characters.service import CharacterService
from app.chat import CreateChatSessionRequest, default_chat_store


def _services(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OMNIX_CHARACTER_MODE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    manifest = tmp_path / "assets.json"
    assets = SharedAssetStore(manifest)
    for name in ("closed", "small", "medium", "wide"):
        image = tmp_path / f"maya-{name}.png"
        image.write_bytes(b"PNG")
        assets.upsert_asset(
            AssetRecord(
                id=f"image:maya-{name}",
                module="image-generation",
                type=AssetType.IMAGE,
                mime_type="image/png",
                storage_path=str(image),
                metadata={"immutable": True},
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
    character_repository = CharacterRepository(tmp_path / "characters.sqlite3")
    character_repository.create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be warm and conversational.",
            default_greeting="Hello from Maya.",
        )
    )
    character_service = CharacterService(
        character_repository,
        asset_store_factory=lambda: assets,
    )
    avatar_service = CharacterAvatarService(
        CharacterAvatarRepository(tmp_path / "characters.sqlite3"),
        character_service_factory=lambda: character_service,
        asset_store_factory=lambda: assets,
    )
    return character_service, avatar_service


def test_avatar_pack_round_trip_and_live_call_resolution(tmp_path: Path, monkeypatch) -> None:
    character_service, avatar_service = _services(tmp_path, monkeypatch)
    pack = avatar_service.upsert(
        "maya",
        UpsertCharacterAvatarPackRequest(
            mouth_frames={
                "closed": "image:maya-closed",
                "small": "image:maya-small",
                "medium": "image:maya-medium",
                "wide": "image:maya-wide",
            },
        ),
    )
    assert pack.version == 1
    assert pack.render_mode == "audio_envelope"
    assert avatar_service.get("maya").mouth_frames["wide"] == "image:maya-wide"

    store = default_chat_store()
    session = store.create_session(CreateChatSessionRequest(title="Maya avatar call"))
    session = store.set_session_interaction(
        session.id,
        SetSessionInteractionRequest(interaction_mode="character", character_id="maya"),
    )
    assert session is not None
    runtime = resolve_live_call_runtime(
        session,
        character_service_factory=lambda: character_service,
        avatar_service_factory=lambda: avatar_service,
    )
    assert runtime.avatar_pack is not None
    assert runtime.avatar_pack.mouth_frames["closed"] == "image:maya-closed"
    assert runtime.preload.avatar_pack_loaded is True


def test_avatar_pack_rejects_missing_or_non_image_assets(tmp_path: Path, monkeypatch) -> None:
    _, avatar_service = _services(tmp_path, monkeypatch)
    with pytest.raises(CharacterAvatarAssetError, match="not found"):
        avatar_service.upsert(
            "maya",
            UpsertCharacterAvatarPackRequest(base_asset_id="image:missing"),
        )
