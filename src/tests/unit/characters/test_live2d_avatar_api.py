from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assets import AssetRecord, AssetType, SharedAssetStore
from app.platform.characters import CharacterRepository, CreateCharacterRequest
from app.platform.characters.avatar_models import UpsertCharacterAvatarPackRequest
from app.platform.characters.avatar_repository import CharacterAvatarRepository
from app.platform.characters.avatar_service import CharacterAvatarService
from app.platform.characters.live2d_avatar import (
    CharacterLive2DAvatarService,
    register_character_live2d_avatar_routes,
)
from app.platform.characters.service import CharacterService

import pytest

from app.platform.characters import live2d_avatar

FAKE_RUNTIME = b"window.__live2d_test__ = true;"


@pytest.fixture(autouse=True)
def _pinned_fake_runtime(monkeypatch):
    """The tests serve a stand-in runtime; it is pinned the way the real files are."""
    digest = hashlib.sha256(FAKE_RUNTIME).hexdigest()
    monkeypatch.setattr(live2d_avatar, "_RUNTIME_SHA256", {name: digest for name in live2d_avatar._RUNTIME_FILES})


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
            return FAKE_RUNTIME
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
            return FAKE_RUNTIME
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


def test_a_runtime_file_that_changed_at_its_source_is_refused(tmp_path: Path) -> None:
    service = CharacterLive2DAvatarService(asset_store_factory=lambda: SharedAssetStore(tmp_path / "assets.json"),
                                           data_root=tmp_path / "live2d", download_bytes=lambda url: b"other code")
    with pytest.raises(ValueError, match="has changed at its source"):
        service._ensure_runtime()
    assert not service.runtime_installed()


def test_an_earlier_unpinned_runtime_download_is_replaced(tmp_path: Path) -> None:
    old = tmp_path / "live2d" / "runtime" / "live2dcubismcore.min.js"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"a third-party copy")
    service = CharacterLive2DAvatarService(asset_store_factory=lambda: SharedAssetStore(tmp_path / "assets.json"),
                                           data_root=tmp_path / "live2d", download_bytes=lambda url: FAKE_RUNTIME)
    service._ensure_runtime()
    assert old.read_bytes() == FAKE_RUNTIME and service.runtime_installed()


def test_cubism_core_comes_from_live2d_itself() -> None:
    assert live2d_avatar._RUNTIME_FILES["live2dcubismcore.min.js"].startswith("https://cubism.live2d.com/")


def test_avatars_download_and_remove_from_the_library(tmp_path: Path) -> None:
    """The setup screen and Settings, Models download avatars without a character; removal spares those in use."""
    assets = SharedAssetStore(tmp_path / "assets.json")
    model_json = json.dumps({"Version": 3, "FileReferences": {"Moc": "m.moc3"}}).encode()

    def download(url: str) -> bytes:
        if url.endswith(".js"):
            return FAKE_RUNTIME
        if url.endswith(".model3.json"):
            return model_json
        return b"MOC3"

    characters = CharacterRepository(tmp_path / "characters.sqlite3")
    characters.create(CreateCharacterRequest(id="maya", display_name="Maya", personality_prompt="Be warm."))
    character_service = CharacterService(characters, asset_store_factory=lambda: assets)
    avatar_service = CharacterAvatarService(CharacterAvatarRepository(tmp_path / "characters.sqlite3"),
                                            character_service_factory=lambda: character_service,
                                            asset_store_factory=lambda: assets)
    service = CharacterLive2DAvatarService(avatar_service_factory=lambda: avatar_service,
                                           asset_store_factory=lambda: assets, data_root=tmp_path / "live2d",
                                           download_bytes=download)
    app = FastAPI()
    register_character_live2d_avatar_routes(app, service_factory=lambda: service)
    client = TestClient(app)
    model_id = "open-llm-vtuber-shizuku"

    library = client.get("/api/character-live2d/models").json()
    assert not library["runtime_installed"] and not any(item["installed"] for item in library["models"])
    assert client.post(f"/api/character-live2d/models/{model_id}", json={}).status_code == 422  # terms first
    installed = client.post(f"/api/character-live2d/models/{model_id}", json={
        "accept_live2d_runtime_terms": True, "accept_model_terms": True}).json()
    assert installed["runtime_installed"]
    assert [item["id"] for item in installed["models"] if item["installed"]] == [model_id]

    # A character using it keeps it; once it uses another avatar, the download can go.
    service.characters_using = lambda requested: ["Maya"]
    refused = client.delete(f"/api/character-live2d/models/{model_id}")
    assert refused.status_code == 409 and "avatar of Maya" in refused.json()["detail"]
    service.characters_using = lambda requested: []
    removed = client.delete(f"/api/character-live2d/models/{model_id}").json()
    assert not any(item["installed"] for item in removed["models"])
    assert not (tmp_path / "live2d" / "models" / model_id).exists()


def test_the_library_routes_declare_their_permissions() -> None:
    from app.security.permissions import declared_permission

    app = FastAPI()
    register_character_live2d_avatar_routes(app)
    routes = {(next(iter(route.methods)), route.path): route for route in app.routes if hasattr(route, "methods")}
    assert declared_permission(routes[("POST", "/api/character-live2d/models/{model_id}")]) == "models:admin"
    assert declared_permission(routes[("DELETE", "/api/character-live2d/models/{model_id}")]) == "models:admin"
    assert declared_permission(routes[("GET", "/api/character-live2d/models")]) == "settings:read"


def test_previews_come_through_omnix_from_their_catalog_address(tmp_path: Path) -> None:
    """The app's content security policy allows only its own images, so the preview is fetched and served."""
    fetched: list[str] = []

    def download(url: str) -> bytes:
        fetched.append(url)
        return b"\xff\xd8\xff\xe0 a jpeg" if "haru" in url else b"<html>not an image</html>"

    service = CharacterLive2DAvatarService(asset_store_factory=lambda: SharedAssetStore(tmp_path / "assets.json"),
                                           data_root=tmp_path / "live2d", download_bytes=download)
    app = FastAPI()
    register_character_live2d_avatar_routes(app, service_factory=lambda: service)
    client = TestClient(app)
    library = client.get("/api/character-live2d/models").json()
    haru = next(item for item in library["models"] if item["id"] == "live2d-sample-haru")
    assert haru["preview_path"] == "/api/character-live2d/previews/live2d-sample-haru"
    preview = client.get(haru["preview_path"])
    assert preview.status_code == 200 and preview.content.startswith(b"\xff\xd8")
    client.get(haru["preview_path"])
    assert fetched == [haru["preview_url"]]  # fetched once, then served from disk
    assert client.get("/api/character-live2d/previews/open-llm-vtuber-shizuku").status_code == 404  # not an image
    assert client.get("/api/character-live2d/previews/unknown").status_code == 404
