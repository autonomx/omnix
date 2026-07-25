"""World genre-profile preview, editing, validation, and approval routes."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request

from app.rpg.worlds.profile_authoring import (
    approve_world_profile_review,
    read_world_profile_review,
    update_world_profile_review,
)

_ROUTE_SENTINEL = "_omnix_rpg_world_profile_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_world_profile_route_hook_installed"


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


def register_rpg_world_profile_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get(
        "/api/rpg/worlds/{world_id}/genre-profile",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_read_world_genre_profile(world_id: str) -> dict[str, Any]:
        try:
            return read_world_profile_review(world_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.patch(
        "/api/rpg/worlds/{world_id}/genre-profile",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_update_world_genre_profile(
        world_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        expected_revision = int(payload.get("expected_profile_revision") or 0)
        profile = payload.get("profile")
        if expected_revision < 1:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "expected_profile_revision_required"},
            )
        if not isinstance(profile, Mapping):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "genre_profile_required"},
            )
        try:
            return update_world_profile_review(
                world_id,
                expected_profile_revision=expected_revision,
                profile=profile,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/worlds/{world_id}/genre-profile/approve",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_approve_world_genre_profile(
        world_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        expected_revision = int(payload.get("expected_profile_revision") or 0)
        if expected_revision < 1:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "expected_profile_revision_required"},
            )
        try:
            return approve_world_profile_review(
                world_id,
                expected_profile_revision=expected_revision,
                approved_by=str(payload.get("approved_by") or "local-author"),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise


def install_rpg_world_profile_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_world_profile_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
