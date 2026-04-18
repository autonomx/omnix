"""Phase 12.13.5 — File-backed visual job queue with hardening."""
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


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO 8601 datetime string and return a datetime or None."""
    value = _safe_str(value).strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _lease_is_valid(job: Dict[str, Any], *, now: datetime | None = None) -> bool:
    """Check if a leased job has a valid (unexpired) lease."""
    now = now or _utc_now()
    if _safe_str(job.get("status")).strip() != "leased":
        return False
    lease_expires_at = _parse_iso(_safe_str(job.get("lease_expires_at")).strip())
    if lease_expires_at is None:
        return False
    return lease_expires_at > now


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
        "attempts": int(data.get("attempts") or 0),
    }


def _job_sort_key(job: Dict[str, Any]) -> tuple[str, str]:
    return (_safe_str(job.get("created_at")).strip(), _safe_str(job.get("job_id")).strip())


def _dedupe_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep at most one active job per (session_id, request_id).

    Prefer leased(valid) > queued > leased(stale) > complete/failed.
    """
    now = _utc_now()
    grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
    for job in jobs:
        job = _normalize_job(job)
        key = (_safe_str(job.get("session_id")).strip(), _safe_str(job.get("request_id")).strip())
        grouped.setdefault(key, []).append(job)

    out: List[Dict[str, Any]] = []
    for _key, bucket in grouped.items():
        bucket = [_normalize_job(item) for item in bucket]

        def _rank(item: Dict[str, Any]) -> tuple[int, str, str]:
            status = _safe_str(item.get("status")).strip()
            if status == "leased" and _lease_is_valid(item, now=now):
                return (0, _safe_str(item.get("created_at")).strip(), _safe_str(item.get("job_id")).strip())
            if status == "queued":
                return (1, _safe_str(item.get("created_at")).strip(), _safe_str(item.get("job_id")).strip())
            if status == "leased":
                return (2, _safe_str(item.get("created_at")).strip(), _safe_str(item.get("job_id")).strip())
            return (3, _safe_str(item.get("created_at")).strip(), _safe_str(item.get("job_id")).strip())

        bucket.sort(key=_rank)
        winner = bucket[0]
        out.append(winner)

        # Preserve completed/failed history only when it is not shadowing an active job.
        winner_status = _safe_str(winner.get("status")).strip()
        if winner_status in {"complete", "failed"}:
            for extra in bucket[1:]:
                if _safe_str(extra.get("status")).strip() in {"complete", "failed"}:
                    out.append(extra)

    out.sort(key=_job_sort_key)
    return out


def normalize_visual_queue() -> Dict[str, Any]:
    """Rewrite queue into canonical deduped form and reclaim stale leases."""
    state = _read_queue()
    jobs = [_normalize_job(job) for job in _safe_list(state.get("jobs"))]
    now = _utc_now()

    repaired: List[Dict[str, Any]] = []
    for job in jobs:
        job = _normalize_job(job)
        if _safe_str(job.get("status")).strip() == "leased" and not _lease_is_valid(job, now=now):
            job["status"] = "queued"
            job["lease_token"] = ""
            job["lease_expires_at"] = ""
            job["updated_at"] = now.isoformat()
        repaired.append(job)

    repaired = _dedupe_jobs(repaired)
    state["jobs"] = repaired
    _write_queue(state)
    return {"jobs": repaired, "total": len(repaired)}


def enqueue_visual_job(*, session_id: str, request_id: str) -> Dict[str, Any]:
    state = _read_queue()
    jobs = [_normalize_job(job) for job in _safe_list(state.get("jobs"))]
    session_id = _safe_str(session_id).strip()
    request_id = _safe_str(request_id).strip()
    now = _utc_now()
    now_iso = now.isoformat()

    # Fresh requests should not be shadowed by stale queued/leased jobs that share the
    # same target prefix. Example:
    #   portrait:npc_guard_captain:2:20260418...
    # should replace old queued/leased jobs starting with:
    #   portrait:npc_guard_captain:2:
    prefix = ""
    parts = request_id.split(":")
    if len(parts) >= 3:
        prefix = ":".join(parts[:3]) + ":"

    # Reclaim stale leased jobs first.
    for idx, existing in enumerate(jobs):
        if (
            _safe_str(existing.get("session_id")).strip() == session_id
            and _safe_str(existing.get("request_id")).strip() == request_id
            and _safe_str(existing.get("status")).strip() == "leased"
            and not _lease_is_valid(existing, now=now)
        ):
            existing["status"] = "queued"
            existing["lease_token"] = ""
            existing["lease_expires_at"] = ""
            existing["updated_at"] = now_iso
            jobs[idx] = existing

    # Drop queued/leased jobs shadowing this same request family.
    if prefix:
        jobs = [
            existing for existing in jobs
            if not (
                _safe_str(existing.get("session_id")).strip() == session_id
                and _safe_str(existing.get("status")).strip() in {"queued", "leased"}
                and _safe_str(existing.get("request_id")).strip().startswith(prefix)
            )
        ]

    for existing in jobs:
        if (
            _safe_str(existing.get("session_id")).strip() == session_id
            and _safe_str(existing.get("request_id")).strip() == request_id
            and _safe_str(existing.get("status")).strip() in {"queued", "leased"}
        ):
            state["jobs"] = _dedupe_jobs(jobs)
            _write_queue(state)
            return existing

    job = _normalize_job(
        {
            "job_id": f"job:{uuid.uuid4().hex}",
            "session_id": session_id,
            "request_id": request_id,
            "status": "queued",
            "created_at": now_iso,
            "updated_at": now_iso,
            "attempts": 0,
        }
    )
    jobs.append(job)
    state["jobs"] = _dedupe_jobs(jobs)
    _write_queue(state)
    return job


def claim_next_visual_job(*, lease_seconds: int = 300) -> Dict[str, Any]:
    """Claim the next available queued job and mark it as leased."""
    normalize_visual_queue()
    state = _read_queue()
    jobs = [_normalize_job(job) for job in _safe_list(state.get("jobs"))]
    now = _utc_now()
    now_iso = now.isoformat()

    selected = None
    for idx, job in enumerate(jobs):
        if _safe_str(job.get("status")).strip() == "queued":
            selected = idx
            break

    if selected is None:
        return {}

    job = jobs[selected]
    lease_token = f"lease:{uuid.uuid4().hex}"
    job["status"] = "leased"
    job["lease_token"] = lease_token
    actual_lease = max(30, int(lease_seconds or 0))
    job["lease_expires_at"] = (now + timedelta(seconds=actual_lease)).isoformat()
    job["updated_at"] = now_iso
    job["attempts"] = int(job.get("attempts") or 0) + 1
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
        state["jobs"] = _dedupe_jobs(jobs)
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
        state["jobs"] = _dedupe_jobs(jobs)
        _write_queue(state)
        return job
    return {}


def list_visual_jobs() -> List[Dict[str, Any]]:
    normalize_visual_queue()
    state = _read_queue()
    return [_normalize_job(job) for job in _safe_list(state.get("jobs"))]


def prune_completed_visual_jobs(*, keep_last: int = 200) -> Dict[str, Any]:
    normalize_visual_queue()
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