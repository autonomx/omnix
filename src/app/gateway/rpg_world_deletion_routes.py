"""Safe permanent-deletion routes for disposable RPG world projects."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request

from app.rpg.worlds.lifecycle_service import (
    delete_world_project,
    world_deletion_eligibility,
)

_ROUTE_SENTINEL = "_omnix_rpg_world_deletion_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_world_deletion_route_hook_installed"


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


def register_rpg_world_deletion_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get(
        "/api/rpg/worlds/{world_id}/deletion-eligibility",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_world_deletion_eligibility(world_id: str) -> dict[str, Any]:
        try:
            return world_deletion_eligibility(world_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.delete(
        "/api/rpg/worlds/{world_id}",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_delete_world(world_id: str, request: Request) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        confirmation_title = str(payload.get("confirmation_title") or "")
        if not confirmation_title:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "confirmation_title_required"},
            )
        if payload.get("acknowledge_permanent") is not True:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "permanent_deletion_acknowledgement_required"},
            )
        try:
            return delete_world_project(
                world_id,
                confirmation_title=confirmation_title,
                acknowledge_permanent=True,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise


def install_rpg_world_deletion_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_world_deletion_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
