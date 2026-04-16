"""Canonical RPG session routes.

All gameplay turn traffic should go through this module.
Legacy /api/rpg/games* routes are retired from active registration.
"""
from __future__ import annotations

import datetime
import json
import logging
import queue
import time
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.rpg.ai.semantic_state_change_capture import (
    capture_semantic_state_change_proposals_for_session,
)
from app.rpg.economy.action_generator import build_menu_action
from app.rpg.session.ambient_builder import (
    ensure_ambient_runtime_state,
    get_pending_ambient_updates,
)
from app.rpg.session.durable_store import CorruptSessionPayloadError
from app.rpg.session.narration_worker import (
    ensure_narration_worker_running,
    signal_narration_work,
    subscribe_narration_events,
    unsubscribe_narration_events,
)
from app.rpg.session.runtime import (
    _apply_turn_authoritative,
    _enqueue_narration_request,
    _normalize_runtime_settings,
    apply_idle_ticks,
    apply_resume_catchup,
    apply_turn,
    build_frontend_bootstrap_payload,
    load_runtime_session,
    process_next_narration_job,
    save_runtime_session,
)
from app.rpg.social.conversation_presentation import build_conversation_payload
from app.rpg.social.player_interventions import apply_player_intervention

rpg_session_bp = APIRouter()
_logger = logging.getLogger(__name__)




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


# Ensure narration worker is running on module load
ensure_narration_worker_running()


def _normalize_turn_request(data: Dict[str, Any]) -> Dict[str, Any]:
    data = _safe_dict(data)
    player_input = _safe_str(data.get("input")).strip()
    action = _safe_dict(data.get("action"))

    if not action and player_input.startswith("{"):
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

    # Optional performance overrides from the request payload
    performance = _safe_dict(data.get("performance"))

    return {
        "session_id": _safe_str(data.get("session_id")).strip(),
        "player_input": player_input,
        "action": action,
        "performance": performance,
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
    scene_state = _safe_dict(runtime_state.get("current_scene")) or _safe_dict(sim.get("current_scene"))
    memory = _safe_dict(sim.get("memory"))

    payload: Dict[str, Any] = {
        "success": True,
        "session_id": _safe_str(raw_payload.get("session_id") or session.get("session_id")),
        "title": _safe_str(raw_payload.get("title")),
        "opening": _safe_str(raw_payload.get("opening")),
        "narration": _safe_str(raw_payload.get("narration")),
        "choices": _safe_list(raw_payload.get("choices")),
        # Player block
        "player": {
            "stats": stats,
            "skills": skills,
            "level": int(player_state.get("level", 1) or 1),
            "xp": int(player_state.get("xp", 0) or 0),
            "xp_to_next": int(player_state.get("xp_to_next", 0) or 0),
            "inventory_state": inventory_state,
            "equipment": equipment,
            "currency": _safe_dict(inventory_state.get("currency")),
            "inventory_items": _safe_list(inventory_state.get("items")),
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
        "resource_changes": _safe_dict(raw_payload.get("resource_changes")),
        "player_resources": _safe_dict(raw_payload.get("player_resources")),
        "effect_result": _safe_dict(raw_payload.get("effect_result")),
        "action_metadata": _safe_dict(raw_payload.get("action_metadata")),
        "structured_narration": _safe_dict(raw_payload.get("structured_narration")),
        "speaker_turns": _safe_list(raw_payload.get("speaker_turns")),
        "narration": _safe_str(raw_payload.get("narration")),
        "used_app_llm": bool(raw_payload.get("used_app_llm")),
        "gateway_available": bool(raw_payload.get("gateway_available")),
        "raw_llm_narrative": _safe_str(raw_payload.get("raw_llm_narrative")),
        "response_length": _safe_str(raw_payload.get("response_length", "short")),
        # Presentation
        "presentation": _safe_dict(raw_payload.get("presentation")),
        "transaction_menus": _safe_list(raw_payload.get("transaction_menus")),
        # Living-world ambient metadata (Phase 7.4)
        "ambient_updates": _safe_list(
            get_pending_ambient_updates(session, after_seq=0, limit=8)
        ),
        "latest_ambient_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "unread_ambient_count": max(
            0,
            int(runtime_state.get("ambient_seq", 0) or 0)
            - int(_safe_dict(runtime_state.get("subscription_state")).get("last_polled_seq", 0) or 0),
        ),
    }
    # Conversation system payload
    location_id = _safe_str(
        runtime_state.get("current_location_id")
        or _safe_dict(sim.get("player_state")).get("location_id")
    )
    conversation_payload = build_conversation_payload(sim, runtime_state, location_id=location_id)
    payload["active_conversations"] = conversation_payload.get("active_conversations", [])
    payload["recent_conversations"] = conversation_payload.get("recent_conversations", [])
    return payload


@rpg_session_bp.post("/api/rpg/session/menu_action")
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
    return {"ok": True, "game": payload}


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


@rpg_session_bp.post("/api/rpg/session/settings")
async def update_rpg_session_settings(request: Request):
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    settings = _safe_dict(data.get("settings"))

    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)

    runtime_state = _safe_dict(session.get("runtime_state"))
    existing = _safe_dict(runtime_state.get("runtime_settings"))
    merged = dict(existing)
    merged.update(settings)
    runtime_state["runtime_settings"] = _normalize_runtime_settings(merged)
    session["runtime_state"] = runtime_state
    session = save_runtime_session(session)

    return {"ok": True, "settings": runtime_state["runtime_settings"]}


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
    request_performance = _safe_dict(normalized.get("performance"))

    sse_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    if not session_id:
        def error_gen():
            yield _sse({"type": "error", "error": "session_id_required"})
        return StreamingResponse(error_gen(), status_code=400, media_type="text/event-stream", headers=sse_headers)

    def generate():
        try:
            yield _sse({"type": "accepted"})
            yield _sse({"type": "processing", "stage": "authoritative_turn"})

            authoritative_result = _apply_turn_authoritative(
                session_id,
                player_input,
                action=action,
                performance_override=request_performance or None,
            )

            if not authoritative_result.get("ok"):
                err = _safe_str(authoritative_result.get("error") or "turn_failed")
                yield _sse({"type": "error", "error": err})
                return

            authoritative = _safe_dict(authoritative_result.get("authoritative"))
            narration_request = _safe_dict(authoritative_result.get("narration_request"))

            session = load_runtime_session(session_id)
            if session is None:
                yield _sse({"type": "error", "error": "session_not_found_after_authoritative"})
                return
            runtime_state = _copy_dict(session.get("runtime_state"))
            turn_id = _safe_str(authoritative.get("turn_id")).strip()
            tick = int(authoritative.get("tick", 0) or 0)
            runtime_state, narration_job, is_new = _enqueue_narration_request(
                runtime_state,
                turn_id,
                tick,
                narration_request,
                "player_turn",
                100,
            )
            session["runtime_state"] = runtime_state
            save_runtime_session(session)

            if is_new:
                try:
                    ensure_narration_worker_running()
                    signal_narration_work(session_id)
                except Exception:
                    _logger.exception("Failed to start or signal narration worker")

            authoritative_turn_id = _safe_str((narration_job or {}).get("turn_id")).strip() or turn_id
            narration_status = _safe_str((narration_job or {}).get("status") or "queued")

            yield _sse({
                "type": "authoritative_result",
                "turn_id": authoritative_turn_id,
                "tick": authoritative.get("tick"),
                "resolved_result": authoritative.get("resolved_result"),
                "combat_result": authoritative.get("combat_result"),
                "xp_result": authoritative.get("xp_result"),
                "skill_xp_result": authoritative.get("skill_xp_result"),
                "level_up": authoritative.get("level_up"),
                "skill_level_ups": authoritative.get("skill_level_ups"),
                "summary": authoritative.get("summary"),
                "presentation": authoritative.get("presentation"),
                "response_length": authoritative.get("response_length"),
                "fallback_narration": authoritative.get("deterministic_fallback_narration"),
                "narration_status": narration_status,
                "narration_job": narration_job or {},
            })

            # "done" here means authoritative turn resolution is complete.
            # Final narration arrives separately via narration stream events.
            yield _sse({
                "type": "done",
                "turn_id": authoritative_turn_id,
                "tick": authoritative.get("tick"),
                "narration_status": narration_status,
            })
        except Exception as exc:
            _logger.exception("turn/stream failed")
            yield _sse({
                "type": "error",
                "error": str(exc) or "turn_stream_failed",
            })
            return

    return StreamingResponse(generate(), media_type="text/event-stream", headers=sse_headers)


# Debug/manual trigger endpoint.
# Normal gameplay should rely on the background worker manager instead.
@rpg_session_bp.post("/api/rpg/session/process_narration")
async def process_rpg_session_narration(request: Request):
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    result = process_next_narration_job(session_id)
    return JSONResponse(result)


@rpg_session_bp.post("/api/rpg/session/narration_status")
async def get_rpg_session_narration_status(request: Request):
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    turn_id = _safe_str(data.get("turn_id")).strip()

    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)
    
    if not turn_id:
        return JSONResponse({
            "ok": True,
            "turn_id": None,
            "job": None,
            "artifact": None,
        })

    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)

    runtime_state = _safe_dict(session.get("runtime_state"))
    job = _safe_dict(_safe_dict(runtime_state.get("narration_jobs_by_turn")).get(turn_id))
    artifact = _safe_dict(_safe_dict(runtime_state.get("narration_artifacts_by_turn")).get(turn_id))
    job_status = _safe_str(job.get("status")).strip().lower()

    # Self-heal queued narration jobs so polling can recover even if the worker
    # missed a wake-up or the SSE channel never opened on the client.
    if job and not artifact and job_status in ("queued", "processing"):
        # Recover jobs stuck in "processing" state (e.g., worker exception left
        # the job marked processing but never completed it).
        needs_reset = False
        if job_status == "processing":
            started = _safe_str(job.get("started_at"))
            if started:
                try:
                    started_dt = datetime.datetime.fromisoformat(
                        started.replace("Z", "+00:00")
                    )
                    now_dt = datetime.datetime.now(datetime.timezone.utc)
                    if (now_dt - started_dt).total_seconds() > 90:
                        needs_reset = True
                except Exception:
                    needs_reset = True
            else:
                needs_reset = True

        if needs_reset:
            _logger.warning(
                "Resetting stuck processing narration job to queued",
                extra={
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "started_at": _safe_str(job.get("started_at")),
                },
            )
            try:
                runtime_state = dict(runtime_state)
                by_turn = dict(_safe_dict(runtime_state.get("narration_jobs_by_turn")))
                stuck_job = dict(by_turn.get(turn_id, {}))
                stuck_job["status"] = "queued"
                stuck_job["started_at"] = None
                stuck_job["worker_token"] = ""
                by_turn[turn_id] = stuck_job
                runtime_state["narration_jobs_by_turn"] = by_turn
                # Also fix the list
                jobs_list = list(_safe_list(runtime_state.get("narration_jobs")))
                for idx, j in enumerate(jobs_list):
                    if isinstance(j, dict) and _safe_str(j.get("turn_id")).strip() == turn_id:
                        jobs_list[idx] = stuck_job
                runtime_state["narration_jobs"] = jobs_list
                session["runtime_state"] = runtime_state
                save_runtime_session(session)
            except Exception:
                _logger.exception("Failed to reset stuck processing job")

        _logger.info("Re-signaling narration job", extra={
            "session_id": session_id,
            "turn_id": turn_id,
            "job_status": job_status,
            "was_reset": needs_reset,
        })
        try:
            ensure_narration_worker_running()
            signal_narration_work(session_id)
        except Exception:
            _logger.exception("Failed to re-signal narration work", extra={
                "session_id": session_id,
                "turn_id": turn_id,
            })

    # Refresh after any re-signal so the client sees the latest status.
    session = load_runtime_session(session_id)
    runtime_state = _safe_dict((session or {}).get("runtime_state"))
    job = _safe_dict(_safe_dict(runtime_state.get("narration_jobs_by_turn")).get(turn_id))
    artifact = _safe_dict(_safe_dict(runtime_state.get("narration_artifacts_by_turn")).get(turn_id))

    return JSONResponse({
        "ok": True,
        "turn_id": turn_id,
        "job": job,
        "artifact": artifact,
    })


# ── Living-world endpoints (Phase 7) ──────────────────────────────────────


@rpg_session_bp.post("/api/rpg/session/idle_tick")
async def idle_tick_rpg_session(request: Request):
    """Advance world simulation by idle ticks without player action."""
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    count = int(data.get("count", 1) or 1)
    reason = _safe_str(data.get("reason") or "heartbeat").strip()

    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    # Upstream recorded LLM semantic proposal capture.
    session = load_runtime_session(session_id)
    if session:
        rt = _safe_dict(session.get("runtime_state"))
        print("ROUTE recorded_semantic_llm_proposals =", rt.get("recorded_semantic_llm_proposals"))
        print("ROUTE recorded_semantic_llm_prompt present =", bool(rt.get("recorded_semantic_llm_prompt")))
        print("ROUTE recorded_semantic_llm_raw_output present =", bool(rt.get("recorded_semantic_llm_raw_output")))
        session = capture_semantic_state_change_proposals_for_session(session)
        try:
            save_runtime_session(session)
        except Exception:
            # Capture is best-effort; authoritative runtime validation still
            # guards all proposals before state mutation.
            pass

    result = apply_idle_ticks(session_id, count, reason=reason)
    if not result.get("ok"):
        err = _safe_str(result.get("error") or "idle_tick_failed")
        status = 404 if err == "session_not_found" else 500
        return JSONResponse({"ok": False, "error": err}, status_code=status)

    # Debug: verify the saved session exposes the advanced authoritative tick.
    session = load_runtime_session(session_id)
    if session:
        sim = _safe_dict(session.get("simulation_state"))
        rt = _safe_dict(session.get("runtime_state"))
        print("POST-IDLE SIM TICK =", sim.get("tick"), sim.get("current_tick"))
        print("POST-IDLE RUNTIME TICK =", rt.get("tick"))

    # Post-advance capture: lets the LLM observe newly advanced state so the
    # next cycle has fresh recorded proposals grounded in what just changed.
    session = load_runtime_session(session_id)
    if session:
        runtime_state = _safe_dict(session.get("runtime_state"))
        if not _safe_list(runtime_state.get("recorded_semantic_llm_proposals")):
            rt = _safe_dict(session.get("runtime_state"))
            print("ROUTE recorded_semantic_llm_proposals =", rt.get("recorded_semantic_llm_proposals"))
            print("ROUTE recorded_semantic_llm_prompt present =", bool(rt.get("recorded_semantic_llm_prompt")))
            print("ROUTE recorded_semantic_llm_raw_output present =", bool(rt.get("recorded_semantic_llm_raw_output")))
            session = capture_semantic_state_change_proposals_for_session(session)
            try:
                save_runtime_session(session)
            except Exception:
                pass

    return {
        "ok": True,
        "updates": _safe_list(result.get("updates")),
        "latest_seq": int(result.get("latest_seq", 0) or 0),
        "ticks_applied": int(result.get("ticks_applied", 0) or 0),
        "idle_debug_trace": result.get("idle_debug_trace", {}),
        "idle_seconds": result.get("idle_seconds", 0),
        "idle_gate_open": result.get("idle_gate_open", False),
        "settings": result.get("settings", {}),
    }


@rpg_session_bp.post("/api/rpg/session/poll")
async def poll_rpg_session(request: Request):
    """Poll for pending ambient updates by sequence number."""
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    after_seq = int(data.get("after_seq", 0) or 0)
    limit = int(data.get("limit", 8) or 8)

    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)

    updates = get_pending_ambient_updates(session, after_seq=after_seq, limit=limit)
    runtime = _safe_dict(session.get("runtime_state"))

    return {
        "ok": True,
        "updates": updates,
        "latest_seq": int(runtime.get("ambient_seq", 0) or 0),
    }


@rpg_session_bp.get("/api/rpg/session/stream")
async def stream_rpg_session(request: Request):
    """Persistent SSE stream for living-world ambient updates.

    Query params:
      session_id  — required
      after_seq   — optional, start from this seq
    """
    import asyncio
    import time

    session_id = _safe_str(request.query_params.get("session_id", "")).strip()
    after_seq = int(request.query_params.get("after_seq", "0") or 0)

    sse_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    if not session_id or session_id == "session:unknown":
        def error_gen():
            yield _sse({"type": "error", "error": "session_id_required"})
        return StreamingResponse(error_gen(), status_code=400, media_type="text/event-stream", headers=sse_headers)

    async def event_generator():
        local_seq = after_seq
        heartbeat_interval = 5  # seconds
        last_heartbeat = time.monotonic()

        # Initial backlog flush
        session = load_runtime_session(session_id)
        if session is None:
            yield _sse({"type": "error", "error": "session_not_found"})
            return

        backlog = get_pending_ambient_updates(session, after_seq=local_seq, limit=8)
        for update in backlog:
            yield _sse({"type": "ambient", "update": update})
            seq = int(_safe_dict(update).get("seq", 0) or 0)
            if seq > local_seq:
                local_seq = seq

        # Long-lived event loop with heartbeats and ambient polling
        for _ in range(600):  # max ~50 minutes at 5s intervals
            await asyncio.sleep(heartbeat_interval)
            now = time.monotonic()

            # Check for new updates
            session = load_runtime_session(session_id)
            if session is None:
                yield _sse({"type": "error", "error": "session_closed"})
                return

            new_updates = get_pending_ambient_updates(session, after_seq=local_seq, limit=8)
            for update in new_updates:
                yield _sse({"type": "ambient", "update": update})
                seq = int(_safe_dict(update).get("seq", 0) or 0)
                if seq > local_seq:
                    local_seq = seq

            # Heartbeat
            if now - last_heartbeat >= heartbeat_interval:
                runtime = _safe_dict(session.get("runtime_state"))
                yield _sse({
                    "type": "heartbeat",
                    "latest_seq": int(runtime.get("ambient_seq", 0) or 0),
                    "tick": int(runtime.get("tick", 0) or 0),
                })
                last_heartbeat = now

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=sse_headers)


@rpg_session_bp.get("/api/rpg/session/narration_events")
async def stream_rpg_session_narration_events(request: Request):
    session_id = _safe_str(request.query_params.get("session_id")).strip()
    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    ensure_narration_worker_running()
    subscriber_q = subscribe_narration_events(session_id)

    sse_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    import asyncio

    async def event_generator():
        last_heartbeat = time.monotonic()
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    evt = await asyncio.wait_for(subscriber_q.get(), timeout=0.5)
                    event_type = evt.get("type", "narration_event")
                    yield f"event: {event_type}\ndata: {json.dumps(evt)}\n\n"
                except asyncio.TimeoutError:
                    now = time.monotonic()
                    if now - last_heartbeat >= 15.0:
                        yield "event: heartbeat\ndata: {\"type\": \"heartbeat\"}\n\n"
                        last_heartbeat = now
                    await asyncio.sleep(0.05)
        finally:
            unsubscribe_narration_events(session_id, subscriber_q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=sse_headers,
    )


@rpg_session_bp.post("/api/rpg/session/resume")
async def resume_rpg_session(request: Request):
    """Resume a session with bounded catch-up for elapsed time."""
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    elapsed_seconds = int(data.get("elapsed_seconds", 0) or 0)

    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    # Upstream recorded LLM semantic proposal capture before catch-up/resume.
    try:
        session = load_runtime_session(session_id)
    except CorruptSessionPayloadError as exc:
        _logger.exception("resume_rpg_session: corrupt persisted session")
        return JSONResponse(
            {
                "ok": False,
                "error": "corrupt_session_payload",
                "session_id": session_id,
                "detail": {"path": str(exc.path)},
            },
            status_code=409,
        )

    if session:
        session = capture_semantic_state_change_proposals_for_session(session)
        try:
            save_runtime_session(session)
        except Exception:
            pass

    result = apply_resume_catchup(session_id, elapsed_seconds=elapsed_seconds)
    if not result.get("ok"):
        err = _safe_str(result.get("error") or "resume_failed")
        status = 404 if err == "session_not_found" else 500
        return JSONResponse({"ok": False, "error": err}, status_code=status)

    # Debug: verify the saved session exposes the advanced authoritative tick.
    try:
        session = load_runtime_session(session_id)
    except CorruptSessionPayloadError as exc:
        _logger.exception("resume_rpg_session: session became corrupt after catch-up")
        return JSONResponse(
            {
                "ok": False,
                "error": "corrupt_session_payload",
                "session_id": session_id,
                "detail": {"path": str(exc.path)},
            },
            status_code=409,
        )

    if session:
        sim = _safe_dict(session.get("simulation_state"))
        rt = _safe_dict(session.get("runtime_state"))
        print("POST-RESUME SIM TICK =", sim.get("tick"), sim.get("current_tick"))
        print("POST-RESUME RUNTIME TICK =", rt.get("tick"))

    # Post-catchup capture: after resume advances the world, capture again so
    # recorded proposals reflect the newly advanced scene state.
    try:
        session = load_runtime_session(session_id)
    except CorruptSessionPayloadError as exc:
        _logger.exception("resume_rpg_session: corrupt persisted session during post-catchup capture")
        return JSONResponse(
            {
                "ok": False,
                "error": "corrupt_session_payload",
                "session_id": session_id,
                "detail": {"path": str(exc.path)},
            },
            status_code=409,
        )

    if session:
        runtime_state = _safe_dict(session.get("runtime_state"))
        if not _safe_list(runtime_state.get("recorded_semantic_llm_proposals")):
            rt = _safe_dict(session.get("runtime_state"))
            print("ROUTE recorded_semantic_llm_proposals =", rt.get("recorded_semantic_llm_proposals"))
            print("ROUTE recorded_semantic_llm_prompt present =", bool(rt.get("recorded_semantic_llm_prompt")))
            print("ROUTE recorded_semantic_llm_raw_output present =", bool(rt.get("recorded_semantic_llm_raw_output")))
            session = capture_semantic_state_change_proposals_for_session(session)
            try:
                save_runtime_session(session)
            except Exception:
                pass

    # Debug: check if recap is generated
    if result.get("world_advance_recap"):
        print("DEBUG RECAP:", result.get("world_advance_recap"))
    else:
        print("DEBUG RECAP: None")

    return {
        "ok": True,
        "updates": _safe_list(result.get("updates")),
        "latest_seq": int(result.get("latest_seq", 0) or 0),
        "ticks_applied": int(result.get("ticks_applied", 0) or 0),
        "excess_summarized": int(result.get("excess_summarized", 0) or 0),
        "world_advance_recap": _safe_dict(result.get("world_advance_recap")),
    }


# ── World Events endpoint ────────────────────────────────────────────────


@rpg_session_bp.post("/api/rpg/session/world_events")
async def get_rpg_session_world_events(request: Request):
    """Return cached recent world event rows from runtime state."""
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    print(
        "DEBUG WORLD EVENTS ROUTE REQUEST =",
        {
            "session_id": session_id,
        },
    )

    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)

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

    print(
        "DEBUG WORLD EVENTS ROUTE RESPONSE =",
        {
            "count": len(recent_rows),
            "player_count": len(player_world_view_rows),
            "event_ids": [_safe_str(r.get("event_id")) for r in recent_rows],
            "player_event_ids": [_safe_str(r.get("event_id")) for r in player_world_view_rows],
        },
    )

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


@rpg_session_bp.post("/api/rpg/session/world_behavior")
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


@rpg_session_bp.post("/api/rpg/session/world_behavior/update")
async def update_world_behavior(request: Request):
    """Update in-game world behavior overrides."""
    from app.rpg.creator.schema import (
        _WORLD_BEHAVIOR_ENUMS,
        normalize_world_behavior_config,
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

    # Apply only valid changes
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


@rpg_session_bp.post("/api/rpg/session/conversation/intervene")
async def rpg_session_conversation_intervene(request: Request):
    data = await request.json()
    session_id = _safe_str(data.get("session_id"))
    conversation_id = _safe_str(data.get("conversation_id"))
    option_id = _safe_str(data.get("option_id"))

    session = load_runtime_session(session_id)
    if session is None:
        return JSONResponse({"ok": False, "error": "session_not_found"}, status_code=404)

    simulation_state = _safe_dict(session.get("simulation_state"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    tick = int(_safe_dict(simulation_state).get("tick", 0) or 0)

    result = apply_player_intervention(conversation_id, option_id, simulation_state, runtime_state, tick)
    session["simulation_state"] = simulation_state
    session["runtime_state"] = runtime_state
    session = save_runtime_session(session)

    payload = build_conversation_payload(
        simulation_state,
        runtime_state,
        location_id=_safe_str(runtime_state.get("current_location_id")),
    )
    return JSONResponse({
        "success": True,
        "result": result,
        "active_conversations": payload.get("active_conversations", []),
        "recent_conversations": payload.get("recent_conversations", []),
    })