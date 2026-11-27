"""The System Assistant's first-run defaults: a live portrait and the Maya voice (desktop setup).

The desktop installer ships both (``resources/assistant``; the voice is staged into the voice library). Setup offers
them as one choice. Neither replaces the owner's own: the portrait becomes the assistant's avatar pack only while it
has none, and the voice becomes the assistant's voice (its settings profile) only while none is chosen.
"""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.assets import default_asset_store
from app.assets.canonical_voice_clones import canonical_voice_clone_root
from app.assets.protocol import AssetStore
from app.conversation.contracts import SYSTEM_ASSISTANT_ID
from app.runtime.paths import resources_root

from .avatar_models import CharacterAvatarPack, UpsertCharacterAvatarPackRequest
from .avatar_service import CharacterAvatarAssetError, CharacterAvatarService, default_character_avatar_service

ASSISTANT_VOICE_ID = "Maya"


def assistant_portrait_path() -> Path:
    return resources_root() / "assistant" / "portrait.png"


def adopt_assistant_voice(voice_id: str) -> str:
    """Make ``voice_id`` the assistant's voice unless the owner chose one; return the assistant's voice."""
    from app.settings.access import load_settings, save_settings
    from app.settings.profile_repository import load_settings_profile, save_settings_profile

    settings = load_settings()
    chosen = load_settings_profile(settings).assistant.voice_id
    if chosen:
        return chosen
    before = deepcopy(settings)
    save_settings_profile(settings, {"assistant": {"voiceId": voice_id}})
    save_settings({key: value for key, value in settings.items() if before.get(key) != value})
    return voice_id


class AssistantDefaults(BaseModel):
    """What setup can offer the assistant, and whether it already has an avatar of its own."""

    portrait_available: bool
    voice_id: str  # empty when the voice library lacks it
    has_avatar: bool


class AssistantDefaultsApplied(BaseModel):
    applied: bool  # False: the assistant already had an avatar, left as it was
    avatar_pack: CharacterAvatarPack
    voice_id: str  # the assistant's voice now: the shipped one, the owner's own, or empty


class AssistantDefaultsService:
    def __init__(
        self,
        *,
        avatar_service_factory: Callable[[], CharacterAvatarService] = default_character_avatar_service,
        asset_store_factory: Callable[[], AssetStore] = default_asset_store,
        portrait_path: Callable[[], Path] = assistant_portrait_path,
        voice_root: Callable[[], Path] = canonical_voice_clone_root,
        adopt_voice: Callable[[str], str] = adopt_assistant_voice,
    ) -> None:
        self.avatar_service_factory = avatar_service_factory
        self.asset_store_factory = asset_store_factory
        self.portrait_path = portrait_path
        self.voice_root = voice_root
        self.adopt_voice = adopt_voice

    def voice_id(self) -> str:
        return ASSISTANT_VOICE_ID if (self.voice_root() / f"{ASSISTANT_VOICE_ID}.wav").is_file() else ""

    def status(self) -> AssistantDefaults:
        pack = self.avatar_service_factory().optional_get(SYSTEM_ASSISTANT_ID)
        return AssistantDefaults(portrait_available=self.portrait_path().is_file(), voice_id=self.voice_id(),
                                 has_avatar=pack is not None)

    def apply(self) -> AssistantDefaultsApplied:
        """Give the assistant the shipped portrait and voice where it has none of its own."""
        avatars = self.avatar_service_factory()
        pack = avatars.optional_get(SYSTEM_ASSISTANT_ID)
        applied = pack is None
        if pack is None:
            source = self.portrait_path()
            if not source.is_file():
                raise CharacterAvatarAssetError("this install has no assistant portrait")
            from app.platform.image.contracts import save_image_reference_upload

            image = save_image_reference_upload(source.read_bytes(), filename="System Assistant portrait.png",
                                                mime_type="image/png", store=self.asset_store_factory())
            pack = avatars.upsert(SYSTEM_ASSISTANT_ID, UpsertCharacterAvatarPackRequest(
                render_mode="static", renderer="portrait", base_asset_id=image.id,
                fallback_renderer="sprite", portrait_emotion="character",
            ))
        shipped = self.voice_id()
        return AssistantDefaultsApplied(applied=applied, avatar_pack=pack,
                                        voice_id=self.adopt_voice(shipped) if shipped else "")


def register_assistant_defaults_routes(
    router: APIRouter,
    *,
    service_factory: Callable[[], AssistantDefaultsService] = AssistantDefaultsService,
) -> None:
    @router.get("/api/assistant-defaults", response_model=AssistantDefaults, tags=["characters"])
    def assistant_defaults() -> AssistantDefaults:
        return service_factory().status()

    @router.get("/api/assistant-defaults/portrait", response_model=None, response_class=FileResponse,
                tags=["characters"])
    def assistant_default_portrait() -> FileResponse:
        path = service_factory().portrait_path()
        if not path.is_file():
            raise HTTPException(status_code=404, detail="assistant_portrait_not_installed")
        return FileResponse(path, media_type="image/png")

    @router.post("/api/assistant-defaults", response_model=AssistantDefaultsApplied, tags=["characters"])
    def apply_assistant_defaults() -> AssistantDefaultsApplied:
        try:
            return service_factory().apply()
        except CharacterAvatarAssetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = [
    "ASSISTANT_VOICE_ID",
    "AssistantDefaults",
    "AssistantDefaultsApplied",
    "AssistantDefaultsService",
    "adopt_assistant_voice",
    "register_assistant_defaults_routes",
]
