from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.characters import CharacterRepository, CreateCharacterRequest
from app.characters.avatar_models import UpsertCharacterAvatarPackRequest
from app.characters.avatar_repository import CharacterAvatarRepository
from app.characters.avatar_service import CharacterAvatarService
from app.characters.live2d_avatar import (
    CharacterLive2DAvatarService,
    register_character_live2d_avatar_routes,
)
from app.characters.service import CharacterService


def test_live2d_catalog_activation_serving_and_sprite_restore(tmp_path: Path) -> None:
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
    sprite_pack = avatar_service.upsert(
        "maya",
        UpsertCharacterAvatarPackRequest(
            base_asset_id="image:maya",
            mouth_frames={"closed": "image:maya"},
        ),
    )

    model_json = json.dumps(
        {
            "Version": 3,
            "FileReferences": {
                "Moc": "maya.moc3",
                "Textures": ["textures/texture_00.png"],
            },
        }
    ).encode()

    downloaded_urls: list[str] = []

    def download(url: str) -> bytes:
        downloaded_urls.append(url)
        if url.endswith(".model3.json"):
            return model_json
        if url.endswith("maya.moc3"):
            return b"MOC3"
        if url.endswith("texture_00.png"):
            return b"PNG"
        if url.endswith(".js"):
            return b"window.__live2d_test__ = true;"
        raise AssertionError(f"unexpected download: {url}")

    live2d_service = CharacterLive2DAvatarService(
        avatar_service_factory=lambda: avatar_service,
        asset_store_factory=lambda: assets,
        data_root=tmp_path / "live2d",
        download_bytes=download,
    )
    app = FastAPI()
    register_character_live2d_avatar_routes(app, service_factory=lambda: live2d_service)
    client = TestClient(app)

    catalog = client.get("/api/characters/maya/live2d-models")
    assert catalog.status_code == 200
    assert len(catalog.json()["models"]) == 10
    assert catalog.json()["runtime_installed"] is False

    rejected = client.post(
        "/api/characters/maya/live2d-avatar",
        json={"model_id": "open-llm-vtuber-mao-pro"},
    )
    assert rejected.status_code == 422

    activated = client.post(
        "/api/characters/maya/live2d-avatar",
        json={
            "model_id": "open-llm-vtuber-mao-pro",
            "accept_live2d_runtime_terms": True,
            "accept_model_terms": True,
        },
    )
    assert activated.status_code == 200
    payload = activated.json()
    assert payload["downloaded"] is True
    assert payload["avatar_pack"]["renderer"] == "live2d"
    assert payload["avatar_pack"]["render_mode"] == "viseme"
    rig_asset_id = payload["avatar_pack"]["rig_asset_id"]
    assert any("/live2d-models/mao_pro/runtime/mao_pro.model3.json" in url for url in downloaded_urls)

    installed_catalog = client.get("/api/characters/maya/live2d-models").json()
    assert installed_catalog["runtime_installed"] is True
    assert installed_catalog["models"][0]["installed"] is True
    assert installed_catalog["models"][0]["selected"] is True

    model_file = client.get(
        f"/api/character-live2d/assets/{rig_asset_id}/runtime/mao_pro.model3.json"
    )
    assert model_file.status_code == 200
    assert model_file.json()["Version"] == 3

    runtime_file = client.get("/api/character-live2d/runtime/pixi.min.js")
    assert runtime_file.status_code == 200

    restored = client.post("/api/characters/maya/live2d-avatar/disable")
    assert restored.status_code == 200
    restored_pack = restored.json()["avatar_pack"]
    assert restored_pack["renderer"] == "sprite"
    assert restored_pack["base_asset_id"] == sprite_pack.base_asset_id


def test_live2d_archive_catalog_entry_is_hash_pinned_and_extracts_runtime_only(
    tmp_path: Path,
) -> None:
    model_json = json.dumps(
        {
            "Version": 3,
            "FileReferences": {
                "Moc": "sample.moc3",
                "Textures": ["textures/texture_00.png"],
                "Motions": {"Idle": [{"File": "motions/idle.motion3.json"}]},
            },
        }
    ).encode()
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("sample/runtime/sample.model3.json", model_json)
        archive.writestr("sample/runtime/sample.moc3", b"MOC3")
        archive.writestr("sample/runtime/textures/texture_00.png", b"PNG")
        archive.writestr("sample/runtime/motions/idle.motion3.json", b"{}")
        archive.writestr("sample/source/large-authoring-file.cmo3", b"NOT INSTALLED")
    archive_bytes = archive_buffer.getvalue()
    archive_url = "https://example.com/sample.zip"

    def download(url: str) -> bytes:
        if url == archive_url:
            return archive_bytes
        if url.endswith(".js"):
            return b"window.__live2d_test__ = true;"
        raise AssertionError(f"unexpected download: {url}")

    assets = SharedAssetStore(tmp_path / "assets.json")
    service = CharacterLive2DAvatarService(
        asset_store_factory=lambda: assets,
        data_root=tmp_path / "live2d",
        download_bytes=download,
    )
    entry = {
        "id": "live2d-sample-test",
        "name": "Sample",
        "description": "Test model",
        "preview_url": "https://example.com/sample.png",
        "repository": "Live2D/Cubism Sample Data",
        "revision": f"sha256:{hashlib.sha256(archive_bytes).hexdigest()}",
        "entry_path": "live2d-models/sample/runtime/sample.model3.json",
        "source_url": "https://example.com/source",
        "model_license_url": "https://example.com/model-license",
        "runtime_license_url": "https://example.com/runtime-license",
        "license_summary": "Terms apply.",
        "mouth_parameter_ids": ["ParamMouthOpenY"],
        "mouth_form_parameter_ids": ["ParamMouthForm"],
        "archive_url": archive_url,
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "archive_entry_path": "sample/runtime/sample.model3.json",
    }

    asset, downloaded = service._ensure_model_asset(entry)

    assert downloaded is True
    assert Path(asset.storage_path).is_file()
    model_root = Path(asset.metadata["root_path"])
    assert (model_root / "runtime/sample.moc3").read_bytes() == b"MOC3"
    assert (model_root / "runtime/textures/texture_00.png").read_bytes() == b"PNG"
    assert not (model_root / "source/large-authoring-file.cmo3").exists()
