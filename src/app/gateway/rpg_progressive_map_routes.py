"""Hidden gateway routes for predictive deferred-map materialization."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request

from app.rpg.worlds.progressive_materialization import (
    materialize_deferred_location,
)

_ROUTE_SENTINEL = "_omnix_rpg_progressive_map_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_progressive_map_route_hook_installed"


def _body(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": "request_body_must_be_object"},
        )
    return value


def register_rpg_progressive_map_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/rpg/worlds/{world_id}/deferred-locations/{location_id}/materialize",
        include_in_schema=False,
    )
    async def rpg_materialize_deferred_location(
        world_id: str,
        location_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        try:
            return materialize_deferred_location(
                world_id=world_id,
                source_world_revision=int(
                    payload.get("source_world_revision") or 0
                ),
                location_id=location_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "error": str(exc).strip("'")},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={"ok": False, "error": str(exc)},
            ) from exc


def install_rpg_progressive_map_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_progressive_map_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
