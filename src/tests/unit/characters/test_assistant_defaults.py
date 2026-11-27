"""The System Assistant's first-run defaults: the shipped portrait and voice, never over the owner's own."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.assets import SharedAssetStore
from app.conversation.contracts import SYSTEM_ASSISTANT_ID
from app.platform.characters.assistant_defaults import AssistantDefaultsService, register_assistant_defaults_routes
from app.platform.characters.avatar_models import UpsertCharacterAvatarPackRequest
from app.platform.characters.avatar_repository import CharacterAvatarRepository
from app.platform.characters.avatar_service import CharacterAvatarService
from app.platform.image import reference_assets
from app.settings.access import load_settings
from app.settings.profile_repository import load_settings_profile


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(reference_assets, "image_reference_root", lambda: tmp_path / "references")
    portrait = tmp_path / "assistant" / "portrait.png"
    portrait.parent.mkdir()
    buffer = io.BytesIO()
    Image.new("RGB", (64, 80), (180, 120, 90)).save(buffer, format="PNG")
    portrait.write_bytes(buffer.getvalue())
    voices = tmp_path / "voice_clones"
    voices.mkdir()
    assets = SharedAssetStore(tmp_path / "assets.json")
    avatars = CharacterAvatarService(CharacterAvatarRepository(tmp_path / "characters.sqlite3"),
                                     asset_store_factory=lambda: assets)
    service = AssistantDefaultsService(avatar_service_factory=lambda: avatars, asset_store_factory=lambda: assets,
                                       portrait_path=lambda: portrait, voice_root=lambda: voices)
    app = FastAPI()
    register_assistant_defaults_routes(app.router, service_factory=lambda: service)
    return TestClient(app), avatars, assets, portrait, voices


def assistant_voice() -> str:
    return load_settings_profile(load_settings()).assistant.voice_id


def test_setup_gives_the_assistant_the_shipped_portrait_and_voice(setup) -> None:
    client, avatars, assets, _portrait, voices = setup
    assert client.get("/api/assistant-defaults").json() == {"portrait_available": True, "voice_id": "",
                                                            "has_avatar": False}
    (voices / "Maya.wav").write_bytes(b"RIFF")

    applied = client.post("/api/assistant-defaults").json()

    assert applied["applied"] is True and applied["voice_id"] == "Maya"
    pack = avatars.get(SYSTEM_ASSISTANT_ID)
    assert (pack.renderer, pack.render_mode, pack.fallback_renderer, pack.portrait_emotion) == (
        "portrait", "static", "sprite", "character")
    image = assets.get_asset(pack.base_asset_id)
    assert image is not None and Path(image.storage_path).is_file()
    assert client.get("/api/assistant-defaults").json()["has_avatar"] is True
    assert assistant_voice() == "Maya"


def test_a_voice_the_owner_chose_is_kept_and_a_missing_one_is_not_set(setup) -> None:
    client, _avatars, _assets, _portrait, voices = setup
    assert client.post("/api/assistant-defaults").json()["voice_id"] == ""  # this library has no Maya
    assert assistant_voice() == ""
    (voices / "Maya.wav").write_bytes(b"RIFF")
    from app.platform.characters.assistant_defaults import adopt_assistant_voice

    assert adopt_assistant_voice("Nova") == "Nova"
    assert client.post("/api/assistant-defaults").json()["voice_id"] == "Nova"
    assert assistant_voice() == "Nova"


def test_an_avatar_the_owner_chose_is_never_replaced(setup, tmp_path: Path) -> None:
    client, avatars, *_ = setup
    first = client.post("/api/assistant-defaults").json()["avatar_pack"]
    again = client.post("/api/assistant-defaults").json()
    assert again["applied"] is False and again["avatar_pack"]["version"] == first["version"]
    assert len(list((tmp_path / "references").glob("*.png"))) == 1  # the image is imported once
    avatars.delete(SYSTEM_ASSISTANT_ID)
    assert client.post("/api/assistant-defaults").json()["applied"] is True


def test_an_install_without_the_portrait_offers_nothing_and_refuses_to_apply(setup) -> None:
    client, avatars, _assets, portrait, _voices = setup
    portrait.unlink()
    assert client.get("/api/assistant-defaults").json()["portrait_available"] is False
    assert client.get("/api/assistant-defaults/portrait").status_code == 404
    assert client.post("/api/assistant-defaults").status_code == 422
    assert avatars.optional_get(SYSTEM_ASSISTANT_ID) is None


def test_the_portrait_preview_is_served(setup) -> None:
    client, *_rest = setup
    response = client.get("/api/assistant-defaults/portrait")
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"


def test_any_avatar_the_assistant_has_is_kept(setup) -> None:
    client, avatars, *_ = setup
    client.post("/api/assistant-defaults")
    pack = avatars.get(SYSTEM_ASSISTANT_ID)
    avatars.upsert(SYSTEM_ASSISTANT_ID, UpsertCharacterAvatarPackRequest(
        expected_version=pack.version, renderer="sprite", base_asset_id=pack.base_asset_id))
    assert client.post("/api/assistant-defaults").json()["avatar_pack"]["renderer"] == "sprite"
