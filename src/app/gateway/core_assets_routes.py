"""Core assets routes with explicitly injected store factories."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.assets import (
    AssetLegacyImportDryRun,
    AssetListResponse,
    AssetMigrationPreview,
    AssetRecord,
    SharedAssetStore,
)
from app.gateway.schemas import AssetContentResponse
from app.gateway.story_asset_save import (
    SaveStoryAssetRequest,
    SavedStoryAssetResponse,
    save_story_asset,
)


def _asset_by_id(asset_store: SharedAssetStore, asset_id: str) -> AssetRecord | None:
    get_asset = getattr(asset_store, "get_asset", None)
    if callable(get_asset):
        return get_asset(asset_id)
    return next(
        (asset for asset in asset_store.list_assets().assets if asset.id == asset_id),
        None,
    )


def _text_asset_supported(asset: AssetRecord) -> bool:
    mime_type = asset.mime_type.lower().split(";", 1)[0]
    return mime_type.startswith("text/") or mime_type in {
        "application/json",
        "application/x-subrip",
        "text/html",
        "text/markdown",
        "text/plain",
        "text/vtt",
    }


def _read_text_asset(asset: AssetRecord) -> AssetContentResponse:
    if not _text_asset_supported(asset):
        raise HTTPException(status_code=415, detail="asset_content_not_text")
    path = Path(asset.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="asset_file_not_found")
    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        raise HTTPException(status_code=404, detail="asset_file_not_found") from exc
    if size_bytes > 2_000_000:
        raise HTTPException(status_code=413, detail="asset_content_too_large")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="asset_content_not_utf8") from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="asset_file_not_found") from exc
    return AssetContentResponse(asset=asset, content=content, size_bytes=size_bytes)


def register_core_assets_routes(gateway, *, get_asset_store):
    @gateway.get("/api/assets", response_model=AssetListResponse, tags=["assets"])
    def assets() -> AssetListResponse:
        return get_asset_store().list_assets()

    @gateway.get(
        "/api/assets/{asset_id}/content",
        response_model=AssetContentResponse,
    )
    async def asset_content(asset_id: str) -> AssetContentResponse:
        asset = _asset_by_id(get_asset_store(), asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        return _read_text_asset(asset)

    @gateway.post(
        "/api/assets/story",
        response_model=SavedStoryAssetResponse,
    )
    async def save_story_asset_endpoint(
        request: SaveStoryAssetRequest,
    ) -> SavedStoryAssetResponse:
        return save_story_asset(get_asset_store(), request)

    @gateway.post(
        "/api/assets/migrations/image/dry-run",
        response_model=AssetMigrationPreview,
        tags=["assets"],
    )
    async def image_asset_migration_dry_run() -> AssetMigrationPreview:
        return get_asset_store().import_image_manifest_dry_run()

    @gateway.post(
        "/api/assets/migrations/image/import",
        response_model=AssetMigrationPreview,
        tags=["assets"],
    )
    async def image_asset_migration_import() -> AssetMigrationPreview:
        return get_asset_store().import_image_manifest()

    @gateway.post(
        "/api/assets/migrations/legacy-non-image/dry-run",
        response_model=AssetLegacyImportDryRun,
        tags=["assets"],
    )
    async def legacy_non_image_asset_migration_dry_run() -> AssetLegacyImportDryRun:
        return get_asset_store().preview_legacy_non_image_import()
