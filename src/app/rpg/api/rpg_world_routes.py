"""World-event and world-behavior endpoints for RPG sessions."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.rpg.api.rpg_session_payloads import _safe_dict, _safe_list, _safe_str
from app.rpg.session.runtime import load_runtime_session, save_runtime_session


async def get_rpg_session_world_events(request: Request):
    """Return cached recent world event rows from runtime state."""
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    session = load_runtime_session(session_id)
    if session is None:
        # This endpoint is polled by the live UI while sessions are still being
        # created/loaded. Treat a missing session as an empty polling result so
        # the browser console does not report route-looking 404 noise.
        return {
            "ok": False,
            "error": "session_not_found",
            "recent_world_event_rows": [],
            "player_world_view_rows": [],
            "player_local_world_view_rows": [],
            "player_global_world_view_rows": [],
            "debug_world_events": {
                "recent_world_event_rows_count": 0,
                "player_world_view_rows_count": 0,
                "player_local_world_view_rows_count": 0,
                "player_global_world_view_rows_count": 0,
                "recent_world_event_row_ids": [],
            },
        }

    simulation_state = _safe_dict(session.get("simulation_state"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    recent_rows = _safe_list(runtime_state.get("recent_world_event_rows"))[-48:]

    from app.rpg.analytics.world_events import (
        build_player_global_world_view_rows,
        build_player_local_world_view_rows,
        build_player_world_view_rows,
    )
    player_world_view_rows = build_player_world_view_rows(simulation_state, runtime_state)
    player_local_world_view_rows = build_player_local_world_view_rows(simulation_state, runtime_state)
    player_global_world_view_rows = build_player_global_world_view_rows(simulation_state, runtime_state)

    return {
        "ok": True,
        "recent_world_event_rows": recent_rows,
        "player_world_view_rows": player_world_view_rows,
        "player_local_world_view_rows": player_local_world_view_rows,
        "player_global_world_view_rows": player_global_world_view_rows,
        "debug_world_events": {
            "recent_world_event_rows_count": len(recent_rows),
            "player_world_view_rows_count": len(player_world_view_rows),
            "player_local_world_view_rows_count": len(player_local_world_view_rows),
            "player_global_world_view_rows_count": len(player_global_world_view_rows),
            "recent_world_event_row_ids": [_safe_str(r.get("event_id")) for r in recent_rows],
        },
    }


async def get_world_behavior(request: Request):
    """Return effective world behavior config for a session."""
    from app.rpg.session.runtime import get_effective_world_behavior

    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)

    effective = get_effective_world_behavior(session)
    setup_config = _safe_dict(_safe_dict(session.get("setup_payload")).get("world_behavior"))
    override = _safe_dict(_safe_dict(session.get("runtime_state")).get("world_behavior_override"))

    return {
        "ok": True,
        "effective": effective,
        "setup_config": setup_config,
        "override": override,
    }


async def update_world_behavior(request: Request):
    """Update in-game world behavior overrides."""
    from app.rpg.creator.schema import (
        _WORLD_BEHAVIOR_ENUMS,
    )
    from app.rpg.session.runtime import get_effective_world_behavior

    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    changes = _safe_dict(data.get("changes"))

    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)

    runtime_state = _safe_dict(session.get("runtime_state"))
    override = dict(_safe_dict(runtime_state.get("world_behavior_override")))

    for key, allowed in _WORLD_BEHAVIOR_ENUMS.items():
        val = changes.get(key)
        if isinstance(val, str) and val.strip().lower() in allowed:
            override[key] = val.strip().lower()

    runtime_state["world_behavior_override"] = override
    session["runtime_state"] = runtime_state
    session = save_runtime_session(session)

    effective = get_effective_world_behavior(session)

    return {
        "ok": True,
        "effective": effective,
        "override": override,
    }


def register_rpg_world_routes(router: APIRouter) -> None:
    router.add_api_route("/api/rpg/session/world_events", get_rpg_session_world_events, methods=["POST"])
    router.add_api_route("/api/rpg/session/world_behavior", get_world_behavior, methods=["POST"])
    router.add_api_route("/api/rpg/session/world_behavior/update", update_world_behavior, methods=["POST"])
