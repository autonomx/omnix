"""Canonical RPG session routes.

All gameplay turn traffic should go through this module.
Legacy /api/rpg/games* routes are retired from active registration.
"""
from __future__ import annotations

import datetime
import json
import logging
import queue
import threading
import time
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.rpg.ai.semantic_state_change_capture import (
    capture_semantic_state_change_proposals_for_session,
)
from app.rpg.api.rpg_profile_routes import (
    api_approve_rpg_npc_profile_draft as api_approve_rpg_npc_profile_draft,
    api_draft_rpg_npc_profile as api_draft_rpg_npc_profile,
    api_generate_rpg_npc_profile as api_generate_rpg_npc_profile,
    api_generate_rpg_npc_profile_portrait_prompt as api_generate_rpg_npc_profile_portrait_prompt,
    api_get_rpg_npc_profile as api_get_rpg_npc_profile,
    api_get_rpg_session_character_cards as api_get_rpg_session_character_cards,
    api_reject_rpg_npc_profile_draft as api_reject_rpg_npc_profile_draft,
    api_update_rpg_npc_profile as api_update_rpg_npc_profile,
    list_rpg_npc_biographies as list_rpg_npc_biographies,
    register_rpg_profile_routes,
)
from app.rpg.api.rpg_session_management_routes import (
    delete_rpg_session as delete_rpg_session,
    idle_tick_rpg_session as idle_tick_rpg_session,
    list_rpg_sessions as list_rpg_sessions,
    post_rpg_menu_action as post_rpg_menu_action,
    register_rpg_session_management_routes,
    update_rpg_session as update_rpg_session,
    update_rpg_session_settings as update_rpg_session_settings,
)
from app.rpg.api.rpg_session_payloads import (
    _build_turn_payload,
    _deep_merge_dict,
    _normalize_turn_request,
    _safe_dict,
    _safe_list,
    _safe_str,
)
from app.rpg.session.ambient_builder import (
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
    _copy_dict,
    _enqueue_narration_request,
    _generate_turn_narration_artifact,
    _normalize_runtime_settings,
    apply_resume_catchup,
    apply_turn,
    build_frontend_bootstrap_payload,
    load_runtime_session,
    process_next_narration_job,
    save_runtime_session,
)
from app.rpg.social.conversation_presentation import build_conversation_payload
from app.rpg.social.player_interventions import apply_player_intervention
from app.rpg.api.rpg_world_routes import (
    get_rpg_session_world_events as get_rpg_session_world_events,
    get_world_behavior as get_world_behavior,
    register_rpg_world_routes,
    update_world_behavior as update_world_behavior,
)

rpg_session_bp = APIRouter()
_logger = logging.getLogger(__name__)
_LIVE_FIRST_DRAFT_TIMEOUT_S = 12.0
_LIVE_FIRST_DRAFT_MAX_TIMEOUT_S = 60.0


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _has_stream_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _stream_authoritative_payload(authoritative_result: Dict[str, Any]) -> Dict[str, Any]:
    """Return the turn payload shape used by the streaming route.

    Some runtime paths expose completed turn fields under ``result`` and some
    older/tests paths expose them under ``authoritative``. The stream route
    needs the same filled fields either way.
    """
    authoritative_result = _safe_dict(authoritative_result)
    result_payload = _safe_dict(authoritative_result.get("result"))
    authoritative = _safe_dict(authoritative_result.get("authoritative"))
    merged = dict(result_payload)
    for key, value in authoritative.items():
        if _has_stream_value(value) or key not in merged:
            merged[key] = value
    return merged


def _stream_narration_request(authoritative_result: Dict[str, Any]) -> Dict[str, Any]:
    authoritative_result = _safe_dict(authoritative_result)
    return (
        _safe_dict(authoritative_result.get("narration_request"))
        or _safe_dict(_safe_dict(authoritative_result.get("authoritative")).get("narration_request"))
        or _safe_dict(_safe_dict(authoritative_result.get("result")).get("narration_request"))
    )


def _live_first_draft_enabled(perf: Dict[str, Any]) -> bool:
    perf = _safe_dict(perf)
    return perf.get("enable_live_first_draft_stream") is True


def _live_first_draft_timeout_s(perf: Dict[str, Any]) -> float:
    perf = _safe_dict(perf)
    timeout_s = _safe_float(
        perf.get("live_first_draft_timeout_s"),
        _LIVE_FIRST_DRAFT_TIMEOUT_S,
    )
    if timeout_s <= 0:
        timeout_s = _LIVE_FIRST_DRAFT_TIMEOUT_S
    return min(timeout_s, _LIVE_FIRST_DRAFT_MAX_TIMEOUT_S)


def _start_live_first_draft_thread(
    session_id: str,
    narration_request: Dict[str, Any],
) -> "queue.Queue[Dict[str, Any]]":
    """
    Generate the first-draft narration inline for the current turn request,
    while streaming chunks back to the same HTTP response.

    Queue events:
      {"type": "token", "text": "..."}
      {"type": "result", "result": {...}}
      {"type": "error", "error": "..."}
    """
    event_q: "queue.Queue[Dict[str, Any]]" = queue.Queue()

    def _emit_chunk(piece: str) -> None:
        piece = _safe_str(piece)
        if not piece:
            return
        event_q.put({
            "type": "token",
            "text": piece,
        })

    def _worker() -> None:
        try:
            result = _generate_turn_narration_artifact(
                session_id,
                narration_request,
                on_chunk=_emit_chunk,
            )
            event_q.put({
                "type": "result",
                "result": _safe_dict(result),
            })
        except Exception as exc:
            _logger.exception("live first-draft narration failed")
            event_q.put({
                "type": "error",
                "error": _safe_str(exc) or "live_first_draft_failed",
            })

    threading.Thread(
        target=_worker,
        name=f"rpg-live-first-draft:{session_id}",
        daemon=True,
    ).start()

    return event_q


def _enqueue_and_signal_narration_job(
    session_id: str,
    runtime_state: Dict[str, Any],
    turn_id: str,
    tick: int,
    narration_request: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any], bool]:
    runtime_state = _copy_dict(runtime_state)
    runtime_state["session_id"] = session_id
    narration_request = _safe_dict(narration_request)
    narration_request["session_id"] = session_id
    if turn_id and not _safe_str(narration_request.get("turn_id")).strip():
        narration_request["turn_id"] = turn_id
    if tick and not int(narration_request.get("tick", 0) or 0):
        narration_request["tick"] = tick

    runtime_state, narration_job, is_new = _enqueue_narration_request(
        runtime_state,
        turn_id,
        tick,
        narration_request,
        "player_turn",
        100,
    )

    session = load_runtime_session(session_id)
    if session is not None:
        session["runtime_state"] = runtime_state
        save_runtime_session(session)

    if is_new:
        try:
            ensure_narration_worker_running()
            signal_narration_work(session_id)
        except Exception:
            _logger.exception("Failed to start or signal narration worker")

    return runtime_state, narration_job, is_new


# Ensure narration worker is running on module load
ensure_narration_worker_running()


def _merge_request_runtime_settings(
    session_id: str,
    runtime_settings: Dict[str, Any],
) -> Dict[str, Any]:
    runtime_settings = _safe_dict(runtime_settings)
    if not session_id or not runtime_settings:
        return {"ok": True, "applied": False}

    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}

    runtime_state = _safe_dict(session.get("runtime_state"))
    existing = _safe_dict(runtime_state.get("runtime_settings"))
    merged = _deep_merge_dict(existing, runtime_settings)
    runtime_state["runtime_settings"] = _normalize_runtime_settings(merged)
    session["runtime_state"] = runtime_state
    save_runtime_session(session)
    return {
        "ok": True,
        "applied": True,
        "settings": runtime_state["runtime_settings"],
    }


register_rpg_session_management_routes(rpg_session_bp)
register_rpg_profile_routes(rpg_session_bp)
register_rpg_world_routes(rpg_session_bp)


@rpg_session_bp.post("/api/rpg/session/get")
async def get_rpg_session(request: Request):
    data = await request.json()
    session_id = _safe_str(data.get("session_id")).strip()
    if not session_id:
        return {"ok": False, "error": "missing_session_id"}

    session = load_runtime_session(session_id)
    print("[RPG][session/get]", {
        "requested_session_id": session_id,
        "session_type": type(session).__name__,
        "session_found": bool(session),
        "session_manifest_id": ((session or {}).get("manifest") or {}).get("id") if isinstance(session, dict) else None,
    })
    if not session:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}

    game = build_frontend_bootstrap_payload(session)
    if game.get("session_id") == "session:unknown":
        game["session_id"] = session_id

    return {"ok": True, "game": game}


@rpg_session_bp.post("/api/rpg/session/turn")
async def execute_rpg_session_turn(request: Request):
    data = await request.json()
    normalized = _normalize_turn_request(data)
    session_id = _safe_str(normalized.get("session_id")).strip()
    player_input = _safe_str(normalized.get("player_input")).strip()
    action = _safe_dict(normalized.get("action"))

    if not session_id:
        return JSONResponse({"ok": False, "error": "session_id_required"}, status_code=400)

    settings_merge = _merge_request_runtime_settings(
        session_id,
        _safe_dict(normalized.get("runtime_settings")),
    )
    if not settings_merge.get("ok"):
        return JSONResponse(
            {
                "ok": False,
                "error": settings_merge.get("error") or "settings_merge_failed",
            },
            status_code=404,
        )

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
    request_runtime_settings = _safe_dict(normalized.get("runtime_settings"))

    sse_headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    if not session_id:
        def error_gen():
            yield _sse({"type": "error", "error": "session_id_required"})
        return StreamingResponse(error_gen(), status_code=400, media_type="text/event-stream", headers=sse_headers)

    settings_merge = _merge_request_runtime_settings(session_id, request_runtime_settings)
    if not settings_merge.get("ok"):
        def error_gen():
            yield _sse({
                "type": "error",
                "error": settings_merge.get("error") or "settings_merge_failed",
            })
        return StreamingResponse(error_gen(), status_code=404, media_type="text/event-stream", headers=sse_headers)

    def generate():
        try:
            turn_request_id = uuid.uuid4().hex[:12]
            t0 = time.monotonic()
            _logger.info(
                "[RPG TURN STREAM] request_start session=%s req=%s input_len=%d",
                session_id,
                turn_request_id,
                len(player_input),
            )

            yield _sse({"type": "accepted"})
            yield _sse({"type": "processing", "stage": "authoritative_turn"})

            authoritative_result = _apply_turn_authoritative(
                session_id,
                player_input,
                action=action,
                performance_override=request_performance or None,
            )
            authoritative = _stream_authoritative_payload(authoritative_result)
            narration_request = _stream_narration_request(authoritative_result)

            t_authoritative_done = time.monotonic()
            _logger.info(
                "[RPG TURN STREAM] authoritative_done session=%s req=%s dt=%.3fs ok=%s turn_id=%s tick=%s",
                session_id,
                turn_request_id,
                t_authoritative_done - t0,
                authoritative_result.get("ok"),
                authoritative.get("turn_id"),
                authoritative.get("tick"),
            )

            if not authoritative_result.get("ok"):
                err = _safe_str(authoritative_result.get("error") or "turn_failed")
                yield _sse({"type": "error", "error": err})
                return

            session = load_runtime_session(session_id)
            if session is None:
                yield _sse({"type": "error", "error": "session_not_found_after_authoritative"})
                return
            runtime_state = _copy_dict(session.get("runtime_state"))
            turn_id = _safe_str(authoritative.get("turn_id") or narration_request.get("turn_id")).strip()
            tick = int(authoritative.get("tick") or narration_request.get("tick") or 0)
            if turn_id and not _safe_str(narration_request.get("turn_id")).strip():
                narration_request["turn_id"] = turn_id
            if tick and not int(narration_request.get("tick", 0) or 0):
                narration_request["tick"] = tick
            runtime_state["session_id"] = session_id
            narration_request["session_id"] = session_id

            perf = _safe_dict(narration_request.get("performance"))
            live_first_draft_stream = _live_first_draft_enabled(perf)

            authoritative_turn_id = turn_id
            narration_status = "streaming" if live_first_draft_stream else "queued"

            yield _sse({
                "type": "authoritative_result",
                "turn_id": authoritative_turn_id,
                "tick": tick,
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
                "narration_job": {},
                "live_draft_streaming": live_first_draft_stream,
            })

            if live_first_draft_stream:
                yield _sse({
                    "type": "processing",
                    "stage": "live_first_draft",
                    "turn_id": authoritative_turn_id,
                })

                event_q = _start_live_first_draft_thread(session_id, narration_request)
                live_result = {}
                live_error = ""
                live_timeout_s = _live_first_draft_timeout_s(perf)
                live_started_at = time.monotonic()

                while True:
                    elapsed_s = time.monotonic() - live_started_at
                    remaining_s = live_timeout_s - elapsed_s
                    if remaining_s <= 0:
                        live_error = f"live_first_draft_timeout_after_{live_timeout_s:.3f}s"
                        _logger.warning(
                            "[RPG TURN STREAM] live_first_draft_timeout session=%s req=%s turn_id=%s timeout_s=%.3f",
                            session_id,
                            turn_request_id,
                            authoritative_turn_id,
                            live_timeout_s,
                        )
                        yield _sse({
                            "type": "live_first_draft_timeout",
                            "turn_id": authoritative_turn_id,
                            "timeout_s": live_timeout_s,
                        })
                        break

                    try:
                        evt = event_q.get(timeout=min(0.10, max(remaining_s, 0.001)))
                    except queue.Empty:
                        # Keep the HTTP stream active even if the model has not
                        # yielded a chunk yet.
                        yield _sse({
                            "type": "heartbeat",
                            "stage": "live_first_draft",
                            "turn_id": authoritative_turn_id,
                        })
                        continue

                    evt_type = _safe_str(evt.get("type")).strip().lower()
                    if evt_type == "token":
                        yield _sse({
                            "type": "token",
                            "turn_id": authoritative_turn_id,
                            "text": _safe_str(evt.get("text")),
                        })
                        continue
                    if evt_type == "result":
                        live_result = _safe_dict(evt.get("result"))
                        break
                    if evt_type == "error":
                        live_error = _safe_str(evt.get("error") or "live_first_draft_failed")
                        break

                if live_result.get("ok"):
                    artifact = _safe_dict(live_result.get("artifact"))
                    if artifact:
                        yield _sse({
                            "type": "narration_artifact",
                            **artifact,
                            "turn_id": authoritative_turn_id,
                            "live_draft_streaming": True,
                        })
                        yield _sse({
                            "type": "done",
                            "turn_id": authoritative_turn_id,
                            "tick": authoritative.get("tick"),
                            "narration_status": "completed",
                            "live_draft_streaming": True,
                        })
                        return

                _logger.warning(
                    "Live first-draft stream failed; falling back to queued narration",
                    extra={
                        "session_id": session_id,
                        "turn_id": authoritative_turn_id,
                        "error": live_error or _safe_str(live_result.get("error")),
                    },
                )

            # Fallback path: queue narration in the background worker.
            runtime_state, narration_job, is_new = _enqueue_and_signal_narration_job(
                session_id,
                runtime_state,
                turn_id,
                tick,
                narration_request,
            )

            yield _sse({
                "type": "narration_job",
                "turn_id": authoritative_turn_id,
                "status": _safe_str((narration_job or {}).get("status") or "queued"),
                "job": narration_job or {},
                "live_draft_streaming": False,
            })
            yield _sse({
                "type": "done",
                "turn_id": authoritative_turn_id,
                "tick": authoritative.get("tick"),
                "narration_status": _safe_str((narration_job or {}).get("status") or "queued"),
                "live_draft_streaming": False,
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
# ── Character Card API routes (Bundle BJ-BK-BL) ──────────────────────────────

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

    started = _safe_str(job.get("started_at"))
    age_seconds = 0.0
    if started:
        try:
            started_dt = datetime.datetime.fromisoformat(
                started.replace("Z", "+00:00")
            )
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            age_seconds = (now_dt - started_dt).total_seconds()
        except Exception:
            age_seconds = -1.0

    _logger.info(
        "[RPG NARRATION STATUS] poll session=%s turn_id=%s status=%s age=%.1fs has_artifact=%s",
        session_id,
        turn_id,
        job_status,
        age_seconds,
        bool(artifact),
    )

    # Self-heal queued narration jobs so polling can recover even if the worker
    # missed a wake-up or the SSE channel never opened on the client.
    #
    # IMPORTANT:
    # - queued      -> may be re-signaled
    # - processing  -> must NOT be re-signaled unless we first prove it is
    #                  stuck and reset it back to queued
    #
    # Re-signaling live "processing" jobs can trigger duplicate expensive
    # narration executions while the original worker still owns the job.
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
                # The authoritative status is now queued again.
                job_status = "queued"
            except Exception:
                _logger.exception("Failed to reset stuck processing job")

        # Only re-signal truly queued jobs. Never re-signal active processing
        # work unless we reset it back to queued above.
        if job_status == "queued":
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
        else:
            _logger.debug(
                "Narration job is already processing; skipping re-signal",
                extra={
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "job_status": job_status,
                    "was_reset": needs_reset,
                },
            )

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
