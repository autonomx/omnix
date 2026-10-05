from __future__ import annotations

# RPG session runtime responsibility module.
import time as _time
import logging
from app.apps.rpg.ai.world_scene_narrator import (
    narrate_scene as narrate_scene,
)
from app.apps.rpg.session.session_runtime_store import (
    load_runtime_session as load_runtime_session, save_runtime_session as save_runtime_session,
)
from app.apps.rpg.session.state_normalization import (
    _copy_dict as _copy_dict, _normalize_final_narration_text as _normalize_final_narration_text, _safe_dict as _safe_dict, _safe_list as _safe_list, _safe_str as _safe_str,
)
from app.apps.rpg.session.companion_turn_runtime import (
    _ensure_narration_job_state as _ensure_narration_job_state, _get_authoritative_narration_job_id as _get_authoritative_narration_job_id,
    _get_narration_job_for_turn as _get_narration_job_for_turn, _has_narration_artifact_for_turn as _has_narration_artifact_for_turn,
    _mark_narration_job_status as _mark_narration_job_status, _store_narration_artifact as _store_narration_artifact,
)
from app.apps.rpg.session.narration_worker import (
    publish_narration_event as publish_narration_event, signal_narration_work as signal_narration_work,
)
from app.apps.rpg.session.combat_intent import (
    _utc_now_iso as _utc_now_iso, ensure_ambient_runtime_state as ensure_ambient_runtime_state,
)
import os as os
from app.apps.rpg.ai.grounding_soft_audit import (
    run_grounding_soft_audit as run_grounding_soft_audit,
)
from app.apps.rpg.llm_app_gateway import (
    build_app_llm_gateway as build_app_llm_gateway,
)
from app.apps.rpg.ai.grounding_settings import (
    normalize_grounding_settings as normalize_grounding_settings,
)
from app.apps.rpg.session.narration_queue_runtime import (
    _enqueue_grounding_soft_audit_request as _enqueue_grounding_soft_audit_request,
)
from typing import (
    Any as Any, Callable as Callable, Dict as Dict, List as List, Optional as Optional,
)

logger = logging.getLogger(__name__)

from .state_normalization import _merge_stepped_simulation_state  # noqa: F401


def _ambient_conversation_artifact_line(artifact: dict[str, Any]) -> str:
    artifact = _safe_dict(artifact)
    return _safe_str(artifact.get("line") or artifact.get("narration") or artifact.get("text"))


def _generate_turn_narration_artifact(
    session_id: str,
    narration_request: dict[str, Any],
    on_chunk: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    logger.debug("_generate_turn_narration_artifact called", extra={"session_id": session_id, "turn_id": narration_request.get("turn_id")})
    t0 = _time.monotonic()
    logger.info("[RPG NARRATION ARTIFACT] start session=%s turn_id=%s tick=%s", session_id, narration_request.get("turn_id"), narration_request.get("tick"))
    narration_request = _safe_dict(narration_request)
    turn_id = _safe_str(narration_request.get("turn_id")).strip()
    tick = int(narration_request.get("tick", 0) or 0)
    scene = _safe_dict(narration_request.get("scene"))
    narration_context = _safe_dict(narration_request.get("narration_context"))
    perf = _safe_dict(narration_request.get("performance"))

    streamed_chunks: list[str] = []

    def _emit_chunk(piece: str) -> None:
        piece = _safe_str(piece)
        if not piece:
            return
        streamed_chunks.append(piece)
        if on_chunk:
            try:
                on_chunk(piece)
            except Exception:
                logger.exception("Failed to emit narration chunk")

    llm_enabled = bool(perf.get("enable_live_narration_llm", True))
    retry_on_invalid = bool(perf.get("enable_narration_retry", False))
    llm_gateway = build_app_llm_gateway() if llm_enabled else None
    logger.debug("LLM gateway status", extra={"session_id": session_id, "turn_id": turn_id, "llm_enabled": llm_enabled, "llm_gateway": llm_gateway is not None})

    logger.debug("Calling narrate_scene", extra={"session_id": session_id, "turn_id": turn_id})
    t_narrate0 = _time.monotonic()
    narration_result = narrate_scene(
        scene,
        narration_context,
        llm_gateway=llm_gateway,
        tone="dramatic",
        retry_on_invalid=retry_on_invalid,
        debug_logging=False,
        on_chunk=_emit_chunk,
    )
    logger.info("[RPG NARRATION ARTIFACT] narrate_scene_done session=%s turn_id=%s dt=%.3fs used_llm=%s",
        session_id, turn_id, _time.monotonic() - t_narrate0, bool(_safe_dict(narration_result).get("used_llm")))
    logger.debug("narrate_scene returned", extra={"session_id": session_id, "turn_id": turn_id, "result_keys": list(narration_result.keys()) if isinstance(narration_result, dict) else type(narration_result)})

    narration_result = _safe_dict(narration_result)
    if not _safe_str(narration_result.get("narration")).strip() and streamed_chunks:
        narration_result["narration"] = "".join(streamed_chunks).strip()
    if not _safe_str(narration_result.get("raw_llm_narrative")).strip() and streamed_chunks:
        narration_result["raw_llm_narrative"] = "".join(streamed_chunks).strip()

    final_narration = _normalize_final_narration_text(
        _safe_str(narration_result.get("narration") or narration_result.get("narrative") or "")
    )
    narration_json = _safe_dict(narration_result.get("narration_json"))

    artifact = {
        "turn_id": turn_id,
        "tick": tick,
        "narration": final_narration,
        "narration_json": narration_json,
        "authoritative_action": _safe_str(narration_json.get("action")).strip(),
        "authoritative_reward": _safe_str(narration_json.get("reward")).strip(),
        "authoritative_npc": _safe_dict(narration_json.get("npc")),
        "used_llm": bool(narration_result.get("used_llm")),
        "raw_llm_narrative": _safe_str(narration_result.get("raw_llm_narrative")),
        "narration_context": _safe_dict(narration_request.get("narration_context")),
        "grounding_validation": _safe_dict(
            narration_result.get("grounding_validation")
            or narration_json.get("grounding_validation")
        ),
        "grounding_fallback": bool(
            narration_result.get("grounding_fallback")
            or narration_json.get("grounding_fallback")
        ),
        "speaker_presentation": _safe_dict(narration_result.get("speaker_presentation")),
        "format_warning": bool(narration_result.get("format_warning")),
        "created_at": _utc_now_iso(),
        "artifact_type": "turn_narration",
    }

    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": True, "session": None, "artifact": artifact}

    runtime_state = _copy_dict(session.get("runtime_state"))
    current_tick = int(runtime_state.get("tick", 0) or 0)

    # SAFETY: do not attach narration to a future-overwritten turn
    if tick < current_tick - 1:
        return {
            "ok": False,
            "error": "stale_narration_artifact",
            "artifact": artifact,
        }

    updated_runtime = _store_narration_artifact(runtime_state, artifact)

    # Only merge narration artifact fields back, so a late narration result
    # cannot overwrite newer runtime state from a later committed turn.
    session_runtime = _copy_dict(session.get("runtime_state"))
    session_runtime["narration_artifacts"] = _safe_list(updated_runtime.get("narration_artifacts"))
    session_runtime["narration_artifacts_by_turn"] = _safe_dict(updated_runtime.get("narration_artifacts_by_turn"))
    session["runtime_state"] = session_runtime

    t_save0 = _time.monotonic()
    session = save_runtime_session(session)
    logger.info(
        "[RPG NARRATION ARTIFACT] save_done session=%s turn_id=%s dt=%.3fs total=%.3fs",
        session_id,
        turn_id,
        _time.monotonic() - t_save0,
        _time.monotonic() - t0,
    )

    return {"ok": True, "session": session, "artifact": artifact}


def _process_next_narration_job(session_id: str) -> dict[str, Any]:
    """
    Process at most one queued narration job for the given session.
    Safe for polling/heartbeat driven execution.
    """
    t0 = _time.monotonic()
    logger.info("[RPG NARRATION JOB] process_start session=%s", session_id)
    logger.debug("process_next_narration_job called", extra={"session_id": session_id})
    session = load_runtime_session(session_id)
    if session is None:
        logger.warning("Session not found in process_next_narration_job", extra={"session_id": session_id})
        return {"ok": False, "error": "session_not_found"}

    runtime_state = _copy_dict(session.get("runtime_state"))
    runtime_state = _ensure_narration_job_state(runtime_state)

    jobs = [_safe_dict(j) for j in _safe_list(runtime_state.get("narration_jobs")) if isinstance(j, dict)]
    logger.debug("Found narration jobs", extra={"session_id": session_id, "total_jobs": len(jobs), "job_statuses": [j.get("status") for j in jobs]})
    queued = [j for j in jobs if _safe_str(j.get("status")) == "queued"]
    queued_job = None
    if queued:
        queued.sort(
            key=lambda j: (
                -int(j.get("priority", 0) or 0),
                -int(j.get("tick", 0) or 0),
                _safe_str(j.get("created_at")),
            )
        )
        queued_job = queued[0]
        logger.info(
            "[RPG NARRATION JOB] selected session=%s turn_id=%s job_id=%s status=%s attempts=%s max_attempts=%s",
            session_id,
            queued_job.get("turn_id"),
            queued_job.get("job_id"),
            _safe_str(queued_job.get("status")),
            queued_job.get("attempts"),
            queued_job.get("max_attempts"),
        )
        logger.debug("Selected queued job", extra={"session_id": session_id, "turn_id": queued_job.get("turn_id"), "priority": queued_job.get("priority")})

    if queued_job:
        turn_id = _safe_str(queued_job.get("turn_id")).strip()
        selected_job_id = _safe_str(queued_job.get("job_id")).strip()

        authoritative_job = _get_narration_job_for_turn(runtime_state, turn_id)
        authoritative_job_id = _safe_str(authoritative_job.get("job_id")).strip()
        if not authoritative_job_id or authoritative_job_id != selected_job_id:
            jobs = _safe_list(runtime_state.get("narration_jobs"))
            jobs = [
                _safe_dict(job)
                for job in jobs
                if _safe_str(_safe_dict(job).get("job_id")).strip() != selected_job_id
            ]
            runtime_state["narration_jobs"] = jobs
            session["runtime_state"] = runtime_state
            save_runtime_session(session)
            return {
                "ok": True,
                "status": "skipped",
                "reason": "superseded_job",
                "turn_id": turn_id,
            }

    if not queued_job:
        logger.info("No queued narration jobs for session", extra={"session_id": session_id})
        return {"ok": True, "status": "idle"}

    turn_id = _safe_str(queued_job.get("turn_id")).strip()
    tick = int(queued_job.get("tick", 0) or 0)
    logger.info("Processing queued narration job", extra={"session_id": session_id, "turn_id": turn_id, "tick": tick})
    current_tick = int(runtime_state.get("tick", 0) or 0)

    # Single-flight protection:
    # Re-load the authoritative per-turn job state before claiming. A repeated
    # wake-up may still be looking at an older queued snapshot while another
    # worker already owns the same turn's narration.
    current_job = _get_narration_job_for_turn(runtime_state, turn_id)
    current_status = _safe_str(current_job.get("status")).strip().lower()
    current_worker_token = _safe_str(current_job.get("worker_token")).strip()
    current_job_id = _safe_str(current_job.get("job_id")).strip()
    if current_job_id and current_job_id != selected_job_id:
        return {
            "ok": True,
            "status": "skipped",
            "reason": "superseded_before_claim",
            "turn_id": turn_id,
        }
    if current_status == "processing" or current_worker_token:
        logger.info(
            "Skipping narration job already claimed by another worker",
            extra={
                "session_id": session_id,
                "turn_id": turn_id,
                "status": current_status,
                "worker_token": current_worker_token,
            },
        )
        return {
            "ok": True,
            "status": "skipped",
            "reason": "already_processing",
            "turn_id": turn_id,
        }

    if _has_narration_artifact_for_turn(runtime_state, turn_id):
        authoritative_job_id = _get_authoritative_narration_job_id(runtime_state, turn_id)
        if authoritative_job_id == selected_job_id:
            runtime_state = _mark_narration_job_status(
                runtime_state,
                turn_id,
                status="completed",
                error="",
            )
            session["runtime_state"] = runtime_state
            session = save_runtime_session(session)
        return {
            "ok": True,
            "status": "completed",
            "turn_id": turn_id,
            "deduped": True,
        }

    authoritative_job_id = _get_authoritative_narration_job_id(runtime_state, turn_id)
    if authoritative_job_id != selected_job_id:
        return {
            "ok": True,
            "status": "skipped",
            "reason": "superseded_before_processing",
            "turn_id": turn_id,
        }

    # Optional stale protection: if narration is far behind, mark stale.
    job_kind = _safe_str(queued_job.get("job_kind")).strip() or "player_turn"

    # Only ambient/background narration may be dropped for staleness.
    # Player-turn narration is blocking UX and must still complete.
    if job_kind == "ambient_conversation" and tick < current_tick - 1:
        logger.info("[RPG NARRATION JOB] stale_detected session=%s turn_id=%s tick=%s current_tick=%s", session_id, turn_id, tick, current_tick)
        runtime_state = _mark_narration_job_status(runtime_state, turn_id, status="stale", error="stale_narration_job")
        session["runtime_state"] = runtime_state
        session = save_runtime_session(session)

        publish_narration_event(
            session_id,
            {
                "type": "narration_job",
                "session_id": session_id,
                "turn_id": turn_id,
                "tick": tick,
                "status": "stale",
                "error": "stale_narration_job",
            },
        )

        return {
            "ok": True,
            "status": "stale",
            "turn_id": turn_id,
        }

    worker_token = f"{_utc_now_iso()}:{os.getpid()}:{turn_id}"
    logger.debug("Marking narration job as processing", extra={"session_id": session_id, "turn_id": turn_id, "worker_token": worker_token})
    runtime_state = _mark_narration_job_status(
        runtime_state,
        turn_id,
        status="processing",
        worker_token=worker_token,
    )
    session["runtime_state"] = runtime_state
    session = save_runtime_session(session)

    logger.info(
        "[RPG NARRATION JOB] claimed session=%s turn_id=%s job_id=%s worker_token=%s dt=%.3fs",
        session_id,
        turn_id,
        selected_job_id,
        worker_token,
        _time.monotonic() - t0,
    )

    current_job = _safe_dict(
        _safe_dict(runtime_state.get("narration_jobs_by_turn")).get(turn_id)
    )
    attempts = int(current_job.get("attempts", 0))
    max_attempts = int(current_job.get("max_attempts", 3))

    try:
        publish_narration_event(
            session_id,
            {
                "type": "narration_job",
                "turn_id": turn_id,
                "status": "processing",
                "retry_count": attempts,
                "max_retries": max_attempts,
            },
        )
    except Exception:
        logger.exception("Failed to publish narration processing event")

    # Re-read after claim and verify we still own the job before doing work.
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found_after_claim"}

    claimed_job = _safe_dict(
        _safe_dict(_safe_dict(session.get("runtime_state")).get("narration_jobs_by_turn")).get(turn_id)
    )
    if _safe_str(claimed_job.get("worker_token")) != worker_token:
        return {"ok": False, "status": "claimed_elsewhere", "turn_id": turn_id}

    narration_request = _safe_dict(claimed_job.get("narration_request") or queued_job.get("narration_request"))
    job_kind = _safe_str(queued_job.get("job_kind")).strip() or _safe_str(claimed_job.get("job_kind")).strip() or "player_turn"
    logger.debug("Narration request prepared", extra={"session_id": session_id, "turn_id": turn_id, "request_keys": list(narration_request.keys()) if narration_request else None})

    if not narration_request or not narration_request.get("turn_id"):
        logger.info("[RPG NARRATION JOB] missing_request session=%s turn_id=%s", session_id, turn_id)
        logger.error("Missing narration request", extra={"session_id": session_id, "turn_id": turn_id})
        runtime_state = _mark_narration_job_status(
            runtime_state,
            turn_id,
            status="failed",
            error="missing_narration_request",
        )
        session["runtime_state"] = runtime_state
        session = save_runtime_session(session)
        return {
            "ok": False,
            "status": "failed",
            "turn_id": turn_id,
            "error": "missing_narration_request",
        }

    def _on_chunk(piece: str) -> None:
        publish_narration_event(
            session_id,
            {
                "type": "narration_chunk",
                "turn_id": turn_id,
                "chunk": piece,
            },
        )

    if job_kind == "grounding_soft_audit":
        try:
            audit_result = run_grounding_soft_audit(
                displayed_payload=_safe_dict(narration_request.get("displayed_payload")),
                turn_contract=_safe_dict(narration_request.get("turn_contract")),
                state_snapshot=_safe_dict(narration_request.get("state_snapshot")),
                llm_gateway=build_app_llm_gateway(),
                grounding_settings=_safe_dict(narration_request.get("grounding_settings")),
            )

            session = load_runtime_session(session_id)
            if session is None:
                return {"ok": False, "error": "session_not_found_after_soft_audit"}

            runtime_state = _copy_dict(session.get("runtime_state"))
            runtime_state = _mark_narration_job_status(runtime_state, turn_id, status="completed")
            session["runtime_state"] = runtime_state
            session = save_runtime_session(session)

            correction = _safe_dict(audit_result.get("correction"))
            if audit_result.get("ok") and audit_result.get("correction_needed") and correction:
                publish_narration_event(
                    session_id,
                    {
                        "type": "grounding_soft_correction",
                        "session_id": session_id,
                        "turn_id": _safe_str(narration_request.get("source_turn_id")),
                        "audit_turn_id": turn_id,
                        "role": "grounding_soft_correction",
                        "append_only": True,
                        "final": True,
                        "version": 1,
                        "text": _safe_str(
                            _safe_dict(correction.get("npc")).get("line")
                            or correction.get("narration")
                            or correction.get("action")
                        ),
                        "correction": correction,
                        "audit": _safe_dict(audit_result.get("audit")),
                    },
                )

            return {
                "ok": True,
                "status": "completed",
                "turn_id": turn_id,
                "soft_audit": audit_result,
                "session": session,
            }
        except Exception as exc:
            logger.exception("Grounding soft audit failed for session %s turn %s", session_id, turn_id)
            runtime_state = _mark_narration_job_status(
                runtime_state,
                turn_id,
                status="failed",
                error=f"grounding_soft_audit_failed: {exc!r}",
            )
            session["runtime_state"] = runtime_state
            session = save_runtime_session(session)
            return {
                "ok": False,
                "status": "failed",
                "turn_id": turn_id,
                "error": "grounding_soft_audit_failed",
            }

    t_gen = _time.monotonic()
    logger.info(
        "[RPG NARRATION JOB] generation_start session=%s turn_id=%s tick=%s",
        session_id,
        turn_id,
        queued_job.get("tick"),
    )
    logger.debug("Calling _generate_turn_narration_artifact", extra={"session_id": session_id, "turn_id": turn_id})
    try:
        result = _generate_turn_narration_artifact(session_id, narration_request, on_chunk=_on_chunk)

        logger.info(
            "[RPG NARRATION JOB] generation_end session=%s turn_id=%s ok=%s dt=%.3fs error=%s",
            session_id,
            turn_id,
            result.get("ok"),
            _time.monotonic() - t_gen,
            result.get("error"),
        )
    except Exception:
        logger.exception(
            "Exception in _generate_turn_narration_artifact for session %s turn %s",
            session_id,
            turn_id,
        )
        result = {"ok": False, "error": "narration_generation_exception"}

    session = _safe_dict(result.get("session")) or session
    latest_runtime_state = ensure_ambient_runtime_state(_copy_dict(session.get("runtime_state")))
    if _has_narration_artifact_for_turn(latest_runtime_state, turn_id):
        authoritative_job_id = _get_authoritative_narration_job_id(latest_runtime_state, turn_id)
        if authoritative_job_id == selected_job_id:
            latest_runtime_state = _mark_narration_job_status(
                latest_runtime_state,
                turn_id,
                status="completed",
                error="",
            )
            session["runtime_state"] = latest_runtime_state
            session = save_runtime_session(session)
        return {
            "ok": True,
            "status": "completed",
            "turn_id": turn_id,
            "deduped": True,
        }

    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found_after_narration"}

    runtime_state = _copy_dict(session.get("runtime_state"))
    current_job = _safe_dict(
        _safe_dict(runtime_state.get("narration_jobs_by_turn")).get(turn_id)
    )
    attempts = int(current_job.get("attempts", 0))
    max_attempts = int(current_job.get("max_attempts", 3))

    if result.get("ok"):
        runtime_state = _mark_narration_job_status(runtime_state, turn_id, status="completed")
        session["runtime_state"] = runtime_state
        session = save_runtime_session(session)

        artifact = _safe_dict(result.get("artifact"))
        publish_narration_event(
            session_id,
            {
                "type": "narration_complete",
                "turn_id": turn_id,
                "artifact": artifact,
            },
        )
        job_kind = _safe_str(_safe_dict(queued_job).get("job_kind")).strip() or "player_turn"
        if job_kind == "ambient_conversation":
            line = _ambient_conversation_artifact_line(artifact)
            speaker = _safe_str(artifact.get("speaker"))
            target = _safe_str(artifact.get("target"))
            conversation_id = _safe_str(artifact.get("conversation_id"))
            if not conversation_id and (speaker or target):
                def _norm(x):
                    return _safe_str(x).strip().lower().replace(" ", "_")

                speaker_key = _norm(speaker) or "unknown"
                target_key = _norm(target) or "unknown"
                conversation_id = f"conv_{turn_id}_{speaker_key}_{target_key}"

            if speaker or target:
                publish_narration_event(
                    session_id,
                    {
                        "type": "npc_conversation_artifact",
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "role": "npc_conversation",
                        "conversation_id": conversation_id,
                        "tick": artifact.get("tick"),
                        "speaker": speaker,
                        "target": target,
                        "line": line,
                        "text": line,
                        "used_llm": bool(artifact.get("used_llm")),
                    },
                )
            else:
                publish_narration_event(
                    session_id,
                    {
                        "type": "ambient_conversation_artifact",
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "role": "ambient_narration",
                        "tick": artifact.get("tick"),
                        "text": _safe_str(artifact.get("narration") or line),
                        "used_llm": bool(artifact.get("used_llm")),
                    },
                )
        else:
            narration_event = dict(artifact)
            narration_event.update(
                {
                    "type": "narration_artifact",
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "role": "turn_narration",
                    "final": True,
                    "version": int(artifact.get("version") or 1),
                    "tick": artifact.get("tick"),
                    "text": _safe_str(artifact.get("narration")),
                    "used_llm": bool(artifact.get("used_llm")),
                }
            )
            publish_narration_event(
                session_id,
                narration_event,
            )
            try:
                runtime_settings = _safe_dict(
                    _safe_dict(session.get("runtime_state")).get("runtime_settings")
                )
                grounding_settings = normalize_grounding_settings(
                    _safe_dict(runtime_settings.get("grounding"))
                )
                audit_turn_contract = _safe_dict(
                    _safe_dict(artifact.get("narration_context")).get("turn_contract")
                    or _safe_dict(narration_request.get("narration_context")).get("turn_contract")
                    or narration_request.get("turn_contract")
                )
                if bool(grounding_settings.get("background_soft_audit", True)) and audit_turn_contract:
                    source_turn_id = turn_id
                    audit_request = {
                        "turn_id": f"{source_turn_id}:grounding_soft_audit",
                        "source_turn_id": source_turn_id,
                        "tick": artifact.get("tick") or tick,
                        "displayed_payload": _safe_dict(artifact.get("narration_json")) or {
                            "format_version": "rpg_narration_v2",
                            "narration": _safe_str(artifact.get("narration")),
                            "action": "",
                            "npc": None,
                            "reward": None,
                            "followup_hooks": [],
                        },
                        "turn_contract": audit_turn_contract,
                        "state_snapshot": _safe_dict(
                            _safe_dict(narration_request.get("narration_context")).get("simulation_state")
                            or narration_request.get("simulation_state")
                        ),
                        "grounding_settings": grounding_settings,
                    }
                    runtime_state = _copy_dict(session.get("runtime_state"))
                    runtime_state, _, audit_is_new = _enqueue_grounding_soft_audit_request(
                        runtime_state,
                        source_turn_id,
                        int(artifact.get("tick") or tick or 0),
                        audit_request,
                    )
                    session["runtime_state"] = runtime_state
                    session = save_runtime_session(session)
                    if audit_is_new:
                        signal_narration_work(session_id)
            except Exception:
                logger.exception("Failed to enqueue grounding soft audit for session %s turn %s", session_id, turn_id)
        return {
            "ok": True,
            "status": "completed",
            "turn_id": turn_id,
            "artifact": artifact,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "session": session,
        }

    # Implement retry logic
    current_job = _safe_dict(
        _safe_dict(runtime_state.get("narration_jobs_by_turn")).get(turn_id)
    )
    attempts = int(current_job.get("attempts", 0))
    max_attempts = int(current_job.get("max_attempts", 3))

    # Increment before checking threshold
    attempts += 1

    if attempts >= max_attempts:
        final_status = "failed"
    else:
        final_status = "queued"

    runtime_state = _mark_narration_job_status(
        runtime_state,
        turn_id,
        status=final_status,
        error=_safe_str(result.get("error") or "narration_failed") if final_status == "failed" else "",
    )

    # Update attempts count and reset claim fields when re-queuing
    job = _safe_dict(_safe_dict(runtime_state.get("narration_jobs_by_turn")).get(turn_id))
    job["attempts"] = attempts
    if final_status == "queued":
        job["started_at"] = None
        job["worker_token"] = ""
    runtime_state["narration_jobs_by_turn"][turn_id] = job

    if final_status == "failed":
        try:
            publish_narration_event(
                session_id,
                {
                    "type": "narration_job",
                    "turn_id": turn_id,
                    "status": "failed",
                    "retry_count": attempts,
                    "max_retries": max_attempts,
                    "error": _safe_str(result.get("error") or "narration_failed"),
                },
            )
        except Exception:
            logger.exception("Failed to publish narration job failure event")
    session["runtime_state"] = runtime_state
    session = save_runtime_session(session)
    return {
        "ok": False if final_status == "failed" else True,
        "status": final_status,
        "turn_id": turn_id,
        "error": _safe_str(result.get("error") or "narration_failed") if final_status == "failed" else "",
        "attempts": attempts,
        "max_attempts": max_attempts,
        "artifact": result.get("artifact"),
        "session": session,
    }


def process_next_narration_job(session_id: str) -> dict[str, Any]:
    """Process one job and apply its result to the owning interaction lifecycle."""

    result = _process_next_narration_job(session_id)
    if not isinstance(result, dict):
        return result
    try:
        from app.apps.rpg.session.interaction_lifecycle import (
            apply_narration_result_to_interaction,
        )

        return apply_narration_result_to_interaction(session_id, result)
    except Exception as exc:
        from app.apps.rpg.debug_logging import log_rpg_event

        result["interaction_lifecycle_update"] = {
            "updated": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        log_rpg_event(
            "turn.stage.degraded",
            category="performance",
            level="warning",
            session_id=session_id,
            turn_id=str(result.get("turn_id") or "") or None,
            fields={
                "metric": "rpg_turn_stage_degraded",
                "stage": "interaction_narration_result",
                "degraded_stage_count": 1,
                "error_type": type(exc).__name__,
            },
            error=exc,
        )
        return result


__all__ = [
    '_process_next_narration_job',
    'process_next_narration_job',
]
