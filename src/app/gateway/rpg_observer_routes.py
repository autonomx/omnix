"""Hidden gateway routes for observer knowledge and safe map projections."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import ValidationError

from app.rpg.map_observer_runtime import ObserverPerceptionPolicy
from app.rpg.map_observer_service import (
    load_campaign_observer_projection,
    observe_campaign_map,
)

_ROUTE_SENTINEL = "_omnix_rpg_observer_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_observer_route_hook_installed"


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


def register_rpg_observer_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.post(
        "/api/rpg/map-instances/{map_instance_id}/observers/{observer_actor_id}/observe",
        include_in_schema=False,
    )
    async def rpg_observe_map(
        map_instance_id: str,
        observer_actor_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        expected = payload.pop("expected_knowledge_revision", None)
        try:
            policy = ObserverPerceptionPolicy.model_validate(payload)
            return observe_campaign_map(
                map_instance_id,
                observer_actor_id=observer_actor_id,
                policy=policy,
                expected_knowledge_revision=(
                    int(expected) if expected is not None else None
                ),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.get(
        "/api/rpg/map-instances/{map_instance_id}/observers/{observer_actor_id}/projection",
        include_in_schema=False,
    )
    def rpg_observer_projection(
        map_instance_id: str,
        observer_actor_id: str,
        _known_revision: int | None = Query(default=None, ge=0),
    ) -> dict[str, Any]:
        try:
            return load_campaign_observer_projection(
                map_instance_id,
                observer_actor_id=observer_actor_id,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise


def install_rpg_observer_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_observer_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
