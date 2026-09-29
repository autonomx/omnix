"""Core assets routes with explicitly injected store factories."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.assets import (
    AssetLegacyImportDryRun,
    AssetListResponse,
    AssetMigrationPreview,
    AssetRecord,
    SharedAssetStore,
)
from app.gateway.schemas import AssetContentResponse
from app.assets.models import AssetContentTooLarge


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


def _read_text_asset(asset_store: SharedAssetStore, asset: AssetRecord) -> AssetContentResponse:
    if not _text_asset_supported(asset):
        raise HTTPException(status_code=415, detail="asset_content_not_text")
    try:
        content_bytes = asset_store.read_asset_bytes(asset.id, max_bytes=2_000_000)
    except AssetContentTooLarge as exc:
        raise HTTPException(status_code=413, detail="asset_content_too_large") from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="asset_file_not_found") from exc
    try:
        content = content_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="asset_content_not_utf8") from exc
    size_bytes = len(content_bytes)
    return AssetContentResponse(asset=asset, content=content, size_bytes=size_bytes)


def register_core_assets_routes(router: APIRouter, *, get_asset_store):
    @router.get("/api/assets", response_model=AssetListResponse, tags=["assets"])
    def assets() -> AssetListResponse:
        return get_asset_store().list_assets()

    @router.get(
        "/api/assets/{asset_id}/content",
        response_model=AssetContentResponse,
    )
    async def asset_content(asset_id: str) -> AssetContentResponse:
        asset_store = get_asset_store()
        asset = _asset_by_id(asset_store, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        return _read_text_asset(asset_store, asset)

    @router.post(
        "/api/assets/migrations/image/dry-run",
        response_model=AssetMigrationPreview,
        tags=["assets"],
    )
    async def image_asset_migration_dry_run() -> AssetMigrationPreview:
        return get_asset_store().import_image_manifest_dry_run()

    @router.post(
        "/api/assets/migrations/image/import",
        response_model=AssetMigrationPreview,
        tags=["assets"],
    )
    async def image_asset_migration_import() -> AssetMigrationPreview:
        return get_asset_store().import_image_manifest()

    @router.post(
        "/api/assets/migrations/legacy-non-image/dry-run",
        response_model=AssetLegacyImportDryRun,
        tags=["assets"],
    )
    async def legacy_non_image_asset_migration_dry_run() -> AssetLegacyImportDryRun:
        return get_asset_store().preview_legacy_non_image_import()
