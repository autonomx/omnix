"""Character profile management with shared voice-asset validation."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.assets import AssetType, SharedAssetStore, default_asset_store

from .models import (
    ArchiveCharacterResponse,
    CharacterListResponse,
    CharacterProfile,
    CharacterVersionListResponse,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)
from .repository import (
    CharacterConflictError,
    CharacterNotFoundError,
    CharacterRepository,
)


class CharacterVoiceAssetError(ValueError):
    pass


class CharacterService:
    def __init__(
        self,
        repository: CharacterRepository | None = None,
        *,
        asset_store_factory: Callable[[], SharedAssetStore] = default_asset_store,
    ) -> None:
        self.repository = repository or CharacterRepository()
        self.asset_store_factory = asset_store_factory

    def list(self, *, include_archived: bool = False) -> CharacterListResponse:
        return CharacterListResponse(
            characters=self.repository.list(include_archived=include_archived)
        )

    def get(self, character_id: str, *, include_archived: bool = False) -> CharacterProfile:
        profile = self.repository.get(character_id, include_archived=include_archived)
        if profile is None:
            raise CharacterNotFoundError(character_id)
        return profile

    def create(self, request: CreateCharacterRequest) -> CharacterProfile:
        self._validate_voice_asset(request.default_voice_asset_id)
        return self.repository.create(request)

    def update(self, character_id: str, request: UpdateCharacterRequest) -> CharacterProfile:
        if request.default_voice_asset_id is not None:
            self._validate_voice_asset(request.default_voice_asset_id)
        return self.repository.update(character_id, request)

    def archive(self, character_id: str) -> ArchiveCharacterResponse:
        return ArchiveCharacterResponse(character=self.repository.archive(character_id))

    def versions(self, character_id: str) -> CharacterVersionListResponse:
        return CharacterVersionListResponse(versions=self.repository.versions(character_id))

    def resolve_snapshot(self, character_id: str):
        return self.get(character_id).snapshot()

    def _validate_voice_asset(self, asset_id: str | None) -> None:
        if not asset_id:
            return
        asset = next(
            (
                item
                for item in self.asset_store_factory().list_assets().assets
                if item.id == asset_id
            ),
            None,
        )
        if asset is None:
            raise CharacterVoiceAssetError(f"voice asset not found: {asset_id}")
        if asset.type != AssetType.VOICE_PROFILE:
            raise CharacterVoiceAssetError(
                f"asset is not a voice profile: {asset_id} ({asset.type.value})"
            )
        storage_path = Path(asset.storage_path)
        if asset.mime_type == "audio/wav" and not storage_path.is_file():
            raise CharacterVoiceAssetError(f"voice profile audio is missing: {asset_id}")


def default_character_service() -> CharacterService:
    return CharacterService()


__all__ = [
    "CharacterConflictError",
    "CharacterNotFoundError",
    "CharacterService",
    "CharacterVoiceAssetError",
    "default_character_service",
]
