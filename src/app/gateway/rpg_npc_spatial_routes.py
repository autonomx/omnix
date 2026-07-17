"""Hidden gateway routes for durable campaign NPC spatial simulation."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import ValidationError

from app.rpg.npc_spatial_campaign_authoring import (
    configure_campaign_spatial_policy,
    read_campaign_spatial_state,
    save_campaign_spatial_goal,
    save_campaign_spatial_routine,
)
from app.rpg.npc_spatial_campaign_contracts import (
    CampaignNpcSpatialGoal,
    CampaignNpcSpatialPolicy,
    CampaignNpcSpatialRoutine,
    CampaignSpatialTickRequest,
)
from app.rpg.npc_spatial_campaign_runtime import advance_campaign_spatial_tick

_ROUTE_SENTINEL = "_omnix_rpg_npc_spatial_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_npc_spatial_route_hook_installed"


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


def register_rpg_npc_spatial_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/rpg/campaigns/{campaign_id}/spatial-goals",
        include_in_schema=False,
    )
    async def rpg_save_campaign_spatial_goal(
        campaign_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        payload["campaign_id"] = campaign_id
        expected_revision = int(payload.pop("expected_revision", 0))
        try:
            goal = CampaignNpcSpatialGoal.model_validate(payload)
            return save_campaign_spatial_goal(
                goal,
                expected_revision=expected_revision,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/campaigns/{campaign_id}/spatial-routines",
        include_in_schema=False,
    )
    async def rpg_save_campaign_spatial_routine(
        campaign_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        payload["campaign_id"] = campaign_id
        expected_revision = int(payload.pop("expected_revision", 0))
        try:
            routine = CampaignNpcSpatialRoutine.model_validate(payload)
            return save_campaign_spatial_routine(
                routine,
                expected_revision=expected_revision,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/campaigns/{campaign_id}/spatial-policy",
        include_in_schema=False,
    )
    async def rpg_configure_campaign_spatial_policy(
        campaign_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        expected_world_tick = int(payload.pop("expected_world_tick", -1))
        if expected_world_tick < 0:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "expected_world_tick_required"},
            )
        try:
            policy = CampaignNpcSpatialPolicy.model_validate(payload)
            return configure_campaign_spatial_policy(
                campaign_id,
                policy,
                expected_world_tick=expected_world_tick,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/campaigns/{campaign_id}/spatial-ticks",
        include_in_schema=False,
    )
    async def rpg_advance_campaign_spatial_tick(
        campaign_id: str,
        request: Request,
    ) -> dict[str, Any]:
        try:
            tick_request = CampaignSpatialTickRequest.model_validate(
                _body(await request.json())
            )
            return advance_campaign_spatial_tick(campaign_id, tick_request)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.get(
        "/api/rpg/campaigns/{campaign_id}/spatial-state",
        include_in_schema=False,
    )
    def rpg_read_campaign_spatial_state(
        campaign_id: str,
        tick_limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, Any]:
        try:
            return read_campaign_spatial_state(
                campaign_id,
                tick_limit=tick_limit,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise


def install_rpg_npc_spatial_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_npc_spatial_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
