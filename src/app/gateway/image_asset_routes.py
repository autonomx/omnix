"""Browser-safe file delivery for shared image assets."""
from __future__ import annotations

from email.utils import formatdate, parsedate_to_datetime
from functools import wraps
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from app.assets import AssetRecord, AssetType, default_asset_store

_ROUTE_SENTINEL = "_omnix_image_asset_file_registered"
_HOOK_SENTINEL = "_omnix_image_asset_file_hook_installed"
IMAGE_ASSET_FILE_PATH = "/api/assets/{asset_id}/file"
SUPPORTED_IMAGE_MIME_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp", "image/svg+xml"}
NORMALIZABLE_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
IMMUTABLE_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
MUTABLE_ASSET_CACHE_CONTROL = "public, max-age=300, must-revalidate"
BROWSER_PREVIEW_CACHE_CONTROL = "public, max-age=300, must-revalidate"


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
        preview: bool = Query(default=False),
    ) -> Response:
        asset = _asset_by_id(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        if asset.type != AssetType.IMAGE or asset.mime_type.lower() not in SUPPORTED_IMAGE_MIME_TYPES:
            raise HTTPException(status_code=415, detail="asset_content_not_image")
        if asset.mime_type.lower() == "image/svg+xml" and not _is_trusted_svg(asset):
            raise HTTPException(status_code=415, detail="asset_svg_not_trusted")
        path = Path(asset.storage_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="asset_file_not_found")
        try:
            stat_result = path.stat()
        except OSError as exc:
            raise HTTPException(status_code=404, detail="asset_file_not_found") from exc

        browser_preview = bool(preview and not download)
        etag = _asset_etag(
            asset,
            stat_result.st_size,
            stat_result.st_mtime_ns,
            variant="browser-preview-v2" if browser_preview else "original",
        )
        last_modified = formatdate(stat_result.st_mtime, usegmt=True)
        headers = {
            "Cache-Control": BROWSER_PREVIEW_CACHE_CONTROL if browser_preview else _cache_control(asset),
            "ETag": etag,
            "Last-Modified": last_modified,
            "X-Content-Type-Options": "nosniff",
        }
        if _not_modified(request, etag, stat_result.st_mtime):
            return Response(status_code=304, headers=headers)

        if browser_preview:
            normalized_response = _normalized_browser_preview(path, asset, headers)
            if normalized_response is not None:
                return normalized_response

        return FileResponse(
            path,
            media_type=asset.mime_type,
            filename=path.name,
            content_disposition_type="attachment" if download else "inline",
            headers=headers,
            stat_result=stat_result,
        )


def _normalized_browser_preview(
    path: Path,
    asset: AssetRecord,
    headers: dict[str, str],
) -> Response | None:
    """Re-encode unusual raster assets without mutating the stored original.

    Pillow is intentionally imported only on the preview-normalization path so
    importing unrelated gateway modules does not require image dependencies.
    """

    if asset.mime_type.lower() not in NORMALIZABLE_IMAGE_MIME_TYPES:
        return None
    try:
        from PIL import Image

        from app.image.output_normalization import normalize_generated_image
    except ImportError:
        return None
    try:
        with Image.open(path) as source:
            width, height = source.size
            requires_normalization = (
                source.mode != "RGB"
                or max(width, height) > 8192
                or width * height > 32 * 1024 * 1024
            )
            if not requires_normalization:
                return None
            normalized, _metadata = normalize_generated_image(source)
            output = BytesIO()
            normalized.save(output, format="PNG", optimize=False, compress_level=6)
    except (OSError, TypeError, ValueError):
        # A valid browser-decodable original remains preferable to replacing a
        # failed normalization attempt with a gateway error.
        return None

    preview_headers = dict(headers)
    preview_headers["Content-Disposition"] = f'inline; filename="{path.stem}.png"'
    preview_headers["X-Omnix-Image-Normalized"] = "1"
    return Response(
        content=output.getvalue(),
        media_type="image/png",
        headers=preview_headers,
    )


def _asset_by_id(asset_id: str) -> AssetRecord | None:
    store = default_asset_store()
    get_asset = getattr(store, "get_asset", None)
    if callable(get_asset):
        return get_asset(asset_id)
    return next((asset for asset in store.list_assets().assets if asset.id == asset_id), None)


def _is_trusted_svg(asset: AssetRecord) -> bool:
    """Allow only explicitly trusted SVGs, including legacy curated map-pack records."""

    if bool(asset.metadata.get("trusted_svg")):
        return True
    return str(asset.compat.get("source") or "").strip() == "curated-svg"


def _cache_control(asset: AssetRecord) -> str:
    return IMMUTABLE_ASSET_CACHE_CONTROL if bool(asset.metadata.get("immutable")) else MUTABLE_ASSET_CACHE_CONTROL


def _asset_etag(asset: AssetRecord, size: int, mtime_ns: int, *, variant: str = "original") -> str:
    source = f"{asset.id}:{size}:{mtime_ns}:{variant}".encode("utf-8")
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
