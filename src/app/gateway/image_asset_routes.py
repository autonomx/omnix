"""Browser-safe file delivery for shared image assets."""
from __future__ import annotations

from functools import wraps
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from app.assets import AssetRecord, AssetType, default_asset_store

_ROUTE_SENTINEL = "_omnix_image_asset_file_registered"
_HOOK_SENTINEL = "_omnix_image_asset_file_hook_installed"
IMAGE_ASSET_FILE_PATH = "/api/assets/{asset_id}/file"
SUPPORTED_IMAGE_MIME_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}


def register_image_asset_file_route(gateway: FastAPI) -> None:
    """Register an ID-based image response without exposing local paths."""

    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get(IMAGE_ASSET_FILE_PATH, include_in_schema=False)
    def image_asset_file(asset_id: str, download: bool = Query(default=False)) -> FileResponse:
        asset = _asset_by_id(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        if asset.type != AssetType.IMAGE or asset.mime_type.lower() not in SUPPORTED_IMAGE_MIME_TYPES:
            raise HTTPException(status_code=415, detail="asset_content_not_image")
        path = Path(asset.storage_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="asset_file_not_found")
        return FileResponse(
            path,
            media_type=asset.mime_type,
            filename=path.name,
            content_disposition_type="attachment" if download else "inline",
        )


def _asset_by_id(asset_id: str) -> AssetRecord | None:
    return next((asset for asset in default_asset_store().list_assets().assets if asset.id == asset_id), None)


def install_image_asset_file_hook() -> None:
    """Install the image file route before the gateway app is constructed."""

    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_image_asset_file_route(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
