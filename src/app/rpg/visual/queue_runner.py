"""Phase 12.13 — Visual queue runner.

Queue runner delegates execution to the canonical worker pipeline
(process_pending_image_requests) so that request lifecycle semantics
(max_attempts, status transitions, asset persistence) remain correct.
"""
from __future__ import annotations

from typing import Any, Dict

from app.rpg.session.durable_store import load_session, save_session
from .job_queue import (
    claim_next_visual_job,
    complete_visual_job,
    list_visual_jobs,
    release_visual_job,
)
from .worker import process_pending_image_requests


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _find_request(state: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Locate an image request by request_id inside simulation state."""
    for req in state.get("image_requests", []):
        if isinstance(req, dict) and _safe_str(req.get("request_id")) == request_id:
            return req
    return {}


def run_one_visual_job(*, lease_seconds: int = 300) -> Dict[str, Any]:
    """Claim one queued job, run canonical worker, and reconcile state."""
    job = claim_next_visual_job(lease_seconds=lease_seconds)
    if not job:
        return {"ok": True, "processed": False, "reason": "no_jobs"}

    session_id = _safe_str(job.get("session_id")).strip()
    job_id = _safe_str(job.get("job_id")).strip()
    lease_token = _safe_str(job.get("lease_token")).strip()
    request_id = _safe_str(job.get("request_id")).strip()

    try:
        session = load_session(session_id)
        sim = session.get("simulation_state") or {}

        # Run canonical worker pipeline (enforces max_attempts, status, assets)
        sim = process_pending_image_requests(sim, limit=1)

        session["simulation_state"] = sim
        save_session(session_id, session)

    except Exception as exc:
        release_visual_job(job_id=job_id, lease_token=lease_token, error=_safe_str(exc).strip()[:500])
        return {
            "ok": False,
            "processed": False,
            "job_id": job_id,
            "session_id": session_id,
            "error": _safe_str(exc).strip()[:500],
        }

    # Determine request state AFTER execution
    req = _find_request(sim, request_id)
    status = _safe_str(req.get("status")).strip()

    if status in {"complete", "failed", "blocked"}:
        # Terminal state — mark job done
        complete_visual_job(job_id=job_id, lease_token=lease_token)
    else:
        # Still pending / retryable — release back to queue
        release_visual_job(job_id=job_id, lease_token=lease_token)

    return {"ok": True, "processed": True, "job_id": job_id, "session_id": session_id, "request_status": status}


def get_visual_queue_stats() -> Dict[str, Any]:
    """Return queue statistics."""
    jobs = list_visual_jobs()
    out = {"queued": 0, "leased": 0, "complete": 0, "failed": 0, "total": len(jobs)}
    for job in jobs:
        status = _safe_str(job.get("status")).strip()
        if status in out:
            out[status] += 1
    return out