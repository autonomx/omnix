"""Global image job queue (IMG-4)."""
from __future__ import annotations

import time
import uuid
from typing import Dict, Any, List

_QUEUE: List[Dict[str, Any]] = []


def enqueue_image_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    job = {
        "job_id": f"job:{uuid.uuid4().hex}",
        "status": "queued",
        "payload": payload,
        "created_at": time.time(),
        "updated_at": time.time(),
        "lease_token": "",
        "lease_expires_at": 0,
    }
    _QUEUE.append(job)
    return job


def claim_next_image_job() -> Dict[str, Any] | None:
    now = time.time()
    for job in _QUEUE:
        if job["status"] == "queued" or job["lease_expires_at"] < now:
            token = uuid.uuid4().hex
            job["status"] = "leased"
            job["lease_token"] = token
            job["lease_expires_at"] = now + 30
            return job
    return None


def complete_image_job(job_id: str, token: str, result: Dict[str, Any]):
    for job in _QUEUE:
        if job["job_id"] == job_id and job["lease_token"] == token:
            job["status"] = "complete"
            job["result"] = result
            job["updated_at"] = time.time()
            return job
    return None


def release_image_job(job_id: str, token: str):
    for job in _QUEUE:
        if job["job_id"] == job_id and job["lease_token"] == token:
            job["status"] = "queued"
            job["lease_token"] = ""
            job["lease_expires_at"] = 0
            return job
    return None


def list_image_jobs():
    return _QUEUE
