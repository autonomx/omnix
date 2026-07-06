"""Legacy image queue compatibility facade over durable shared jobs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def enqueue_image_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Submit a legacy image request through the authoritative shared job store."""
    from app.jobs.adapters import enqueue_image_job as enqueue_shared_image_job
    from app.jobs.store import default_job_store

    job = enqueue_shared_image_job(default_job_store(), payload=dict(payload or {}))
    return _legacy_job_view(job)


def claim_next_image_job() -> Dict[str, Any] | None:
    from app.jobs.models import ClaimJobRequest, ResourceClass
    from app.jobs.store import default_job_store

    response = default_job_store().claim_next(
        ClaimJobRequest(
            worker_id="legacy-image-worker",
            resource_classes=[ResourceClass.GPU_IMAGE],
            lease_seconds=30,
        )
    )
    if not response.ok or response.job is None:
        return None
    return _legacy_job_view(response.job)


def complete_image_job(job_id: str, lease_token: str, result: Dict[str, Any]):
    from app.jobs.models import CompleteJobRequest
    from app.jobs.store import default_job_store

    store = default_job_store()
    job = store.get_job(job_id)
    if not _lease_matches(job, lease_token):
        return None
    completed = store.complete_job(
        job_id,
        CompleteJobRequest(
            output_refs=_legacy_output_refs(result),
            logs=[{"level": "info", "message": "Legacy image worker completed shared job"}],
        ),
    )
    return _legacy_job_view(completed) if completed else None


def fail_image_job(job_id: str, lease_token: str, error: str):
    from app.jobs.models import FailJobRequest
    from app.jobs.store import default_job_store

    store = default_job_store()
    job = store.get_job(job_id)
    if not _lease_matches(job, lease_token):
        return None
    failed = store.fail_job(
        job_id,
        FailJobRequest(
            code="legacy_image_job_failed",
            message=str(error or "Image generation failed"),
            retryable=True,
            details={"legacy_system": "src/app/image/job_queue.py"},
         ),
    )
    return _legacy_job_view(failed) if failed else None


def release_image_job(job_id: str, token: str):
    """Release a legacy lease without restoring an in-memory shadow queue."""
    from app.jobs.models import JobStatus
    from app.jobs.store import default_job_store

    store = default_job_store()
    job = store.get_job(job_id)
    if not _lease_matches(job, token):
        return None
    job.status = JobStatus.QUEUED
    job.lease = None
    job.updated_at = datetime.now(timezone.utc).isoformat()
    with store._connect() as conn:  # noqa: RLF001 - compatibility facade
        store._update_job(conn, job)  # noqa: SLF001
        store._append_event(conn, job.id, "job.updated", job.model_dump(mode="json"))  # noqa: SLF001
    return _legacy_job_view(job)


def list_image_jobs() -> List[Dict[str, Any]]:
    from app.jobs.store import default_job_store

    return [
        _legacy_job_view(job)
        for job in default_job_store().list_jobs()
        if job.type == "image.generate" or job.module in {"image", "image-generation"}
    ]


def _lease_matches(job: Any, token: str) -> bool:
    return bool(job is not None and job.lease is not None and job.lease.token == token)


def _legacy_output_refs(result: Dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = dict(result or {})
    asset_id = str(payload.get("asset_id") or "").strip()
    if not asset_id:
        return []
    allowed = {
        "type": "image",
        "asset_id": asset_id,
        "title": str(payload.get("title") or "Generated image"),
        "mime_type": str(payload.get("mime_type") or "image/png"),
    }
    for key in ("width", "height", "provider_id", "seed"):
        if payload.get(key) is not None:
            allowed[key] = payload[key]
    return [allowed]


def _legacy_job_view(job: Any) -> Dict[str, Any]:
    status = getattr(getattr(job, "status", None), "value", str(getattr(job, "status", "queued")))
    if status == "completed":
        status = "complete"
    lease = getattr(job, "lease", None)
    result: Dict[str, Any] | None = None
    output_refs = list(getattr(job, "output_refs", []) or [])
    if output_refs:
        result = dict(output_refs[0])
    error = getattr(job, "error", None)
    if error is not None:
        result = {"error": error.message, "status": "failed", "code": error.code}
    return {
        "job_id": job.id,
        "shared_job_id": job.id,
        "status": status,
        "payload": dict(getattr(job, "input_payload", {}) or {}),
        "result": result,
        "created_at": _epoch(getattr(job, "created_at", None)),
        "updated_at": _epoch(getattr(job, "updated_at", None)),
        "lease_token": getattr(lease, "token", "") if lease else "",
        "lease_expires_at": _epoch(getattr(lease, "expires_at", None)) if lease else 0,
    }


def _epoch(value: str | None) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0
