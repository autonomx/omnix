"""Phase 12.13 — File-backed visual job queue."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


_QUEUE_DIR_ENV = "RPG_VISUAL_QUEUE_DIR"
_DEFAULT_QUEUE_DIR = "data/rpg/visual_queue"
_QUEUE_FILE = "queue.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _queue_dir() -> str:
    return os.getenv(_QUEUE_DIR_ENV, _DEFAULT_QUEUE_DIR).strip() or _DEFAULT_QUEUE_DIR


def _queue_path() -> str:
    return os.path.join(_queue_dir(), _QUEUE_FILE)


def _ensure_queue_dir() -> None:
    os.makedirs(_queue_dir(), exist_ok=True)


def _read_queue() -> Dict[str, Any]:
    _ensure_queue_dir()
    path = _queue_path()
    if not os.path.exists(path):
        return {"jobs": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"jobs": []}
    jobs = _safe_list(data.get("jobs"))
    return {"jobs": [_normalize_job(job) for job in jobs]}


def _write_queue(data: Dict[str, Any]) -> None:
    _ensure_queue_dir()
    path = _queue_path()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _normalize_job(value: Any) -> Dict[str, Any]:
    data = _safe_dict(value)
    return {
        "job_id": _safe_str(data.get("job_id")).strip() or f"job:{uuid.uuid4().hex}",
        "request_id": _safe_str(data.get("request_id")).strip(),
        "session_id": _safe_str(data.get("session_id")).strip(),
        "status": _safe_str(data.get("status")).strip() or "queued",
        "lease_token": _safe_str(data.get("lease_token")).strip(),
        "lease_expires_at": _safe_str(data.get("lease_expires_at")).strip(),
        "created_at": _safe_str(data.get("created_at")).strip() or _utc_now_iso(),
        "updated_at": _safe_str(data.get("updated_at")).strip() or _utc_now_iso(),
        "completed_at": _safe_str(data.get("completed_at")).strip(),
        "error": _safe_str(data.get("error")).strip(),
    }


def enqueue_visual_job(*, session_id: str, request_id: str) -> Dict[str, Any]:
    state = _read_queue()
    jobs = _safe_list(state.get("jobs"))
    session_id = _safe_str(session_id).strip()
    request_id = _safe_str(request_id).strip()

    for existing in jobs:
        existing = _normalize_job(existing)
        if existing["session_id"] == session_id and existing["request_id"] == request_id and existing["status"] in {"queued", "leased"}:
            return existing

    job = _normalize_job(
        {
            "job_id": f"job:{uuid.uuid4().hex}",
            "session_id": session_id,
            "request_id": request_id,
            "status": "queued",
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
    )
    jobs.append(job)
    jobs.sort(key=lambda item: (item.get("created_at") or "", item.get("job_id") or ""))
    state["jobs"] = jobs
    _write_queue(state)
    return job


def claim_next_visual_job(*, lease_seconds: int = 300) -> Dict[str, Any]:
    state = _read_queue()
    jobs = [_normalize_job(job) for job in _safe_list(state.get("jobs"))]
    now = _utc_now()
    now_iso = now.isoformat()

    selected = None
    for idx, job in enumerate(jobs):
        lease_expires_at = _safe_str(job.get("lease_expires_at")).strip()
        lease_valid = False
        if lease_expires_at:
            try:
                lease_valid = datetime.fromisoformat(lease_expires_at) > now
            except Exception:
                lease_valid = False

        if job["status"] == "queued" or (job["status"] == "leased" and not lease_valid):
            selected = idx
            break

    if selected is None:
        return {}

    job = jobs[selected]
    lease_token = f"lease:{uuid.uuid4().hex}"
    job["status"] = "leased"
    job["lease_token"] = lease_token
    job["lease_expires_at"] = (now + timedelta(seconds=max(30, int(lease_seconds)))).isoformat()
    job["updated_at"] = now_iso
    jobs[selected] = job
    state["jobs"] = jobs
    _write_queue(state)
    return job


def complete_visual_job(*, job_id: str, lease_token: str, error: str = "") -> Dict[str, Any]:
    state = _read_queue()
    jobs = [_normalize_job(job) for job in _safe_list(state.get("jobs"))]
    now_iso = _utc_now_iso()

    for idx, job in enumerate(jobs):
        if job["job_id"] != _safe_str(job_id).strip():
            continue
        if job["lease_token"] != _safe_str(lease_token).strip():
            return {}
        job["status"] = "failed" if _safe_str(error).strip() else "complete"
        job["error"] = _safe_str(error).strip()
        job["lease_token"] = ""
        job["lease_expires_at"] = ""
        job["updated_at"] = now_iso
        job["completed_at"] = now_iso
        jobs[idx] = job
        state["jobs"] = jobs
        _write_queue(state)
        return job
    return {}


def release_visual_job(*, job_id: str, lease_token: str, error: str = "") -> Dict[str, Any]:
    state = _read_queue()
    jobs = [_normalize_job(job) for job in _safe_list(state.get("jobs"))]
    now_iso = _utc_now_iso()
    for idx, job in enumerate(jobs):
        if job["job_id"] != _safe_str(job_id).strip():
            continue
        if job["lease_token"] != _safe_str(lease_token).strip():
            return {}
        job["status"] = "queued"
        job["error"] = _safe_str(error).strip()
        job["lease_token"] = ""
        job["lease_expires_at"] = ""
        job["updated_at"] = now_iso
        jobs[idx] = job
        state["jobs"] = jobs
        _write_queue(state)
        return job
    return {}


def list_visual_jobs() -> List[Dict[str, Any]]:
    state = _read_queue()
    return [_normalize_job(job) for job in _safe_list(state.get("jobs"))]


def prune_completed_visual_jobs(*, keep_last: int = 200) -> Dict[str, Any]:
    state = _read_queue()
    jobs = [_normalize_job(job) for job in _safe_list(state.get("jobs"))]
    active = [job for job in jobs if job["status"] not in {"complete", "failed"}]
    finished = [job for job in jobs if job["status"] in {"complete", "failed"}]
    finished.sort(key=lambda item: (item.get("completed_at") or "", item.get("job_id") or ""))
    finished = finished[-max(0, int(keep_last)):]
    new_jobs = active + finished
    new_jobs.sort(key=lambda item: (item.get("created_at") or "", item.get("job_id") or ""))
    state["jobs"] = new_jobs
    _write_queue(state)
    return {"kept": len(new_jobs), "active": len(active), "finished_kept": len(finished)}