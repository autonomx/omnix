"""Character avatar-pack management backed by shared image assets."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.assets import AssetType, SharedAssetStore, default_asset_store

from .avatar_models import CharacterAvatarPack, UpsertCharacterAvatarPackRequest
from .avatar_repository import CharacterAvatarRepository
from .repository import CharacterNotFoundError
from .service import CharacterService, default_character_service


class CharacterAvatarAssetError(ValueError):
    pass


class CharacterAvatarService:
    def __init__(
        self,
        repository: CharacterAvatarRepository | None = None,
        *,
        character_service_factory: Callable[[], CharacterService] = default_character_service,
        asset_store_factory: Callable[[], SharedAssetStore] = default_asset_store,
    ) -> None:
        self.repository = repository or CharacterAvatarRepository()
        self.character_service_factory = character_service_factory
        self.asset_store_factory = asset_store_factory

    def get(self, character_id: str) -> CharacterAvatarPack:
        self.character_service_factory().get(character_id, include_archived=True)
        pack = self.repository.get(character_id)
        if pack is None:
            raise CharacterNotFoundError(f"character avatar pack not found: {character_id}")
        return pack

    def resolve(self, character_id: str | None) -> CharacterAvatarPack | None:
        if not character_id:
            return None
        return self.repository.get(character_id)

    def upsert(
        self,
        character_id: str,
        request: UpsertCharacterAvatarPackRequest,
    ) -> CharacterAvatarPack:
        self.character_service_factory().get(character_id, include_archived=True)
        self._validate_assets(request)
        return self.repository.upsert(character_id, request)

    def delete(self, character_id: str) -> bool:
        self.character_service_factory().get(character_id, include_archived=True)
        return self.repository.delete(character_id)

    def _validate_assets(self, request: UpsertCharacterAvatarPackRequest) -> None:
        asset_ids = {
            asset_id
            for asset_id in [
                request.base_asset_id,
                *request.mouth_frames.values(),
                *request.blink_frames.values(),
                *request.expression_frames.values(),
                *request.outfit_frames.values(),
                *request.background_asset_ids.values(),
            ]
            if asset_id
        }
        if not asset_ids:
            raise CharacterAvatarAssetError("avatar pack requires at least one image asset")
        assets = {asset.id: asset for asset in self.asset_store_factory().list_assets().assets}
        for asset_id in sorted(asset_ids):
            asset = assets.get(asset_id)
            if asset is None:
                raise CharacterAvatarAssetError(f"avatar image asset not found: {asset_id}")
            if asset.type != AssetType.IMAGE:
                raise CharacterAvatarAssetError(
                    f"avatar asset is not an image: {asset_id} ({asset.type.value})"
                )
            try:
                available = Path(asset.storage_path).is_file()
            except OSError:
                available = False
            if not available:
                raise CharacterAvatarAssetError(f"avatar image file is missing: {asset_id}")


def default_character_avatar_service() -> CharacterAvatarService:
    return CharacterAvatarService()


__all__ = [
    "CharacterAvatarAssetError",
    "CharacterAvatarService",
    "default_character_avatar_service",
]
