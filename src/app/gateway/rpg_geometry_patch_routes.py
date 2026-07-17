"""Hidden gateway routes for campaign-owned geometry patch events."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from app.rpg.map_geometry_patch import ApplyGeometryPatchCommand
from app.rpg.map_geometry_patch_service import apply_campaign_geometry_patch

_ROUTE_SENTINEL = "_omnix_rpg_geometry_patch_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_geometry_patch_route_hook_installed"


def _body(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": "request_body_must_be_object"},
        )
    return value


def _raise_domain_error(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": str(exc).strip("'")},
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error": str(exc)},
        ) from exc
    raise exc


def register_rpg_geometry_patch_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/rpg/map-instances/{map_instance_id}/geometry-patches",
        include_in_schema=False,
    )
    async def rpg_apply_geometry_patch(
        map_instance_id: str,
        request: Request,
    ) -> dict[str, Any]:
        try:
            command = ApplyGeometryPatchCommand.model_validate(
                _body(await request.json())
            )
            event, snapshot = apply_campaign_geometry_patch(
                map_instance_id,
                command,
            )
            return {
                "ok": True,
                "event": event.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
            }
        except Exception as exc:
            _raise_domain_error(exc)
            raise


def install_rpg_geometry_patch_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_geometry_patch_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
