"""Hidden gateway routes for portable RPG world bundle export and import."""
from __future__ import annotations
from fastapi import APIRouter


from functools import wraps
from typing import Any, Callable

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response

from app.rpg.worlds.world_bundle import MAX_WORLD_BUNDLE_BYTES
from app.rpg.worlds.world_bundle_export import export_world_bundle
from app.rpg.worlds.world_bundle_import import (
    WorldBundleImportConflict,
    import_world_bundle,
)

_ROUTE_SENTINEL = "_omnix_rpg_world_bundle_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_world_bundle_route_hook_installed"


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(
            status_code=404,
            detail={"ok": False, "error": str(exc).strip("'")},
        )
    if isinstance(exc, WorldBundleImportConflict):
        return HTTPException(
            status_code=409,
            detail={"ok": False, "error": str(exc)},
        )
    return HTTPException(
        status_code=422,
        detail={"ok": False, "error": str(exc)},
    )


def register_rpg_world_bundle_routes(router: APIRouter, state) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.get(
        "/api/rpg/worlds/{world_id}/export",
        response_model=None,
        response_class=Response,
        responses={
            200: {
                "description": "Portable RPG world bundle archive.",
                "content": {
                    "application/zip": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                },
            }
        },
        tags=["rpg-world"],
    )
    def rpg_export_world_bundle(world_id: str) -> Response:
        try:
            bundle = export_world_bundle(world_id)
        except (KeyError, ValueError) as exc:
            raise _error(exc) from exc
        return Response(
            content=bundle.content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{bundle.filename}"',
                "X-Omnix-World-Bundle-Version": str(bundle.manifest.version),
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post(
        "/api/rpg/worlds/import",
        tags=["rpg-world"],
    )
    def rpg_import_world_bundle(
        request: Request,
        bundle_content: bytes = Body(..., media_type="application/zip"),
        target_world_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_WORLD_BUNDLE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail={"ok": False, "error": "world_bundle_size_limit_exceeded"},
                    )
            except ValueError:
                pass
        content = bundle_content
        try:
            return import_world_bundle(
                content,
                target_world_id=target_world_id,
            )
        except (KeyError, ValueError) as exc:
            raise _error(exc) from exc


def install_rpg_world_bundle_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_world_bundle_routes(self, self.state)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
