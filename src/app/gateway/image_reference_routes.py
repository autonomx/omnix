"""Browser routes for reusable image-to-image reference assets."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query, Request

from app.assets import AssetListResponse
from app.image.reference_assets import (
    ImageReferenceError,
    list_image_reference_assets,
    save_image_reference_upload,
)

_ROUTE_SENTINEL = "_omnix_image_reference_routes_registered"
_HOOK_SENTINEL = "_omnix_image_reference_routes_hook_installed"
DEFAULT_REFERENCE_LIMIT = 100
MAX_REFERENCE_LIMIT = 250


def register_image_reference_routes(gateway: FastAPI) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get(
        "/api/image-generation/references",
        response_model=AssetListResponse,
        include_in_schema=False,
    )
    def image_references(
        limit: int = Query(default=DEFAULT_REFERENCE_LIMIT, ge=1, le=MAX_REFERENCE_LIMIT),
    ) -> AssetListResponse:
        return list_image_reference_assets(limit=limit)

    @gateway.post("/api/image-generation/references", include_in_schema=False)
    async def upload_image_reference(
        request: Request,
        filename: str = Query(default="reference-image"),
    ) -> dict[str, Any]:
        try:
            asset = save_image_reference_upload(
                await request.body(),
                filename=filename,
                mime_type=request.headers.get("content-type", ""),
            )
        except ImageReferenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True, "asset": asset.model_dump(mode="json")}


def install_image_reference_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_image_reference_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
