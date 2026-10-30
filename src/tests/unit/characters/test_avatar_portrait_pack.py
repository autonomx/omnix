"""The avatar pack's portrait renderer (live portrait roadmap, Phase 2): what a portrait pack must name."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.platform.characters.avatar_models import CharacterAvatarPack, UpsertCharacterAvatarPackRequest

STAMPS = {"created_at": "2026-10-30T00:00:00+00:00", "updated_at": "2026-10-30T00:00:00+00:00"}


def test_a_portrait_pack_names_its_image_and_defaults_to_the_orb_and_a_neutral_face() -> None:
    pack = CharacterAvatarPack(character_id="maya", renderer="portrait", base_asset_id="image:maya", **STAMPS)
    assert pack.fallback_renderer == "orb" and pack.portrait_emotion == "neutral"
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
    assert pack.fallback_renderer == "orb" and pack.portrait_emotion == "neutral"
    with pytest.raises(ValidationError, match="rig_asset_id"):
        CharacterAvatarPack(character_id="maya", renderer="live2d", **STAMPS)
