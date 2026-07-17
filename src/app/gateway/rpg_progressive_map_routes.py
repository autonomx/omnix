"""Hidden gateway routes for predictive deferred-map materialization."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Query, Request

from app.rpg.worlds.progressive_materialization import materialize_deferred_location
from app.rpg.worlds.progressive_materialization_job_service import (
    materialization_job_telemetry,
    schedule_campaign_predictive_materialization,
    schedule_predictive_materialization,
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
                source_world_revision=int(payload.get("source_world_revision") or 0),
                location_id=location_id,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/worlds/{world_id}/materialization-jobs/schedule",
        include_in_schema=False,
    )
    async def rpg_schedule_world_materialization(
        world_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        current_location_id = str(payload.get("current_location_id") or "").strip()
        if not current_location_id:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "current_location_id_required"},
            )
        try:
            return schedule_predictive_materialization(
                world_id=world_id,
                source_world_revision=int(payload.get("source_world_revision") or 0),
                current_location_id=current_location_id,
                route_intent_location_id=(
                    str(payload["route_intent_location_id"])
                    if payload.get("route_intent_location_id")
                    else None
                ),
                minimum_score=float(payload.get("minimum_score", 0.35)),
                kick_worker=bool(payload.get("kick_worker", True)),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/campaigns/{campaign_id}/materialization-signals",
        include_in_schema=False,
    )
    async def rpg_schedule_campaign_materialization(
        campaign_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        current_location_id = str(payload.get("current_location_id") or "").strip()
        if not current_location_id:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "current_location_id_required"},
            )
        try:
            return schedule_campaign_predictive_materialization(
                campaign_id,
                current_location_id=current_location_id,
                route_intent_location_id=(
                    str(payload["route_intent_location_id"])
                    if payload.get("route_intent_location_id")
                    else None
                ),
                minimum_score=float(payload.get("minimum_score", 0.35)),
                kick_worker=bool(payload.get("kick_worker", True)),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.get(
        "/api/rpg/worlds/{world_id}/materialization-jobs",
        include_in_schema=False,
    )
    def rpg_materialization_telemetry(
        world_id: str,
        source_world_revision: int | None = Query(default=None, ge=1),
    ) -> dict[str, Any]:
        return materialization_job_telemetry(
            world_id=world_id,
            source_world_revision=source_world_revision,
        )


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
