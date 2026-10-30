"""Typed contracts for live-chat character avatar packs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AvatarRenderMode = Literal["audio_envelope", "viseme", "static"]
# "portrait": a talking-head video of ``base_asset_id`` (the live portrait service, FLOAT).
AvatarRenderer = Literal["sprite", "live2d", "rive", "portrait"]
# What a portrait pack shows when the portrait is not available (Rive is not drawn in live calls).
PortraitFallbackRenderer = Literal["sprite", "live2d", "orb"]
PortraitEmotion = Literal["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
AvatarMouthFrame = Literal["closed", "small", "medium", "wide"]


def validate_renderer_assets(renderer: str, fallback: str, *, base_asset_id: str | None, rig_asset_id: str | None,
                             mouth_frames: dict[str, str]) -> None:
    """A pack names what its renderer draws; a portrait pack also what its fallback draws."""
    sprite_ready = bool(base_asset_id or mouth_frames.get("closed"))
    if renderer == "sprite" and not sprite_ready:
        raise ValueError("sprite avatar pack requires base_asset_id or a closed mouth frame")
    if renderer == "portrait":
        if not base_asset_id:
            raise ValueError("portrait avatar pack requires base_asset_id (the portrait image)")
        if fallback == "sprite" and not sprite_ready:
            raise ValueError("a sprite fallback requires base_asset_id or a closed mouth frame")
        if fallback == "live2d" and not rig_asset_id:
            raise ValueError("a Live2D fallback requires rig_asset_id")
    elif renderer != "sprite" and not rig_asset_id:
        raise ValueError("rigged avatar pack requires rig_asset_id")


class CharacterAvatarPack(BaseModel):
    """Durable shared-image references for one Character Mode live avatar."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: str = Field(min_length=1, max_length=160)
    version: int = Field(default=1, ge=1)
    render_mode: AvatarRenderMode = "audio_envelope"
    renderer: AvatarRenderer = "sprite"
    rig_asset_id: str | None = Field(default=None, max_length=240)
    base_asset_id: str | None = Field(default=None, max_length=240)
    mouth_frames: dict[str, str] = Field(default_factory=dict)
    blink_frames: dict[str, str] = Field(default_factory=dict)
    expression_frames: dict[str, str] = Field(default_factory=dict)
    outfit_frames: dict[str, str] = Field(default_factory=dict)
    background_asset_ids: dict[str, str] = Field(default_factory=dict)
    active_outfit: str | None = Field(default=None, max_length=120)
    active_background: str | None = Field(default=None, max_length=120)
    mouth_anchor: dict[str, float] = Field(default_factory=dict)
    fallback_renderer: PortraitFallbackRenderer = "orb"
    portrait_emotion: PortraitEmotion = "neutral"
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def validate_renderable_pack(self) -> "CharacterAvatarPack":
        validate_renderer_assets(self.renderer, self.fallback_renderer, base_asset_id=self.base_asset_id,
                                 rig_asset_id=self.rig_asset_id, mouth_frames=self.mouth_frames)
        for key, value in {
            **self.mouth_frames,
            **self.blink_frames,
            **self.expression_frames,
            **self.outfit_frames,
            **self.background_asset_ids,
        }.items():
            if not str(key).strip() or not str(value).strip():
                raise ValueError("avatar pack frame keys and asset IDs must be non-empty")
        return self


class UpsertCharacterAvatarPackRequest(BaseModel):
    """Browser-authored asset selections; identity ownership stays server-side."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = Field(default=None, ge=1)
    render_mode: AvatarRenderMode = "audio_envelope"
    renderer: AvatarRenderer = "sprite"
    rig_asset_id: str | None = Field(default=None, max_length=240)
    base_asset_id: str | None = Field(default=None, max_length=240)
    mouth_frames: dict[str, str] = Field(default_factory=dict)
    blink_frames: dict[str, str] = Field(default_factory=dict)
    expression_frames: dict[str, str] = Field(default_factory=dict)
    outfit_frames: dict[str, str] = Field(default_factory=dict)
    background_asset_ids: dict[str, str] = Field(default_factory=dict)
    active_outfit: str | None = Field(default=None, max_length=120)
    active_background: str | None = Field(default=None, max_length=120)
    mouth_anchor: dict[str, float] = Field(default_factory=dict)
    fallback_renderer: PortraitFallbackRenderer = "orb"
    portrait_emotion: PortraitEmotion = "neutral"


class DeleteCharacterAvatarPackResponse(BaseModel):
    ok: bool = True
    character_id: str


__all__ = [
    "AvatarMouthFrame",
    "AvatarRenderMode",
    "AvatarRenderer",
    "CharacterAvatarPack",
    "DeleteCharacterAvatarPackResponse",
    "UpsertCharacterAvatarPackRequest",
]
