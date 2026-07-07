"""Browser-safe file delivery for shared image assets."""
from __future__ import annotations

from email.utils import formatdate, parsedate_to_datetime
from functools import wraps
import hashlib
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from app.assets import AssetRecord, AssetType, default_asset_store

_ROUTE_SENTINEL = "_omnix_image_asset_file_registered"
_HOOK_SENTINEL = "_omnix_image_asset_file_hook_installed"
IMAGE_ASSET_FILE_PATH = "/api/assets/{asset_id}/file"
SUPPORTED_IMAGE_MIME_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp", "image/svg+xml"}
IMMUTABLE_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
MUTABLE_ASSET_CACHE_CONTROL = "public, max-age=300, must-revalidate"


def register_image_asset_file_route(gateway: FastAPI) -> None:
    """Register an ID-based image response without exposing local paths."""

    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get(IMAGE_ASSET_FILE_PATH, include_in_schema=False)
    def image_asset_file(
        asset_id: str,
        request: Request,
        download: bool = Query(default=False),
    ) -> Response:
        asset = _asset_by_id(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        if asset.type != AssetType.IMAGE or asset.mime_type.lower() not in SUPPORTED_IMAGE_MIME_TYPES:
            raise HTTPException(status_code=415, detail="asset_content_not_image")
        if asset.mime_type.lower() == "image/svg+xml" and not bool(asset.metadata.get("trusted_svg")):
            raise HTTPException(status_code=415, detail="asset_svg_not_trusted")
        path = Path(asset.storage_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="asset_file_not_found")
        try:
            stat_result = path.stat()
        except OSError as exc:
            raise HTTPException(status_code=404, detail="asset_file_not_found") from exc
        etag = _asset_etag(asset, stat_result.st_size, stat_result.st_mtime_ns)
        last_modified = formatdate(stat_result.st_mtime, usegmt=True)
        headers = {
            "Cache-Control": _cache_control(asset),
            "ETag": etag,
            "Last-Modified": last_modified,
            "X-Content-Type-Options": "nosniff",
        }
        if _not_modified(request, etag, stat_result.st_mtime):
            return Response(status_code=304, headers=headers)
        return FileResponse(
            path,
            media_type=asset.mime_type,
            filename=path.name,
            content_disposition_type="attachment" if download else "inline",
            headers=headers,
            stat_result=stat_result,
        )


def _asset_by_id(asset_id: str) -> AssetRecord | None:
    return next((asset for asset in default_asset_store().list_assets().assets if asset.id == asset_id), None)


def _cache_control(asset: AssetRecord) -> str:
    return IMMUTABLE_ASSET_CACHE_CONTROL if bool(asset.metadata.get("immutable")) else MUTABLE_ASSET_CACHE_CONTROL


def _asset_etag(asset: AssetRecord, size: int, mtime_ns: int) -> str:
    source = f"{asset.id}:{size}:{mtime_ns}".encode("utf-8")
    return f'"{hashlib.sha256(source).hexdigest()}"'


def _not_modified(request: Request, etag: str, modified_timestamp: float) -> bool:
    if request.headers.get("if-none-match") == etag:
        return True
    if_modified_since = request.headers.get("if-modified-since")
    if not if_modified_since:
        return False
    try:
        requested_timestamp = parsedate_to_datetime(if_modified_since).timestamp()
    except (TypeError, ValueError, OverflowError):
        return False
    return int(modified_timestamp) <= int(requested_timestamp)


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
