"""Compatibility wrapper for global image queue."""
from __future__ import annotations

from typing import Any, Dict, List

from app.image.job_queue import (
    claim_next_image_job,
    complete_image_job,
    enqueue_image_job,
    list_image_jobs,
    release_image_job,
)


def enqueue_visual_job(*, session_id: str, request_id: str) -> Dict[str, Any]:
    job = enqueue_image_job({
        "session_id": session_id,
        "request_id": request_id,
        "source": "rpg",
    })
    # Preserve legacy top-level shape expected by RPG queue runner/routes/tests.
    job["session_id"] = session_id
    job["request_id"] = request_id
    print("[RPG][visual/enqueue]", {"job_id": job.get("job_id"), "session_id": session_id, "request_id": request_id, "payload": job.get("payload")})
    return job


def claim_next_visual_job(*, lease_seconds: int = 300) -> Dict[str, Any]:
    # app.image.job_queue.claim_next_image_job does not accept lease_seconds.
    # Claim first, then let the image queue own its default lease behavior.
    job = claim_next_image_job()
    if isinstance(job, dict):
        payload = job.get("payload") or {}
        if not job.get("session_id"):
            job["session_id"] = payload.get("session_id")
        if not job.get("request_id"):
            job["request_id"] = payload.get("request_id")
    print("[RPG][visual/claim]", {"job": job})
    return job or {}


def complete_visual_job(*, job_id: str, lease_token: str, error: str = "") -> Dict[str, Any]:
    result = {
        "error": error,
        "status": "failed" if error else "complete",
    }
    return complete_image_job(job_id, lease_token, result) or {}


def release_visual_job(*, job_id: str, lease_token: str, error: str = "") -> Dict[str, Any]:
    return release_image_job(job_id, lease_token) or {}


def list_visual_jobs() -> List[Dict[str, Any]]:
    return list_image_jobs()


def normalize_visual_queue() -> Dict[str, Any]:
    jobs = list_image_jobs()
    return {"jobs": jobs, "total": len(jobs)}


def prune_completed_visual_jobs(*, keep_last: int = 200) -> Dict[str, Any]:
    jobs = list_image_jobs()
    return {
        "kept": len(jobs),
        "active": len([j for j in jobs if j.get("status") not in {"complete", "failed"}]),
        "finished_kept": len([j for j in jobs if j.get("status") in {"complete", "failed"}]),
    }


__all__ = [
    "enqueue_visual_job",
    "claim_next_visual_job",
    "complete_visual_job",
    "release_visual_job",
    "list_visual_jobs",
    "normalize_visual_queue",
    "prune_completed_visual_jobs",
]
