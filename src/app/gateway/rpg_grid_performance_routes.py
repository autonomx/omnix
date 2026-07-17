"""Hidden measured performance route for campaign grid map instances."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from app.rpg.grid_runtime_performance import GridRuntimeBudget
from app.rpg.grid_runtime_performance_service import profile_campaign_grid_runtime

_ROUTE_SENTINEL = "_omnix_rpg_grid_performance_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_grid_performance_route_hook_installed"


def _body(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": "request_body_must_be_object"},
        )
    return value


def register_rpg_grid_performance_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/rpg/map-instances/{map_instance_id}/performance-profile",
        tags=["rpg-grid-performance"],
        include_in_schema=False,
    )
    async def rpg_grid_performance_profile(
        map_instance_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        destination = payload.get("path_probe_destination")
        if destination is not None:
            if not isinstance(destination, (list, tuple)) or len(destination) != 2:
                raise HTTPException(
                    status_code=422,
                    detail={"ok": False, "error": "path_probe_destination_invalid"},
                )
            path_probe_destination = (int(destination[0]), int(destination[1]))
        else:
            path_probe_destination = None
        try:
            budget = (
                GridRuntimeBudget.model_validate(payload["budget"])
                if isinstance(payload.get("budget"), Mapping)
                else None
            )
            return profile_campaign_grid_runtime(
                map_instance_id,
                observer_actor_id=str(payload.get("observer_actor_id") or ""),
                path_probe_actor_id=str(payload.get("path_probe_actor_id") or ""),
                path_probe_destination=path_probe_destination,
                budget=budget,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
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


def install_rpg_grid_performance_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_grid_performance_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
