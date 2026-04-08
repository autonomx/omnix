"""Canonical RPG session routes.

All gameplay turn traffic should go through this module.
Legacy /api/rpg/games* routes are retired from active registration.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from flask import Blueprint, Response, jsonify, request

from app.rpg.session.runtime import (
    apply_turn,
    build_frontend_bootstrap_payload,
    load_runtime_session,
    save_runtime_session,
)

rpg_session_bp = Blueprint("rpg_session_bp", __name__)




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


def _get_json() -> Dict[str, Any]:
    """Get JSON body from Flask request, returning empty dict on failure."""
    body = request.get_json(silent=True) or {}
    return body if isinstance(body, dict) else {}


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


@rpg_session_bp.route("/api/rpg/session/list", methods=["POST"])
def list_rpg_sessions():
    """List all RPG sessions for the settings panel."""
    from app.rpg.session.service import list_sessions

    sessions = list_sessions() or []
    resp = jsonify({"ok": True, "sessions": sessions})

    return resp


@rpg_session_bp.route("/api/rpg/session/get", methods=["POST"])
def get_rpg_session():
    data = _get_json()
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_runtime_session(session_id)
    if session is None:
        return jsonify({"ok": False, "error": "session_not_found"}), 404
    payload = build_frontend_bootstrap_payload(session)
    payload["ok"] = True
    payload["game"] = payload
    resp = jsonify(payload)

    return resp


@rpg_session_bp.route("/api/rpg/session/update", methods=["POST"])
def update_rpg_session():
    data = _get_json()
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_runtime_session(session_id)
    if session is None:
        return jsonify({"ok": False, "error": "session_not_found"}), 404

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
    resp = jsonify(payload)

    return resp


@rpg_session_bp.route("/api/rpg/session/delete", methods=["POST"])
def delete_rpg_session():
    data = _get_json()
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_runtime_session(session_id)
    if session is None:
        return jsonify({"ok": False, "error": "session_not_found"}), 404
    manifest = _safe_dict(session.get("manifest"))
    manifest["archived"] = True
    manifest["status"] = "archived"
    session["manifest"] = manifest
    save_runtime_session(session)
    resp = jsonify({"ok": True})

    return resp


@rpg_session_bp.route("/api/rpg/session/turn", methods=["POST"])
def execute_rpg_session_turn():
    data = _get_json()
    session_id = _safe_str(data.get("session_id")).strip()
    player_input = _safe_str(data.get("input")).strip()
    action = _safe_dict(data.get("action"))

    if not session_id:
        return jsonify({"ok": False, "error": "session_id_required"}), 400
    if not player_input:
        return jsonify({"ok": False, "error": "input_required"}), 400

    result = apply_turn(session_id, player_input, action=action)
    if not result.get("ok"):
        if result.get("error") == "session_not_found":
            return jsonify({"ok": False, "error": "session_not_found"}), 404
        return jsonify({"ok": False, "error": "turn_failed", "details": result}), 500

    payload = _build_turn_payload(result)
    resp = jsonify(payload)

    return resp


@rpg_session_bp.route("/api/rpg/session/turn/stream", methods=["POST"])
def execute_rpg_session_turn_stream():
    data = _get_json()
    session_id = _safe_str(data.get("session_id")).strip()
    player_input = _safe_str(data.get("input")).strip()
    action = _safe_dict(data.get("action"))

    sse_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    if not session_id:
        return Response(
            _sse({"type": "error", "error": "session_id_required"}),
            status=400,
            mimetype="text/event-stream",
            headers=sse_headers,
        )

    if not player_input:
        return Response(
            _sse({"type": "error", "error": "input_required"}),
            status=400,
            mimetype="text/event-stream",
            headers=sse_headers,
        )

    result = apply_turn(session_id, player_input, action=action)

    if not result.get("ok"):
        err = _safe_str(result.get("error") or "turn_failed")
        status = 404 if result.get("error") == "session_not_found" else 500
        return Response(
            _sse({"type": "error", "error": err}),
            status=status,
            mimetype="text/event-stream",
            headers=sse_headers,
        )

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

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers=sse_headers,
    )