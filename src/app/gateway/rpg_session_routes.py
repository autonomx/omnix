"""Clean RPG session launch and save-management gateway routes."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, HTTPException

from app.rpg.session.loadout import RpgLoadoutActionRequest, apply_loadout_action
from app.rpg.session.new_game import (
    RpgNewGameRequest,
    RpgRenameSessionRequest,
    continue_rpg_session,
    create_new_game_session,
    delete_rpg_session,
    list_rpg_presets,
    rename_rpg_session,
    start_rpg_preset,
)
from app.rpg.session.service import list_sessions, load_session

_ROUTE_SENTINEL = "_omnix_rpg_session_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_session_route_hook_installed"


def _raise_for_error(payload: dict[str, Any], *, not_found_errors: set[str] | None = None) -> dict[str, Any]:
    if payload.get("ok") is not False:
        return payload
    error = str(payload.get("error") or "rpg_session_error")
    status_code = 404 if error in (not_found_errors or set()) else 400
    raise HTTPException(status_code=status_code, detail=payload)


def register_rpg_session_routes(app: FastAPI) -> None:
    """Attach the typed RPG session API once.

    These routes are intentionally synchronous and should not call LLM, image, TTS,
    or queued-turn workers. They expose the stable REST contract used by the RPG
    launcher and loadout affordances while the older /api/rpg/session/*
    compatibility surface remains available for existing callers.
    """
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get("/api/rpg/presets", tags=["rpg-session"])
    async def rpg_presets() -> dict[str, Any]:
        return list_rpg_presets()

    @app.post("/api/rpg/presets/{preset_id}/start", tags=["rpg-session"])
    async def rpg_start_preset(preset_id: str) -> dict[str, Any]:
        return _raise_for_error(start_rpg_preset(preset_id), not_found_errors={"unknown_rpg_preset"})

    @app.get("/api/rpg/sessions", tags=["rpg-session"])
    async def rpg_sessions() -> dict[str, Any]:
        return {"ok": True, "sessions": list_sessions() or []}

    @app.get("/api/rpg/sessions/{session_id}", tags=["rpg-session"])
    async def rpg_read_session(session_id: str) -> dict[str, Any]:
        session = load_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail={"ok": False, "error": "session_not_found", "session_id": session_id})
        return {"ok": True, "session_id": session_id, "session": session, "game": session.get("state", {})}

    @app.post("/api/rpg/new-game", tags=["rpg-session"])
    async def rpg_new_game(request: RpgNewGameRequest) -> dict[str, Any]:
        return create_new_game_session(request)

    @app.post("/api/rpg/sessions/{session_id}/continue", tags=["rpg-session"])
    async def rpg_continue_session(session_id: str) -> dict[str, Any]:
        return _raise_for_error(continue_rpg_session(session_id), not_found_errors={"session_not_found"})

    @app.post("/api/rpg/sessions/{session_id}/rename", tags=["rpg-session"])
    async def rpg_rename_session(session_id: str, request: RpgRenameSessionRequest) -> dict[str, Any]:
        name = request.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail={"ok": False, "error": "missing_session_name", "session_id": session_id})
        return _raise_for_error(rename_rpg_session(session_id, name), not_found_errors={"session_not_found"})

    @app.post("/api/rpg/sessions/{session_id}/delete", tags=["rpg-session"])
    async def rpg_delete_session(session_id: str) -> dict[str, Any]:
        return _raise_for_error(delete_rpg_session(session_id), not_found_errors={"session_not_found"})

    @app.post("/api/rpg/sessions/{session_id}/loadout-action", tags=["rpg-session"])
    async def rpg_loadout_action(session_id: str, request: RpgLoadoutActionRequest) -> dict[str, Any]:
        return _raise_for_error(apply_loadout_action(session_id, request), not_found_errors={"session_not_found"})


def install_rpg_session_route_hook() -> None:
    """Install the route registration hook for the local gateway app.

    The gateway is still a single-file FastAPI app. This hook keeps the new typed
    RPG session API modular without disturbing the existing compatibility routes;
    once gateway.main is split into route modules, it can call
    register_rpg_session_routes(app) directly and this hook can be removed.
    """
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_rpg_session_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
