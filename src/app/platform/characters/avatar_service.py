"""Character avatar-pack management backed by shared assets."""
from __future__ import annotations

from app.assets.protocol import AssetStore
import logging
from collections.abc import Callable
from typing import Protocol

from app.assets.content import asset_available
from app.assets import AssetRecord, AssetType, default_asset_store
from app.conversation.contracts import SYSTEM_ASSISTANT_ID
from app.runtime.ports import Port, implementations

from .avatar_models import CharacterAvatarPack, UpsertCharacterAvatarPackRequest
from .avatar_repository import CharacterAvatarRepository
from .repository import CharacterNotFoundError
from .service import CharacterService, default_character_service


LOGGER = logging.getLogger(__name__)


class CharacterAvatarAssetError(ValueError):
    pass


class PortraitImageObserver(Protocol):
    """Told when no portrait pack in the tenant shows an image any more (live portrait roadmap, Phase 4).

    The live portrait forgets what it made from the image (its encoding and idle loop). Called after the pack
    change is saved; an observer that fails is logged and never fails the change.
    """

    def on_portrait_released(self, asset_id: str) -> None: ...


PORTRAIT_IMAGE_OBSERVERS: Port[PortraitImageObserver] = Port(
    "characters.portrait_image_observers", PortraitImageObserver, "many",
)


class CharacterAvatarService:
    def __init__(
        self,
        repository: CharacterAvatarRepository | None = None,
        *,
        character_service_factory: Callable[[], CharacterService] = default_character_service,
        asset_store_factory: Callable[[], AssetStore] = default_asset_store,
    ) -> None:
        if repository is None:
            from app.persistence.runtime import uses_postgresql_runtime
            if uses_postgresql_runtime():
                from app.platform.characters.persistence.avatar_store import production_avatar_repository
                repository = production_avatar_repository()
            else:
                repository = CharacterAvatarRepository()
        self.repository = repository
        self.character_service_factory = character_service_factory
        self.asset_store_factory = asset_store_factory

    def _require_owner(self, character_id: str) -> None:
        # The System Assistant is no stored character, but it has a live avatar of its own like one.
        if character_id != SYSTEM_ASSISTANT_ID:
            self.character_service_factory().get(character_id, include_archived=True)

    def get(self, character_id: str) -> CharacterAvatarPack:
        self._require_owner(character_id)
        pack = self.repository.get(character_id)
        if pack is None:
            raise CharacterNotFoundError(f"character avatar pack not found: {character_id}")
        return pack

    def optional_get(self, character_id: str) -> CharacterAvatarPack | None:
        """Return a pack when present without treating normal absence as an error."""
        self._require_owner(character_id)
        return self.repository.get(character_id)

    def resolve(self, character_id: str | None) -> CharacterAvatarPack | None:
        if not character_id:
            return None
        return self.repository.get(character_id)

    def upsert(
        self,
        character_id: str,
        request: UpsertCharacterAvatarPackRequest,
    ) -> CharacterAvatarPack:
        self._require_owner(character_id)
        self._validate_assets(request)
        previous = self.repository.get(character_id)
        pack = self.repository.upsert(character_id, request)
        self._release_portrait(previous)
        return pack

    def portrait_image(self, pack: CharacterAvatarPack, *, max_bytes: int) -> bytes:
        """The portrait pack's image, read on the server (it never comes from the browser)."""
        if pack.renderer != "portrait" or not pack.base_asset_id:
            raise CharacterAvatarAssetError("this avatar pack is not a portrait")
        return self.asset_store_factory().read_asset_bytes(pack.base_asset_id, max_bytes=max_bytes)

    def delete(self, character_id: str) -> bool:
        self._require_owner(character_id)
        previous = self.repository.get(character_id)
        deleted = self.repository.delete(character_id)
        self._release_portrait(previous)
        return deleted

    def _release_portrait(self, previous: CharacterAvatarPack | None) -> None:
        """A portrait image no portrait pack shows any more is released (its portrait cache can go)."""
        if previous is None or previous.renderer != "portrait" or not previous.base_asset_id:
            return
        asset_id = previous.base_asset_id
        uses = getattr(self.repository, "portrait_uses", None)
        if uses is None or uses(asset_id):
            return
        for observer in implementations(PORTRAIT_IMAGE_OBSERVERS):
            try:
                observer.on_portrait_released(asset_id)
            except Exception:
                LOGGER.warning("portrait image observer failed", exc_info=True)

    def _validate_assets(self, request: UpsertCharacterAvatarPackRequest) -> None:
        image_asset_ids = {
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
        if request.renderer == "sprite" and not image_asset_ids:
            raise CharacterAvatarAssetError("sprite avatar pack requires at least one image asset")
        store = self.asset_store_factory()
        for asset_id in sorted(image_asset_ids):
            asset = store.get_asset(asset_id)
            if asset is None:
                raise CharacterAvatarAssetError(f"avatar image asset not found: {asset_id}")
            if asset.type != AssetType.IMAGE:
                raise CharacterAvatarAssetError(
                    f"avatar asset is not an image: {asset_id} ({asset.type.value})"
                )
            _require_file(asset, "avatar image")

        if request.renderer == "portrait" and not request.base_asset_id:
            raise CharacterAvatarAssetError("portrait avatar pack requires its portrait image")
        # A rigged renderer draws its rig; a portrait pack does only when its fallback is Live2D.
        if request.renderer in {"live2d", "rive"} or (
                request.renderer == "portrait" and request.fallback_renderer == "live2d"):
            rig_asset_id = request.rig_asset_id
            if not rig_asset_id:
                raise CharacterAvatarAssetError("rigged avatar pack requires a rig asset")
            rig_asset = store.get_asset(rig_asset_id)
            if rig_asset is None:
                raise CharacterAvatarAssetError(f"avatar rig asset not found: {rig_asset_id}")
            allowed_rig_types = {AssetType.EXPORT, AssetType.SETTINGS_ARTIFACT}
            if rig_asset.type not in allowed_rig_types:
                raise CharacterAvatarAssetError(
                    f"avatar rig asset has unsupported type: {rig_asset_id} ({rig_asset.type.value})"
                )
            _require_file(rig_asset, "avatar rig")


def _require_file(asset: AssetRecord, label: str) -> None:
    try:
        available = asset_available(asset)
    except OSError:
        available = False
    if not available:
        raise CharacterAvatarAssetError(f"{label} file is missing: {asset.id}")


def default_character_avatar_service() -> CharacterAvatarService:
    return CharacterAvatarService()


__all__ = [
    "PORTRAIT_IMAGE_OBSERVERS",
    "CharacterAvatarAssetError",
    "CharacterAvatarService",
    "PortraitImageObserver",
    "default_character_avatar_service",
]
