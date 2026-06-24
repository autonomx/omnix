"""Deterministic new-game creation progress helpers.

The new-game creator remains synchronous and authoritative.  These helpers add a
small job/progress envelope around that synchronous work so the browser can show
backend-owned creation status without introducing LLM, image, TTS, or worker
side effects into session creation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from app.rpg.session.new_game import RpgNewGameRequest, create_new_game_session
from app.rpg.session.service import load_session, save_session

CreationJobStatus = Literal["queued", "running", "completed", "failed"]

NEW_GAME_CREATION_JOB_CONTRACT = "rpg_new_game_creation_job_v1"
NEW_GAME_CREATION_JOB_TYPE = "rpg.new_game.create"

CREATION_STAGES: list[dict[str, Any]] = [
    {
        "id": "validate_setup",
        "label": "Validated setup",
        "detail": "Required fields, toggles, and point-buy totals checked.",
        "progress": 8,
    },
    {
        "id": "resolve_seed",
        "label": "Resolved seed",
        "detail": "Visible or random seed converted into deterministic campaign entropy.",
        "progress": 18,
    },
    {
        "id": "create_player",
        "label": "Created player profile",
        "detail": "Identity, pronouns, background, power source, and capability tags prepared.",
        "progress": 31,
    },
    {
        "id": "apply_stats",
        "label": "Applied stat allocation",
        "detail": "Point-buy stats and build boosts converted into initial profile metadata.",
        "progress": 44,
    },
    {
        "id": "assign_gear",
        "label": "Assigned starter gear",
        "detail": "Starter kit, currency, and capability gear staged for session creation.",
        "progress": 56,
    },
    {
        "id": "prepare_location",
        "label": "Prepared starting location",
        "detail": "Location, available services, and initial NPC roster resolved.",
        "progress": 68,
    },
    {
        "id": "seed_npcs_services",
        "label": "Seeding NPCs and services",
        "detail": "Innkeeper, merchants, rumors, party eligibility, and local events staged.",
        "progress": 78,
    },
    {
        "id": "create_opening_hook",
        "label": "Creating opening hook",
        "detail": "First objective, suggested actions, and opening scene context generated.",
        "progress": 88,
    },
    {
        "id": "save_session",
        "label": "Saving campaign session",
        "detail": "Autosave/checkpoint payload prepared for replay-preserving launch.",
        "progress": 96,
    },
    {
        "id": "ready_first_turn",
        "label": "Ready for first turn",
        "detail": "Turn composer controls are ready; narration, TTS/STT, and image work stay deferred until you act.",
        "progress": 100,
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def creation_job_id(session_id: str) -> str:
    return f"rpg-create:{session_id}"


def _session_id_from_job_id(job_id_or_session_id: str) -> str:
    text = str(job_id_or_session_id or "").strip()
    if text.startswith("rpg-create:"):
        return text.split(":", 1)[1].strip()
    return text


def _stage_index_for_status(status: CreationJobStatus) -> int:
    if status == "completed":
        return len(CREATION_STAGES) - 1
    if status == "failed":
        return max(0, len(CREATION_STAGES) - 2)
    return 0


def build_creation_progress_snapshot(
    *,
    session_id: str = "",
    status: CreationJobStatus = "completed",
    error: str = "",
) -> dict[str, Any]:
    """Build a deterministic progress snapshot for the current creation state."""
    current_index = _stage_index_for_status(status)
    current_stage = CREATION_STAGES[current_index]
    progress = int(current_stage["progress"] if status != "failed" else 68)
    stages = []
    for index, stage in enumerate(CREATION_STAGES):
        if status == "failed" and index > current_index:
            stage_status = "pending"
        elif status == "completed" or index < current_index:
            stage_status = "done"
        elif index == current_index:
            stage_status = "failed" if status == "failed" else "active"
        else:
            stage_status = "pending"
        stages.append({**stage, "index": index, "status": stage_status})
    return {
        "contract_version": NEW_GAME_CREATION_JOB_CONTRACT,
        "job_id": creation_job_id(session_id) if session_id else "",
        "session_id": session_id,
        "status": status,
        "stage": current_stage["id"],
        "stage_label": current_stage["label"],
        "progress": progress,
        "current_stage_index": current_index,
        "stages": stages,
        "error": error,
    }


def build_creation_job(
    *,
    session_id: str = "",
    status: CreationJobStatus = "completed",
    error: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    now = timestamp or _utc_now()
    progress = build_creation_progress_snapshot(session_id=session_id, status=status, error=error)
    job = {
        "contract_version": NEW_GAME_CREATION_JOB_CONTRACT,
        "job_id": progress["job_id"],
        "type": NEW_GAME_CREATION_JOB_TYPE,
        "status": status,
        "progress": progress["progress"],
        "stage": progress["stage"],
        "stage_label": progress["stage_label"],
        "current_stage_index": progress["current_stage_index"],
        "stages": progress["stages"],
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
        "error": error,
    }
    if status == "completed":
        job["completed_at"] = now
    if status == "failed":
        job["failed_at"] = now
    return job


def _attach_creation_metadata(session: dict[str, Any], job: dict[str, Any], progress: dict[str, Any]) -> dict[str, Any]:
    session = dict(session)
    runtime_state = dict(session.get("runtime_state") or {})
    runtime_state["creation_job"] = dict(job)
    runtime_state["creation_progress"] = dict(progress)
    runtime_state["active_job_id"] = None
    runtime_state["last_error"] = job.get("error") or None
    session["runtime_state"] = runtime_state
    manifest = dict(session.get("manifest") or {})
    manifest["creation_job_id"] = job.get("job_id")
    manifest["creation_status"] = job.get("status")
    session["manifest"] = manifest
    return session


def _persist_creation_job(session_id: str, job: dict[str, Any], progress: dict[str, Any]) -> dict[str, Any] | None:
    session = load_session(session_id)
    if not session:
        return None
    return save_session(_attach_creation_metadata(session, job, progress), compact=True)


def create_new_game_session_with_progress(request: RpgNewGameRequest) -> dict[str, Any]:
    """Create a new game and attach backend-authored progress/job status.

    Session creation must remain a fast launch path.  The creation job/progress
    envelope is returned to the browser and attached to the returned session
    payload, but the already-saved campaign is not immediately reloaded and
    saved a second time just to persist completed progress metadata.  The
    persisted creation-job lookup can synthesize a completed job later.
    """
    timestamp = _utc_now()
    result = create_new_game_session(request)
    session_id = str(result.get("session_id") or "")
    if result.get("ok") is not True:
        error = str(result.get("error") or "new_game_creation_failed")
        job = build_creation_job(session_id=session_id, status="failed", error=error, timestamp=timestamp)
        progress = build_creation_progress_snapshot(session_id=session_id, status="failed", error=error)
        return {**result, "creation_job": job, "creation_progress": progress}

    job = build_creation_job(session_id=session_id, status="completed", timestamp=timestamp)
    progress = build_creation_progress_snapshot(session_id=session_id, status="completed")
    session = result.get("session")
    if isinstance(session, dict):
        session = _attach_creation_metadata(session, job, progress)
        result = {**result, "session": session, "game": session.get("state", result.get("game", {}))}
    return {**result, "creation_job": job, "creation_progress": progress}


def get_new_game_creation_job(job_id_or_session_id: str) -> dict[str, Any]:
    session_id = _session_id_from_job_id(job_id_or_session_id)
    if not session_id:
        return {"ok": False, "error": "missing_creation_job_id"}
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "creation_job_not_found", "job_id": job_id_or_session_id}
    runtime_state = dict(session.get("runtime_state") or {})
    job = dict(runtime_state.get("creation_job") or {})
    progress = dict(runtime_state.get("creation_progress") or {})
    if not job:
        job = build_creation_job(session_id=session_id, status="completed")
    if not progress:
        progress = build_creation_progress_snapshot(session_id=session_id, status="completed")
    return {
        "ok": True,
        "job_id": job.get("job_id") or creation_job_id(session_id),
        "session_id": session_id,
        "status": job.get("status") or progress.get("status") or "completed",
        "creation_job": job,
        "creation_progress": progress,
    }
