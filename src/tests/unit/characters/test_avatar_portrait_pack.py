"""The avatar pack's portrait renderer (live portrait roadmap, Phase 2): what a portrait pack must name."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.platform.characters.avatar_models import (
    CharacterAvatarPack,
    UpsertCharacterAvatarPackRequest,
    portrait_emotion_label,
)

STAMPS = {"created_at": "2026-10-30T00:00:00+00:00", "updated_at": "2026-10-30T00:00:00+00:00"}


def test_a_portrait_pack_names_its_image_and_defaults_to_the_orb_and_the_characters_emotion() -> None:
    pack = CharacterAvatarPack(character_id="maya", renderer="portrait", base_asset_id="image:maya", **STAMPS)
    assert pack.fallback_renderer == "orb" and pack.portrait_emotion == "character"
    with pytest.raises(ValidationError, match="portrait image"):
        CharacterAvatarPack(character_id="maya", renderer="portrait", **STAMPS)


@pytest.mark.parametrize(("fallback", "assets", "message"), [
    ("live2d", {}, "Live2D fallback requires rig_asset_id"),
    ("orb", {"rig_asset_id": "rig:maya"}, None),
    ("live2d", {"rig_asset_id": "rig:maya"}, None),
    ("sprite", {}, None),  # the portrait image doubles as the sprite's base
])
def test_a_portrait_packs_fallback_names_what_it_draws(fallback: str, assets: dict, message: str | None) -> None:
    def build() -> CharacterAvatarPack:
        return CharacterAvatarPack(character_id="maya", renderer="portrait", base_asset_id="image:maya",
                                   fallback_renderer=fallback, **assets, **STAMPS)

    if message is None:
        assert build().fallback_renderer == fallback
    else:
        with pytest.raises(ValidationError, match=message):
            build()


def test_the_fallback_cannot_be_another_portrait_or_rive() -> None:
    for fallback in ("portrait", "rive"):
        with pytest.raises(ValidationError):
            UpsertCharacterAvatarPackRequest(renderer="portrait", base_asset_id="image:maya", fallback_renderer=fallback)


def test_existing_packs_without_the_new_fields_still_load() -> None:
    stored = {"character_id": "maya", "version": 3, "renderer": "sprite", "base_asset_id": "image:maya", **STAMPS}
    pack = CharacterAvatarPack.model_validate(stored)
    assert pack.fallback_renderer == "orb" and pack.portrait_emotion == "character"
    with pytest.raises(ValidationError, match="rig_asset_id"):
        CharacterAvatarPack(character_id="maya", renderer="live2d", **STAMPS)


def test_the_portrait_follows_the_characters_speech_emotion_unless_the_pack_names_one() -> None:
    pack = CharacterAvatarPack(character_id="maya", renderer="portrait", base_asset_id="image:maya", **STAMPS)
    assert portrait_emotion_label(pack, "Happy") == "happy"
    assert portrait_emotion_label(pack, "wistful") == "neutral"  # not one of FLOAT's seven labels
    assert portrait_emotion_label(pack, None) == "neutral"
    sad = pack.model_copy(update={"portrait_emotion": "sad"})
    assert portrait_emotion_label(sad, "happy") == "sad"


class _Store:
    def __init__(self, images: set[str]) -> None:
        self.images = images

    def get_asset(self, asset_id: str):
        from types import SimpleNamespace

        from app.assets import AssetType

        return SimpleNamespace(id=asset_id, type=AssetType.IMAGE) if asset_id in self.images else None


def _service(monkeypatch, released: list[str]):
    from app.platform.characters import avatar_service
    from app.platform.characters.avatar_repository import CharacterAvatarRepository

    class Observer:
        def on_portrait_released(self, asset_id: str) -> None:
            released.append(asset_id)

    monkeypatch.setattr(avatar_service, "implementations", lambda port: (Observer(),))
    monkeypatch.setattr(avatar_service, "_require_file", lambda asset, label: None)
    repository = CharacterAvatarRepository(db_path=f"memory-portrait-{id(released)}")
    service = avatar_service.CharacterAvatarService(
        repository, character_service_factory=lambda: type("Characters", (), {"get": lambda *a, **k: None})(),
        asset_store_factory=lambda: _Store({"image:a", "image:b"}))
    return service


def test_a_portrait_image_no_pack_shows_any_more_is_released_once(monkeypatch) -> None:
    released: list[str] = []
    service = _service(monkeypatch, released)
    portrait = UpsertCharacterAvatarPackRequest(renderer="portrait", base_asset_id="image:a")
    service.upsert("maya", portrait)
    service.upsert("lena", portrait)
    service.upsert("maya", UpsertCharacterAvatarPackRequest(renderer="portrait", base_asset_id="image:b"))
    assert released == []  # lena's portrait still shows image:a
    service.delete("lena")
    assert released == ["image:a"]
    service.upsert("maya", UpsertCharacterAvatarPackRequest(renderer="sprite", base_asset_id="image:b"))
    assert released == ["image:a", "image:b"]
