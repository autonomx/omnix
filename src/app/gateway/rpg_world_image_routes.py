"""World-authoring image target, generation, and review routes."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request

from app.rpg.worlds.world_images import (
    generate_world_images,
    read_world_image_targets,
    update_world_image_target,
)

_ROUTE_SENTINEL = "_omnix_rpg_world_image_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_world_image_route_hook_installed"


def _body(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": "request_body_must_be_object"},
        )
    return value


def _raise_domain_error(exc: Exception) -> None:
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


def register_rpg_world_image_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get(
        "/api/rpg/worlds/{world_id}/image-targets",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_world_image_targets(world_id: str) -> dict[str, Any]:
        try:
            return read_world_image_targets(world_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/worlds/{world_id}/image-generation",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_world_image_generation(
        world_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        target_ids = [
            str(value)
            for value in payload.get("target_ids") or ()
            if str(value).strip()
        ]
        prompts = payload.get("prompts")
        try:
            return generate_world_images(
                world_id,
                target_ids=target_ids,
                prompts=prompts if isinstance(prompts, Mapping) else {},
                provider_id=str(payload.get("provider_id") or ""),
                width=max(64, int(payload.get("width") or 768)),
                height=max(64, int(payload.get("height") or 768)),
                style=str(payload.get("style") or ""),
                no_cache=bool(payload.get("no_cache", False)),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.patch(
        "/api/rpg/worlds/{world_id}/image-targets/{target_id:path}",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_update_world_image_target(
        world_id: str,
        target_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        try:
            return update_world_image_target(
                world_id,
                target_id,
                review_state=(
                    str(payload.get("review_state"))
                    if payload.get("review_state") is not None
                    else None
                ),
                active_asset_id=(
                    str(payload.get("active_asset_id"))
                    if payload.get("active_asset_id")
                    else None
                ),
                suggested_prompt=(
                    str(payload.get("suggested_prompt"))
                    if payload.get("suggested_prompt") is not None
                    else None
                ),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/worlds/{world_id}/image-targets/{target_id:path}/regenerate",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_regenerate_world_image_target(
        world_id: str,
        target_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        prompt = str(payload.get("prompt") or "").strip()
        try:
            return generate_world_images(
                world_id,
                target_ids=[target_id],
                prompts={target_id: prompt} if prompt else {},
                provider_id=str(payload.get("provider_id") or ""),
                width=max(64, int(payload.get("width") or 768)),
                height=max(64, int(payload.get("height") or 768)),
                style=str(payload.get("style") or ""),
                no_cache=bool(payload.get("no_cache", True)),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise


def install_rpg_world_image_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_world_image_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
