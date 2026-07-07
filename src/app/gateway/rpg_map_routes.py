"""Cache-aware RPG map definition, overlay, and authoritative action routes."""

from __future__ import annotations

from functools import wraps
import json
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from app.rpg.map_actions import MapActionError, MapActionRequest, apply_map_action, map_action_error_payload
from app.rpg.map_living_overlay import project_living_map_markers
from app.rpg.map_living_state import merge_living_overlay_payload, project_living_map_state
from app.rpg.map_overlay_projection import merge_dynamic_overlay_payload, project_dynamic_map_overlay
from app.rpg.map_projection import project_session_map_overlay
from app.rpg.map_repository import MapDefinitionNotFound, default_map_repository
from app.rpg.map_serialization import canonical_map_json
from app.rpg.map_world_integration import MapWorldIntegrationError, map_repository_for_session
from app.rpg.session.service import load_session, save_session

_ROUTE_SENTINEL = "_omnix_rpg_map_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_map_route_hook_installed"
MAP_DEFINITION_CACHE_CONTROL = "public, max-age=3600, immutable"
MAP_OVERLAY_CACHE_CONTROL = "no-store"
_ALLOWED_ACTIONS = {"travel", "inspect", "enter", "talk", "trade"}


def register_rpg_map_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get("/api/rpg/maps/{map_id}", tags=["rpg-map"], include_in_schema=False)
    def rpg_map_definition(
        map_id: str,
        request: Request,
        known_definition_revision: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
    ) -> Response:
        repository = default_map_repository()
        if session_id:
            repository = _session_repository(_load_session_or_404(session_id))
        try:
            definition = repository.get(map_id)
        except MapDefinitionNotFound as exc:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "map_definition_not_found", "map_id": map_id}) from exc
        return _definition_response(definition, request, known_definition_revision)

    @app.get("/api/rpg/sessions/{session_id}/maps/{map_id}", tags=["rpg-map"], include_in_schema=False)
    def rpg_session_map_definition(
        session_id: str,
        map_id: str,
        request: Request,
        known_definition_revision: str | None = Query(default=None),
    ) -> Response:
        session = _load_session_or_404(session_id)
        repository = _session_repository(session)
        try:
            definition = repository.get(map_id)
        except MapDefinitionNotFound as exc:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "map_definition_not_found", "map_id": map_id}) from exc
        return _definition_response(definition, request, known_definition_revision)

    @app.get("/api/rpg/sessions/{session_id}/maps/{map_id}/overlay", tags=["rpg-map"], include_in_schema=False)
    def rpg_map_overlay(session_id: str, map_id: str) -> Response:
        session = _load_session_or_404(session_id)
        definition, overlay = _definition_and_overlay(session, map_id)
        overlay_payload = _project_overlay_payload(session, definition, overlay)
        etag = _etag(f"{overlay.definition_revision}:{overlay.overlay_revision}:{overlay.session_turn_index}")
        return JSONResponse({
            "ok": True,
            "map_id": map_id,
            "definition_revision": overlay.definition_revision,
            "overlay_revision": overlay.overlay_revision,
            "session_turn_index": overlay.session_turn_index,
            "overlay": overlay_payload,
        }, headers={"Cache-Control": MAP_OVERLAY_CACHE_CONTROL, "ETag": etag})

    @app.post("/api/rpg/sessions/{session_id}/maps/{map_id}/map-actions", tags=["rpg-map"], include_in_schema=False)
    async def rpg_map_action(session_id: str, map_id: str, request: Request) -> Response:
        session = _load_session_or_404(session_id)
        action_request = _map_action_request(await request.json())
        repository = _session_repository(session)
        try:
            result = apply_map_action(session, map_id, action_request, repository)
        except MapDefinitionNotFound as exc:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "map_definition_not_found", "map_id": map_id}) from exc
        except MapActionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=map_action_error_payload(exc, map_id)) from exc

        result_session = result.get("session")
        saved = save_session(result_session, compact=False) if isinstance(result_session, dict) else session
        active_map_id = str(result.get("map_id") or map_id)
        definition, overlay = _definition_and_overlay(saved, active_map_id)
        overlay_payload = _project_overlay_payload(saved, definition, overlay)
        return JSONResponse({
            "ok": True,
            "session_id": session_id,
            "map_id": active_map_id,
            "definition_revision": definition.definition_revision,
            "overlay_revision": overlay.overlay_revision,
            "session_turn_index": overlay.session_turn_index,
            "idempotent": bool(result.get("idempotent")),
            "action_result": result.get("action_result", {}),
            "session": saved,
            "game": saved.get("state", {}),
            "overlay": overlay_payload,
        }, headers={"Cache-Control": MAP_OVERLAY_CACHE_CONTROL})


def _project_overlay_payload(session: dict[str, Any], definition: Any, overlay: Any) -> dict[str, object]:
    dynamic = project_dynamic_map_overlay(session, definition)
    payload = merge_dynamic_overlay_payload(_payload(overlay), dynamic)
    markers = project_living_map_markers(session, definition)
    living = project_living_map_state(session, definition)
    return merge_living_overlay_payload(payload, markers.markers, living)


def _definition_response(definition: Any, request: Request, known_revision: str | None) -> Response:
    etag = _etag(definition.definition_revision)
    headers = {"Cache-Control": MAP_DEFINITION_CACHE_CONTROL, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse({
        "ok": True,
        "map_id": definition.map_id,
        "definition_revision": definition.definition_revision,
        "definition": _payload(definition) if known_revision != definition.definition_revision else None,
    }, headers=headers)


def _load_session_or_404(session_id: str) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found", "session_id": session_id})
    return session


def _session_repository(session: dict[str, Any]) -> Any:
    try:
        return map_repository_for_session(session)
    except MapWorldIntegrationError as exc:
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error": exc.code, "reason": exc.detail or exc.code},
        ) from exc


def _definition_and_overlay(session: dict[str, Any], map_id: str) -> tuple[Any, Any]:
    repository = _session_repository(session)
    try:
        definition = repository.get(map_id)
        overlay = project_session_map_overlay(session, map_id, repository)
        return definition, overlay
    except MapDefinitionNotFound as exc:
        raise HTTPException(status_code=404, detail={"ok": False, "error": "map_definition_not_found", "map_id": map_id}) from exc


def _map_action_request(raw: object) -> MapActionRequest:
    payload = raw if isinstance(raw, dict) else {}
    action = str(payload.get("action") or "").strip().lower()
    target_object_id = str(payload.get("target_object_id") or "").strip()
    definition_revision = str(payload.get("definition_revision") or "").strip()
    try:
        overlay_revision = int(payload.get("overlay_revision"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail={"ok": False, "error": "invalid_overlay_revision"}) from exc
    if action not in _ALLOWED_ACTIONS:
        raise HTTPException(status_code=422, detail={"ok": False, "error": "invalid_map_action"})
    if not target_object_id or not definition_revision or overlay_revision < 0:
        raise HTTPException(status_code=422, detail={"ok": False, "error": "invalid_map_action_request"})
    return MapActionRequest(
        action=action,  # type: ignore[arg-type]
        target_object_id=target_object_id,
        definition_revision=definition_revision,
        overlay_revision=overlay_revision,
        route_id=str(payload.get("route_id") or "").strip() or None,
        client_action_id=str(payload.get("client_action_id") or "").strip() or None,
    )


def _payload(value: object) -> Any:
    return json.loads(canonical_map_json(value))


def _etag(value: str) -> str:
    return f'"{value}"'


def install_rpg_map_route_hook() -> None:
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
