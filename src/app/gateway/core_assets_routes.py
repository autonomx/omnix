"""Core assets routes with explicitly injected store factories."""

from __future__ import annotations

from .core_services import (
    AssetContentResponse,
    AssetLegacyImportDryRun,
    AssetListResponse,
    AssetMigrationPreview,
    HTTPException,
    SaveStoryAssetRequest,
    SavedStoryAssetResponse,
    _asset_by_id,
    _read_text_asset,
    save_story_asset,
)


def register_core_assets_routes(gateway, *, get_asset_store):
    @gateway.get("/api/assets", response_model=AssetListResponse, tags=["assets"])
    def assets() -> AssetListResponse:
        return get_asset_store().list_assets()

    @gateway.get(
        "/api/assets/{asset_id}/content",
        response_model=AssetContentResponse,
        include_in_schema=False,
    )
    async def asset_content(asset_id: str) -> AssetContentResponse:
        asset = _asset_by_id(get_asset_store(), asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        return _read_text_asset(asset)

    @gateway.post(
        "/api/assets/story",
        response_model=SavedStoryAssetResponse,
        include_in_schema=False,
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
