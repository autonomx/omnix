"""Management endpoints for RPG sessions."""
from __future__ import annotations

import datetime
import threading

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


def _semantic_capture_already_active(runtime_state: dict) -> bool:
    runtime_state = _safe_dict(runtime_state)
    capture = _safe_dict(runtime_state.get("semantic_capture_worker"))
    return _safe_str(capture.get("status")).strip().lower() == "running"


def _player_turn_request_active(runtime_state: dict) -> bool:
    marker = _safe_dict(_safe_dict(runtime_state).get("active_player_turn_request"))
    status = _safe_str(marker.get("status")).strip().lower()
    if status not in {"starting", "applying", "streaming"}:
        return False
    return not bool(_safe_str(marker.get("completed_at")).strip())


def _parse_iso_datetime(value: str) -> datetime.datetime | None:
    value = _safe_str(value).strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed
    except Exception:
        return None


def _seconds_since_iso(value: str) -> float:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return 0.0
    return max(0.0, (datetime.datetime.now(datetime.timezone.utc) - parsed).total_seconds())


def _player_turn_background_quiet_active(runtime_state: dict, *, max_processing_age_s: float = 45.0) -> bool:
    """Return true while background/idle work should yield to a player turn."""
    runtime_state = _safe_dict(runtime_state)
    if _player_turn_request_active(runtime_state):
        return True

    artifacts = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))
    jobs_by_turn = _safe_dict(runtime_state.get("narration_jobs_by_turn"))
    jobs = list(jobs_by_turn.values()) if jobs_by_turn else _safe_list(runtime_state.get("narration_jobs"))
    for raw_job in jobs:
        job = _safe_dict(raw_job)
        if (_safe_str(job.get("job_kind")).strip() or "player_turn") != "player_turn":
            continue
        status = _safe_str(job.get("status")).strip().lower()
        if status not in {"queued", "processing", "retrying"}:
            continue
        turn_id = _safe_str(job.get("turn_id")).strip()
        if turn_id and _safe_dict(artifacts.get(turn_id)):
            continue
        if status in {"processing", "retrying"}:
            age_s = _seconds_since_iso(job.get("started_at") or job.get("updated_at") or job.get("created_at"))
            if age_s and age_s > max_processing_age_s:
                continue
        return True
    return False


def _quiet_idle_tick_payload(session: dict, reason: str = "player_turn_quiet") -> dict:
    runtime_state = _safe_dict(_safe_dict(session).get("runtime_state"))
    return {
        "ok": True,
        "updates": [],
        "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "ticks_applied": 0,
        "idle_debug_trace": {
            "idle_suppressed": True,
            "reason": _safe_str(reason or "player_turn_quiet"),
        },
        "idle_seconds": 0,
        "idle_gate_open": False,
        "settings": _normalize_runtime_settings(_safe_dict(runtime_state.get("runtime_settings"))),
        "semantic_capture_background": False,
        "player_turn_quiet": True,
    }


def _mark_semantic_capture_worker(session_id: str, status: str, reason: str = "") -> None:
    try:
        session = load_runtime_session(session_id)
        if session is None:
            return
        runtime_state = _safe_dict(session.get("runtime_state"))
        runtime_state["semantic_capture_worker"] = {
            "status": _safe_str(status),
            "reason": _safe_str(reason),
        }
        session["runtime_state"] = runtime_state
        save_runtime_session(session)
    except Exception:
        pass


def _run_semantic_capture_background(session_id: str, reason: str = "idle_tick") -> bool:
    """Schedule semantic/ambient LLM capture off the request path.

    Idle semantic capture can call the LLM.  Running it inside the heartbeat route
    competes with player-turn narration and makes the UI feel blocked.  The
    background worker keeps the world alive without delaying the player-facing
    response path.
    """
    session_id = _safe_str(session_id).strip()
    if not session_id:
        return False
    try:
        session = load_runtime_session(session_id)
    except Exception as exc:
        print("[RPG][idle_tick] semantic background load failed:", repr(exc))
        return False
    if session is None:
        return False
    runtime_state = _safe_dict(session.get("runtime_state"))
    if _player_turn_background_quiet_active(runtime_state):
        print("[RPG][idle_tick] semantic capture skipped: player turn quiet")
        return False
    if _semantic_capture_already_active(runtime_state):
        return False

    runtime_state["semantic_capture_worker"] = {
        "status": "running",
        "reason": _safe_str(reason),
    }
    session["runtime_state"] = runtime_state
    try:
        save_runtime_session(session)
    except Exception:
        pass

    def _worker() -> None:
        try:
            captured_session = load_runtime_session(session_id)
            if captured_session is None:
                return
            rt = _safe_dict(captured_session.get("runtime_state"))
            print("ROUTE recorded_semantic_llm_proposals =", rt.get("recorded_semantic_llm_proposals"))
            print("ROUTE recorded_semantic_llm_prompt present =", bool(rt.get("recorded_semantic_llm_prompt")))
            print("ROUTE recorded_semantic_llm_raw_output present =", bool(rt.get("recorded_semantic_llm_raw_output")))
            captured_session = capture_semantic_state_change_proposals_for_session(captured_session)
            rt = _safe_dict(captured_session.get("runtime_state"))
            rt["semantic_capture_worker"] = {
                "status": "completed",
                "reason": _safe_str(reason),
            }
            captured_session["runtime_state"] = rt
            try:
                save_runtime_session(captured_session)
            except Exception:
                pass
        except Exception as exc:
            print("[RPG][idle_tick] background semantic proposal capture failed:", repr(exc))
            _mark_semantic_capture_worker(session_id, "failed", repr(exc))

    threading.Thread(
        target=_worker,
        name=f"rpg-idle-semantic-capture:{session_id}",
        daemon=True,
    ).start()
    return True


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

    if _player_turn_background_quiet_active(_safe_dict(session.get("runtime_state"))):
        return _quiet_idle_tick_payload(session)

    # Semantic capture may call the LLM, so schedule it after accepting the
    # heartbeat instead of blocking this HTTP request.
    try:
        _run_semantic_capture_background(session_id, reason="pre_idle_tick")
    except Exception as exc:
        print("[RPG][idle_tick] semantic proposal scheduling failed:", repr(exc))

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
            if (
                not _player_turn_request_active(rt)
                and not _safe_list(rt.get("recorded_semantic_llm_proposals"))
            ):
                _run_semantic_capture_background(session_id, reason="post_idle_tick")

        return {
            "ok": True,
            "updates": _safe_list(result.get("updates")),
            "latest_seq": int(result.get("latest_seq", 0) or 0),
            "ticks_applied": int(result.get("ticks_applied", 0) or 0),
            "idle_debug_trace": _safe_dict(result.get("idle_debug_trace")),
            "idle_seconds": result.get("idle_seconds", 0) or 0,
            "idle_gate_open": bool(result.get("idle_gate_open", False)),
            "settings": _safe_dict(result.get("settings")),
            "semantic_capture_background": True,
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
