"""Shared asset/artifact library."""
from __future__ import annotations

from .legacy_documents import legacy_document_assets
from .models import AssetListResponse, AssetMigrationPreview, AssetRecord, AssetType
from .store import SharedAssetStore as ManifestSharedAssetStore


class SharedAssetStore(ManifestSharedAssetStore):
    """Shared asset store with compatibility read-through for legacy documents."""

    def list_assets(self) -> AssetListResponse:
        assets = {asset.id: asset for asset in super().list_assets().assets}
        for asset in legacy_document_assets():
            assets.setdefault(asset.id, asset)
        return AssetListResponse(assets=list(assets.values()))


def default_asset_store() -> SharedAssetStore:
    return SharedAssetStore()


__all__ = [
    "AssetListResponse",
    "AssetMigrationPreview",
    "AssetRecord",
    "AssetType",
    "SharedAssetStore",
    "default_asset_store",
]
