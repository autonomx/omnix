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


async def _get_json(request: Request) -> Dict[str, Any]:
    """Get JSON body from request, returning empty dict on failure."""
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def _jsonify(data: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    """FastAPI-compatible JSON response."""
    return JSONResponse(content=data, status_code=status_code)


@rpg_session_bp.post("/api/rpg/session/list")
async def list_rpg_sessions():
    """List all RPG sessions for the settings panel."""
    from app.rpg.session.service import list_sessions

    sessions = list_sessions() or []
    return {"ok": True, "sessions": sessions}


@rpg_session_bp.post("/api/rpg/session/get")
async def get_rpg_session(request: Request):
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_runtime_session(session_id)
    if session is None:
        return _jsonify({"ok": False, "error": "session_not_found"}), 404
    payload = build_frontend_bootstrap_payload(session)
    payload["ok"] = True
    payload["game"] = payload
    return payload


@rpg_session_bp.post("/api/rpg/session/update")
async def update_rpg_session(request: Request):
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_runtime_session(session_id)
    if session is None:
        return _jsonify({"ok": False, "error": "session_not_found"}), 404

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
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
    session = load_runtime_session(session_id)
    if session is None:
        return _jsonify({"ok": False, "error": "session_not_found"}), 404
    manifest = _safe_dict(session.get("manifest"))
    manifest["status"] = "archived"
    session["manifest"] = manifest
    save_runtime_session(session)
    return {"ok": True}


@rpg_session_bp.post("/api/rpg/session/turn")
async def execute_rpg_session_turn(request: Request):
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
    player_input = _safe_str(data.get("input")).strip()
    action = _safe_dict(data.get("action"))

    if not session_id:
        return _jsonify({"ok": False, "error": "session_id_required"}), 400
    if not player_input:
        return _jsonify({"ok": False, "error": "input_required"}), 400

    result = apply_turn(session_id, player_input, action=action)
    if not result.get("ok"):
        if result.get("error") == "session_not_found":
            return _jsonify({"ok": False, "error": "session_not_found"}), 404
        return _jsonify({"ok": False, "error": "turn_failed", "details": result}), 500

    payload = _safe_dict(result.get("payload"))
    payload["ok"] = True
    return payload


@rpg_session_bp.post("/api/rpg/session/turn/stream")
async def execute_rpg_session_turn_stream(request: Request):
    data = await _get_json(request)
    session_id = _safe_str(data.get("session_id")).strip()
    player_input = _safe_str(data.get("input")).strip()
    action = _safe_dict(data.get("action"))

    if not session_id:

        def _sid_missing():
            yield f"data: {json.dumps({'type': 'error', 'error': 'session_id_required'})}\n\n"

        return StreamingResponse(_sid_missing(), media_type="text/event-stream", status_code=400)

    if not player_input:

        def _input_missing():
            yield f"data: {json.dumps({'type': 'error', 'error': 'input_required'})}\n\n"

        return StreamingResponse(_input_missing(), media_type="text/event-stream", status_code=400)

    result = apply_turn(session_id, player_input, action=action)

    if not result.get("ok"):

        def _failed():
            err = _safe_str(result.get("error") or "turn_failed")
            yield f"data: {json.dumps({'type': 'error', 'error': err})}\n\n"

        status = 404 if result.get("error") == "session_not_found" else 500
        return StreamingResponse(_failed(), media_type="text/event-stream", status_code=status)

    payload = _safe_dict(result.get("payload"))
    narration = _safe_str(payload.get("narration"))

    def generate():
        words = narration.split()
        for idx, word in enumerate(words):
            chunk = word + (" " if idx < len(words) - 1 else "")
            yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"

        final_payload = dict(payload)
        final_payload["type"] = "done"
        final_payload["ok"] = True
        yield f"data: {json.dumps(final_payload)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )