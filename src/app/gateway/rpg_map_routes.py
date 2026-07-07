"""Cache-aware read-only gateway routes for RPG map definitions and overlays."""

from __future__ import annotations

from functools import wraps
import json
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from app.rpg.map_projection import project_session_map_overlay
from app.rpg.map_repository import MapDefinitionNotFound, default_map_repository
from app.rpg.map_serialization import canonical_map_json
from app.rpg.session.service import load_session

_ROUTE_SENTINEL = "_omnix_rpg_map_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_map_route_hook_installed"
MAP_DEFINITION_CACHE_CONTROL = "public, max-age=3600, immutable"
MAP_OVERLAY_CACHE_CONTROL = "no-store"


def register_rpg_map_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get("/api/rpg/maps/{map_id}", tags=["rpg-map"], include_in_schema=False)
    def rpg_map_definition(
        map_id: str,
        request: Request,
        known_definition_revision: str | None = Query(default=None),
    ) -> Response:
        try:
            definition = default_map_repository().get(map_id)
        except MapDefinitionNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "error": "map_definition_not_found", "map_id": map_id},
            ) from exc
        etag = _etag(definition.definition_revision)
        headers = {"Cache-Control": MAP_DEFINITION_CACHE_CONTROL, "ETag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        include_definition = known_definition_revision != definition.definition_revision
        return JSONResponse(
            {
                "ok": True,
                "map_id": map_id,
                "definition_revision": definition.definition_revision,
                "definition": _payload(definition) if include_definition else None,
            },
            headers=headers,
        )

    @app.get(
        "/api/rpg/sessions/{session_id}/maps/{map_id}/overlay",
        tags=["rpg-map"],
        include_in_schema=False,
    )
    def rpg_map_overlay(session_id: str, map_id: str) -> Response:
        session = load_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "error": "session_not_found", "session_id": session_id},
            )
        try:
            overlay = project_session_map_overlay(session, map_id)
        except MapDefinitionNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "error": "map_definition_not_found", "map_id": map_id},
            ) from exc
        etag = _etag(f"{overlay.definition_revision}:{overlay.overlay_revision}:{overlay.session_turn_index}")
        return JSONResponse(
            {
                "ok": True,
                "map_id": map_id,
                "definition_revision": overlay.definition_revision,
                "overlay_revision": overlay.overlay_revision,
                "session_turn_index": overlay.session_turn_index,
                "overlay": _payload(overlay),
            },
            headers={"Cache-Control": MAP_OVERLAY_CACHE_CONTROL, "ETag": etag},
        )


def _payload(value: object) -> Any:
    return json.loads(canonical_map_json(value))


def _etag(value: str) -> str:
    return f'"{value}"'


def install_rpg_map_route_hook() -> None:
    """Install map routes before the gateway app is constructed."""

    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_rpg_map_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
