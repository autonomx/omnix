"""Phase 12.13.5 — Queue runner for visual jobs with request-state awareness."""
from __future__ import annotations

from typing import Any, Dict

from app.rpg.session.durable_store import load_session_from_disk, save_session_to_disk
from app.rpg.visual.worker import process_pending_image_requests

from .job_queue import (
    claim_next_visual_job,
    complete_visual_job,
    release_visual_job,
)


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _find_request(simulation_state: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Locate an image request by request_id inside simulation state."""
    simulation_state = _safe_dict(simulation_state)
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))
    visual_state = _safe_dict(presentation_state.get("visual_state"))
    requests = visual_state.get("image_requests")
    if not isinstance(requests, list):
        return {}
    for item in requests:
        item = _safe_dict(item)
        if _safe_str(item.get("request_id")).strip() == _safe_str(request_id).strip():
            return item
    return {}


def run_one_queued_job(*, lease_seconds: int = 300) -> Dict[str, Any]:
    """Claim the next queued visual job, run canonical processing, then settle queue state."""
    job = claim_next_visual_job(lease_seconds=lease_seconds)
    if not job:
        return {"ok": True, "processed": False, "reason": "no_job_available"}

    job_id = _safe_str(job.get("job_id")).strip()
    lease_token = _safe_str(job.get("lease_token")).strip()
    session_id = _safe_str(job.get("session_id")).strip()
    request_id = _safe_str(job.get("request_id")).strip()

    if not job_id or not lease_token:
        return {"ok": False, "error": "invalid_job_state"}

    try:
        session = load_session_from_disk(session_id) or {}
        simulation_state = _safe_dict(session.get("simulation_state"))
        simulation_state = process_pending_image_requests(simulation_state, limit=1)
        session["simulation_state"] = simulation_state
        save_session_to_disk(session)
    except Exception as exc:
        release_visual_job(job_id=job_id, lease_token=lease_token, error=_safe_str(exc).strip()[:500])
        return {
            "ok": False,
            "error": _safe_str(exc).strip()[:500],
            "processed": False,
        }

    request_record = _find_request(simulation_state, request_id)
    if not request_record:
        release_visual_job(job_id=job_id, lease_token=lease_token, error="request_not_found_after_run")
        return {
            "ok": False,
            "processed": False,
            "error": "request_not_found_after_run",
            "job_id": job_id,
            "session_id": session_id,
            "request_id": request_id,
        }

    request_status = _safe_str(request_record.get("status")).strip()
    request_error = _safe_str(request_record.get("error")).strip()

    if request_status in {"complete", "failed", "blocked"}:
        complete_visual_job(
            job_id=job_id,
            lease_token=lease_token,
            error=request_error if request_status in {"failed", "blocked"} else "",
        )
    elif request_status == "pending":
        # retryable/transient path: requeue the job
        release_visual_job(job_id=job_id, lease_token=lease_token, error=request_error)
    else:
        release_visual_job(
            job_id=job_id, lease_token=lease_token, error=f"unexpected_request_status:{request_status}"
        )
        return {
            "ok": False,
            "processed": False,
            "error": f"unexpected_request_status:{request_status}",
            "job_id": job_id,
            "session_id": session_id,
            "request_id": request_id,
        }

    return {
        "ok": True,
        "processed": True,
        "job_id": job_id,
        "session_id": session_id,
        "request_id": request_id,
        "request_status": request_status,
    }