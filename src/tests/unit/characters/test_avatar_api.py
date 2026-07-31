from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.characters import CharacterRepository, CreateCharacterRequest
from app.characters.avatar_api import register_character_avatar_routes
from app.characters.avatar_repository import CharacterAvatarRepository
from app.characters.avatar_service import CharacterAvatarService
from app.characters.service import CharacterService


def test_character_avatar_routes_round_trip(tmp_path: Path) -> None:
    image = tmp_path / "maya.png"
    image.write_bytes(b"PNG")
    assets = SharedAssetStore(tmp_path / "assets.json")
    assets.upsert_asset(
        AssetRecord(
            id="image:maya",
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type="image/png",
            storage_path=str(image),
            metadata={},
            created_at="2026-01-01T00:00:00+00:00",
        )
    )
    characters = CharacterRepository(tmp_path / "characters.sqlite3")
    characters.create(
        CreateCharacterRequest(
            id="maya",
            display_name="Maya",
            personality_prompt="Be warm and conversational.",
        )
    )
    character_service = CharacterService(characters, asset_store_factory=lambda: assets)
    avatar_service = CharacterAvatarService(
        CharacterAvatarRepository(tmp_path / "characters.sqlite3"),
        character_service_factory=lambda: character_service,
        asset_store_factory=lambda: assets,
    )
    app = FastAPI()
    register_character_avatar_routes(app, service_factory=lambda: avatar_service)
    client = TestClient(app)

    response = client.get("/api/characters/maya/avatar-pack/optional")
    assert response.status_code == 200
    assert response.json() is None

    response = client.put(
        "/api/characters/maya/avatar-pack",
        json={"base_asset_id": "image:maya", "mouth_frames": {"closed": "image:maya"}},
    )
    assert response.status_code == 200
    assert response.json()["version"] == 1

    response = client.get("/api/characters/maya/avatar-pack/optional")
    assert response.status_code == 200
    assert response.json()["mouth_frames"]["closed"] == "image:maya"

    response = client.get("/api/characters/maya/avatar-pack")
    assert response.status_code == 200
    assert response.json()["mouth_frames"]["closed"] == "image:maya"

    response = client.delete("/api/characters/maya/avatar-pack")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "character_id": "maya"}
