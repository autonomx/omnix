"""Canonical RPG session routes.

All gameplay turn traffic should go through this module.
Legacy /api/rpg/games* routes are retired from active registration.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.rpg.session.runtime import (
    apply_turn,
    build_frontend_bootstrap_payload,
    load_runtime_session,
    save_runtime_session,
)

rpg_session_bp = APIRouter()




def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _normalize_turn_request(data: Dict[str, Any]) -> Dict[str, Any]:
    data = _safe_dict(data)
    player_input = _safe_str(data.get("input")).strip()
    action = _safe_dict(data.get("action"))

    if not action and player_input.startswith("{") and player_input.endswith("}"):
        try:
            parsed = json.loads(player_input)
            action = _safe_dict(parsed)
        except Exception:
            action = {}

    if action and not player_input:
        action_type = _safe_str(action.get("action_type") or action.get("action")).strip().lower()
        npc_name = _safe_str(action.get("npc_name")).strip()
        npc_id = _safe_str(action.get("npc_id") or action.get("target_id")).strip()
        label = npc_name or npc_id or "them"
        if action_type == "talk":
            player_input = f"Talk to {label}"
        elif action_type == "threaten":
            player_input = f"Threaten {label}"
        elif action_type == "persuade":
            player_input = f"Talk to {label}"
        elif action_type == "intimidate":
            player_input = f"Threaten {label}"
        else:
            player_input = action_type.replace("_", " ").strip()

    return {
        "session_id": _safe_str(data.get("session_id")).strip(),
        "player_input": player_input,
        "action": action,
    }






def _build_turn_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build the canonical turn response payload from an apply_turn result."""
    raw_payload = _safe_dict(result.get("payload"))
    session = _safe_dict(result.get("session"))
    sim = _safe_dict(session.get("simulation_state"))
    player_state = _safe_dict(sim.get("player_state"))
    stats = _safe_dict(player_state.get("stats"))
    skills = _safe_dict(player_state.get("skills"))
    inventory_state = _safe_dict(player_state.get("inventory_state"))
    equipment = _safe_dict(inventory_state.get("equipment"))

    runtime_state = _safe_dict(session.get("runtime_state"))
    scene_state = _safe_dict(runtime_state.get("current_scene"))
    memory = _safe_dict(sim.get("memory"))

    payload: Dict[str, Any] = {
        "success": True,
        "session_id": _safe_str(raw_payload.get("session_id") or session.get("session_id")),
        "title": _safe_str(raw_payload.get("title")),
        "opening": _safe_str(raw_payload.get("opening")),
        "narration": _safe_str(raw_payload.get("narration")),
        # Player block
        "player": {
            "stats": stats,
            "skills": skills,
            "level": int(player_state.get("level", 1) or 1),
            "xp": int(player_state.get("xp", 0) or 0),
            "xp_to_next": int(player_state.get("xp_to_next", 0) or 0),
            "inventory_state": inventory_state,
            "equipment": equipment,
            "nearby_npc_ids": _safe_list(player_state.get("nearby_npc_ids")),
            "available_checks": _safe_list(player_state.get("available_checks")),
        },
        # NPC blocks
        "nearby_npcs": _safe_list(raw_payload.get("nearby_npcs") or sim.get("nearby_npcs")),
        "known_npcs": _safe_list(raw_payload.get("known_npcs") or sim.get("known_npcs")),
        # Scene block
        "scene": {
            "scene_id": _safe_str(scene_state.get("scene_id")),
            "items": _safe_list(scene_state.get("items")),
            "available_checks": _safe_list(scene_state.get("available_checks")),
            "present_npc_ids": _safe_list(scene_state.get("present_npc_ids")),
        },
        # Memory block
        "memory_summary": {
            "important_memory": _safe_list(memory.get("important_memory")),
            "recent_memory": _safe_list(memory.get("recent_memory")),
            "recent_world_events": _safe_list(memory.get("recent_world_events")),
        },
        # Progression
        "combat_result": raw_payload.get("combat_result"),
        "xp_result": raw_payload.get("xp_result"),
        "skill_xp_result": raw_payload.get("skill_xp_result"),
        "level_up": _safe_list(raw_payload.get("level_up")),
        "skill_level_ups": _safe_list(raw_payload.get("skill_level_ups")),
        # Presentation
        "presentation": _safe_dict(raw_payload.get("presentation")),
    }
    return payload


@rpg_session_bp.post("/api/rpg/session/list")
def list_rpg_sessions():
    """List all RPG sessions for the settings panel."""
    from app.rpg.session.service import list_sessions

    sessions = list_sessions() or []
    return {"ok": True, "sessions": sessions}


@rpg_session_bp.post("/api/rpg/session/get")
async def get_rpg_session(request: Request):
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)
    payload = build_frontend_bootstrap_payload(session)
    payload["ok"] = True
    payload["game"] = payload

    return payload


@rpg_session_bp.post("/api/rpg/session/update")
async def update_rpg_session(request: Request):
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)

    manifest = _safe_dict(session.get("manifest"))
    runtime_state = _safe_dict(session.get("runtime_state"))

    title = _safe_str(data.get("title")).strip()
    if title:
        manifest["title"] = title

    voice_assignments = data.get("voice_assignments")
    if isinstance(voice_assignments, dict):
        runtime_state["voice_assignments"] = dict(voice_assignments)

    session["manifest"] = manifest
    session["runtime_state"] = runtime_state
    session = save_runtime_session(session)
    payload = build_frontend_bootstrap_payload(session)
    payload["ok"] = True

    return payload


@rpg_session_bp.post("/api/rpg/session/delete")
async def delete_rpg_session(request: Request):
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)
    manifest = _safe_dict(session.get("manifest"))
    manifest["archived"] = True
    manifest["status"] = "archived"
    session["manifest"] = manifest
    save_runtime_session(session)

    return {"ok": True}


@rpg_session_bp.post("/api/rpg/session/turn")
async def execute_rpg_session_turn(request: Request):
    data = await request.json()
    normalized = _normalize_turn_request(data)
    session_id = _safe_str(normalized.get("session_id")).strip()
    player_input = _safe_str(normalized.get("player_input")).strip()
    action = _safe_dict(normalized.get("action"))

    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    result = apply_turn(session_id, player_input, action=action)
    if not result.get("ok"):
        if result.get("error") == "session_not_found":
            return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)
        return JSONResponse({"ok": False, "error": "turn_failed", "details": result}, status_code=500)

    payload = _build_turn_payload(result)

    return payload


@rpg_session_bp.post("/api/rpg/session/turn/stream")
async def execute_rpg_session_turn_stream(request: Request):
    data = await request.json()
    normalized = _normalize_turn_request(data)
    session_id = _safe_str(normalized.get("session_id")).strip()
    player_input = _safe_str(normalized.get("player_input")).strip()
    action = _safe_dict(normalized.get("action"))

    sse_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    if not session_id:
        def error_gen():
            yield _sse({"type": "error", "error": "session_id_required"})
        return StreamingResponse(error_gen(), status_code=400, media_type="text/event-stream", headers=sse_headers)

    result = apply_turn(session_id, player_input, action=action)

    if not result.get("ok"):
        err = _safe_str(result.get("error") or "turn_failed")
        status = 404 if result.get("error") == "session_not_found" else 500
        def error_gen():
            yield _sse({"type": "error", "error": err})
        return StreamingResponse(error_gen(), status_code=status, media_type="text/event-stream", headers=sse_headers)

    payload = _build_turn_payload(result)
    narration = _safe_str(payload.get("narration"))

    def generate():
        words = narration.split()
        for idx, word in enumerate(words):
            chunk = word + (" " if idx < len(words) - 1 else "")
            yield _sse({"type": "token", "text": chunk})

        final_payload = dict(payload)
        final_payload["type"] = "done"
        final_payload["ok"] = True
        yield _sse(final_payload)

    return StreamingResponse(generate(), media_type="text/event-stream", headers=sse_headers)