"""Management endpoints for RPG sessions."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.rpg.ai.semantic_state_change_capture import (
    capture_semantic_state_change_proposals_for_session,
)
from app.rpg.api.rpg_session_payloads import (
    _build_turn_payload,
    _deep_merge_dict,
    _safe_dict,
    _safe_list,
    _safe_str,
)
from app.rpg.economy.action_generator import build_menu_action
from app.rpg.session.runtime import (
    _normalize_runtime_settings,
    apply_turn,
    build_frontend_bootstrap_payload,
    load_runtime_session,
    save_runtime_session,
)


def _empty_idle_tick_payload(error: str = "session_not_found", details: object | None = None) -> dict:
    """Return the non-throwing contract expected by live UI polling."""
    payload = {
        "ok": False,
        "error": _safe_str(error or "idle_tick_failed"),
        "updates": [],
        "latest_seq": 0,
        "ticks_applied": 0,
        "idle_debug_trace": {},
        "idle_seconds": 0,
        "idle_gate_open": False,
        "settings": {},
    }
    if details is not None:
        payload["details"] = _safe_str(details)
    return payload


async def post_rpg_menu_action(request: Request):
    payload = await request.json() or {}
    session_id = _safe_str(payload.get("session_id"))
    action_payload = _safe_dict(payload.get("action"))

    if not session_id:
        return JSONResponse({"success": False, "error": "missing_session_id"}, status_code=400)
    if not action_payload:
        return JSONResponse({"success": False, "error": "missing_action"}, status_code=400)

    action = build_menu_action(action_payload)

    result = apply_turn(
        session_id=session_id,
        player_input="",
        action=action,
    )
    if not result.get("ok"):
        if result.get("error") == "session_not_found":
            return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)
        return JSONResponse({"ok": False, "error": "turn_failed", "details": result}, status_code=500)

    return _build_turn_payload(result)


def list_rpg_sessions():
    """List all RPG sessions for the settings panel."""
    from app.rpg.session.service import list_sessions

    sessions = list_sessions() or []
    return {"ok": True, "sessions": sessions}


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


async def update_rpg_session_settings(request: Request):
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    settings = _safe_dict(data.get("settings"))

    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)

    runtime_state = _safe_dict(session.get("runtime_state"))
    existing = _safe_dict(runtime_state.get("runtime_settings"))
    merged = _deep_merge_dict(existing, settings)
    runtime_state["runtime_settings"] = _normalize_runtime_settings(merged)
    session["runtime_state"] = runtime_state
    session = save_runtime_session(session)

    return {"ok": True, "settings": runtime_state["runtime_settings"]}


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


async def idle_tick_rpg_session(request: Request):
    """Advance world simulation by idle ticks without player action.

    This endpoint is called by a browser heartbeat. Apart from a genuinely
    malformed request with no session id, it must never surface runtime errors
    as HTTP 500s because that creates noisy, repeated console failures while a
    game is loading or a simulation subsystem is degraded.
    """
    try:
        data = await request.json()
    except Exception as exc:
        return _empty_idle_tick_payload("invalid_json", repr(exc))

    data = _safe_dict(data)
    session_id = _safe_str(data.get("session_id")).strip()
    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    try:
        count = int(data.get("count", 1) or 1)
    except Exception:
        count = 1
    count = max(1, min(count, 10))
    reason = _safe_str(data.get("reason") or "heartbeat").strip() or "heartbeat"

    try:
        session = load_runtime_session(session_id)
    except Exception as exc:
        print("[RPG][idle_tick] load_runtime_session failed:", repr(exc))
        return _empty_idle_tick_payload("session_load_failed", repr(exc))

    if session is None:
        # This endpoint is polled by the live UI while sessions are still being
        # created/loaded. Treat a missing session as an empty heartbeat result
        # so the browser console does not report route-looking 404 noise.
        return _empty_idle_tick_payload("session_not_found")

    try:
        rt = _safe_dict(session.get("runtime_state"))
        print("ROUTE recorded_semantic_llm_proposals =", rt.get("recorded_semantic_llm_proposals"))
        print("ROUTE recorded_semantic_llm_prompt present =", bool(rt.get("recorded_semantic_llm_prompt")))
        print("ROUTE recorded_semantic_llm_raw_output present =", bool(rt.get("recorded_semantic_llm_raw_output")))
        session = capture_semantic_state_change_proposals_for_session(session)
        try:
            save_runtime_session(session)
        except Exception:
            pass
    except Exception as exc:
        print("[RPG][idle_tick] semantic proposal capture failed:", repr(exc))

    try:
        from app.rpg.session.runtime import apply_idle_ticks

        result = _safe_dict(apply_idle_ticks(session_id, count, reason=reason))
    except Exception as exc:
        print("[RPG][idle_tick] apply_idle_ticks failed:", repr(exc))
        return _empty_idle_tick_payload("idle_tick_failed", repr(exc))

    try:
        if not result.get("ok"):
            err = _safe_str(result.get("error") or "idle_tick_failed")
            if err == "session_not_found":
                return _empty_idle_tick_payload("session_not_found")
            return _empty_idle_tick_payload(err)

        try:
            session = load_runtime_session(session_id)
        except Exception as exc:
            print("[RPG][idle_tick] post-idle load_runtime_session failed:", repr(exc))
            session = None
        if session:
            sim = _safe_dict(session.get("simulation_state"))
            rt = _safe_dict(session.get("runtime_state"))
            print("POST-IDLE SIM TICK =", sim.get("tick"), sim.get("current_tick"))
            print("POST-IDLE RUNTIME TICK =", rt.get("tick"))

        try:
            session = load_runtime_session(session_id)
        except Exception as exc:
            print("[RPG][idle_tick] final load_runtime_session failed:", repr(exc))
            session = None
        if session:
            runtime_state = _safe_dict(session.get("runtime_state"))
            if not _safe_list(runtime_state.get("recorded_semantic_llm_proposals")):
                rt = _safe_dict(session.get("runtime_state"))
                print("ROUTE recorded_semantic_llm_proposals =", rt.get("recorded_semantic_llm_proposals"))
                print("ROUTE recorded_semantic_llm_prompt present =", bool(rt.get("recorded_semantic_llm_prompt")))
                print("ROUTE recorded_semantic_llm_raw_output present =", bool(rt.get("recorded_semantic_llm_raw_output")))
                try:
                    session = capture_semantic_state_change_proposals_for_session(session)
                    try:
                        save_runtime_session(session)
                    except Exception:
                        pass
                except Exception as exc:
                    print("[RPG][idle_tick] post-idle semantic proposal capture failed:", repr(exc))

        return {
            "ok": True,
            "updates": _safe_list(result.get("updates")),
            "latest_seq": int(result.get("latest_seq", 0) or 0),
            "ticks_applied": int(result.get("ticks_applied", 0) or 0),
            "idle_debug_trace": _safe_dict(result.get("idle_debug_trace")),
            "idle_seconds": result.get("idle_seconds", 0) or 0,
            "idle_gate_open": bool(result.get("idle_gate_open", False)),
            "settings": _safe_dict(result.get("settings")),
        }
    except Exception as exc:
        print("[RPG][idle_tick] response contract failed:", repr(exc))
        return _empty_idle_tick_payload("idle_tick_response_failed", repr(exc))


def register_rpg_session_management_routes(router: APIRouter) -> None:
    router.add_api_route("/api/rpg/session/menu_action", post_rpg_menu_action, methods=["POST"])
    router.add_api_route("/api/rpg/session/list", list_rpg_sessions, methods=["POST"])
    router.add_api_route("/api/rpg/session/update", update_rpg_session, methods=["POST"])
    router.add_api_route("/api/rpg/session/settings", update_rpg_session_settings, methods=["POST"])
    router.add_api_route("/api/rpg/session/delete", delete_rpg_session, methods=["POST"])
    router.add_api_route("/api/rpg/session/idle_tick", idle_tick_rpg_session, methods=["POST"])
