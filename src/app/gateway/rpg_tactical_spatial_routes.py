"""Hidden tactical movement and attack routes for campaign map instances."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from app.rpg.tactical_spatial import (
    TacticalAttackCommand,
    TacticalMoveCommand,
    TacticalSpatialError,
    TacticalSpatialPolicy,
)
from app.rpg.tactical_spatial_service import attack_tactically, move_actor_tactically

_ROUTE_SENTINEL = "_omnix_rpg_tactical_spatial_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_tactical_spatial_route_hook_installed"


def _body(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": "request_body_must_be_object"},
        )
    return value


def _policy(value: object) -> TacticalSpatialPolicy | None:
    return TacticalSpatialPolicy.model_validate(value) if isinstance(value, Mapping) else None


def _raise_domain_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": str(exc).strip("'")},
        ) from exc
    if isinstance(exc, (TacticalSpatialError, ValueError)):
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error": str(exc)},
        ) from exc
    raise exc


def register_rpg_tactical_spatial_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/rpg/map-instances/{map_instance_id}/tactical/move",
        tags=["rpg-tactical-spatial"],
        include_in_schema=False,
    )
    async def rpg_tactical_move(
        map_instance_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        raw_policy = payload.pop("policy", None)
        try:
            command = TacticalMoveCommand.model_validate(payload)
            return move_actor_tactically(
                map_instance_id,
                command,
                policy=_policy(raw_policy),
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/map-instances/{map_instance_id}/tactical/attack",
        tags=["rpg-tactical-spatial"],
        include_in_schema=False,
    )
    async def rpg_tactical_attack(
        map_instance_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        raw_policy = payload.pop("policy", None)
        expected_map_state_revision = payload.pop("expected_map_state_revision", None)
        if expected_map_state_revision is None:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "expected_map_state_revision_required"},
            )
        try:
            command = TacticalAttackCommand.model_validate(payload)
            return attack_tactically(
                map_instance_id,
                command,
                expected_map_state_revision=int(expected_map_state_revision),
                policy=_policy(raw_policy),
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except Exception as exc:
            _raise_domain_error(exc)
            raise


def install_rpg_tactical_spatial_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_tactical_spatial_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
