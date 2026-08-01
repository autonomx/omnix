"""Character profile management with shared voice-asset validation."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.assets import AssetRecord, AssetType, SharedAssetStore, default_asset_store

from .models import (
    ArchiveCharacterResponse,
    CharacterListResponse,
    CharacterProfile,
    CharacterVersionListResponse,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)
from .repository import CharacterConflictError, CharacterNotFoundError, CharacterRepository
from .voice_consent import VoiceConsentError, VoiceProfileGovernanceService


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
        asset = self._validate_voice_asset(request.default_voice_asset_id)
        if asset is not None and request.default_voice_asset_id != asset.id:
            request = request.model_copy(update={"default_voice_asset_id": asset.id})
        return self.repository.create(request)

    def update(self, character_id: str, request: UpdateCharacterRequest) -> CharacterProfile:
        if request.default_voice_asset_id is not None:
            asset = self._validate_voice_asset(request.default_voice_asset_id)
            if asset is not None and request.default_voice_asset_id != asset.id:
                request = request.model_copy(update={"default_voice_asset_id": asset.id})
        return self.repository.update(character_id, request)

    def archive(self, character_id: str) -> ArchiveCharacterResponse:
        return ArchiveCharacterResponse(character=self.repository.archive(character_id))

    def versions(self, character_id: str) -> CharacterVersionListResponse:
        return CharacterVersionListResponse(versions=self.repository.versions(character_id))

    def resolve_snapshot(self, character_id: str):
        return self.get(character_id).snapshot()

    def resolve_voice_asset(self, asset_id: str | None) -> AssetRecord | None:
        """Resolve a governed voice ID, tolerating legacy casing differences.

        Asset IDs are identifiers and remain canonical as returned by the shared
        library. Older character profiles may contain a speaker-cased suffix such
        as ``voice-cloning:Jinx`` while the library record is
        ``voice-cloning:jinx``. Resolve a unique case-insensitive match and return
        the canonical record so callers never confuse asset casing with the exact
        case-sensitive TTS speaker stored in metadata.
        """

        normalized_id = str(asset_id or "").strip()
        if not normalized_id:
            return None
        assets = self.asset_store_factory().list_assets().assets
        exact = next((item for item in assets if item.id == normalized_id), None)
        if exact is not None:
            return exact
        folded_id = normalized_id.casefold()
        matches = [item for item in assets if item.id.casefold() == folded_id]
        return matches[0] if len(matches) == 1 else None

    def validate_voice_for_use(self, asset_id: str, use: str = "character") -> None:
        asset = self.resolve_voice_asset(asset_id)
        if asset is None:
            raise CharacterVoiceAssetError(f"voice asset not found: {asset_id}")
        try:
            VoiceProfileGovernanceService(
                asset_store_factory=self.asset_store_factory
            ).validate_use(asset.id, use)  # type: ignore[arg-type]
        except VoiceConsentError as exc:
            raise CharacterVoiceAssetError(str(exc)) from exc

    def _validate_voice_asset(self, asset_id: str | None) -> AssetRecord | None:
        if not asset_id:
            return None
        asset = self.resolve_voice_asset(asset_id)
        if asset is None:
            raise CharacterVoiceAssetError(f"voice asset not found: {asset_id}")
        if asset.type != AssetType.VOICE_PROFILE:
            raise CharacterVoiceAssetError(
                f"asset is not a voice profile: {asset_id} ({asset.type.value})"
            )
        storage_path = Path(asset.storage_path)
        if asset.mime_type == "audio/wav" and not storage_path.is_file():
            raise CharacterVoiceAssetError(f"voice profile audio is missing: {asset.id}")
        self.validate_voice_for_use(asset.id, "character")
        return asset


def default_character_service() -> CharacterService:
    return CharacterService()


__all__ = [
    "CharacterConflictError",
    "CharacterNotFoundError",
    "CharacterService",
    "CharacterVoiceAssetError",
    "default_character_service",
]
