"""Legacy image queue compatibility facade over durable shared jobs."""
from __future__ import annotations

from datetime import datetime
from typing import Any


def enqueue_image_job(
    payload: dict[str, Any],
    *,
    owner_id: str | None = None,
    priority: int = 0,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Submit a legacy image request through the authoritative shared job store."""
    from app.image.jobs import enqueue_image_job as enqueue_image_feature_job
    from app.jobs.store import default_job_store

    job = enqueue_image_feature_job(
        default_job_store(),
        payload=dict(payload or {}),
        owner_id=owner_id,
        priority=priority,
        idempotency_key=idempotency_key,
    )
    return _legacy_job_view(job)


def claim_next_image_job() -> dict[str, Any] | None:
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


def complete_image_job(job_id: str, lease_token: str, result: dict[str, Any]):
    from app.jobs.models import CompleteJobRequest, FailJobRequest
    from app.jobs.store import default_job_store

    store = default_job_store()
    job = store.get_job(job_id)
    if not _lease_matches(job, lease_token):
        return None
    lease = job.lease
    error = str((result or {}).get("error") or "").strip()
    if error:
        failed = store.fail_job(
            job_id,
            FailJobRequest(
                worker_id=lease.worker_id,
                lease_token=lease_token,
                code="legacy_image_job_failed",
                message=error,
                retryable=False,
            ),
        )
        return _legacy_job_view(failed) if failed else None
    completed = store.complete_job(
        job_id,
        CompleteJobRequest(
            worker_id=lease.worker_id,
            lease_token=lease_token,
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


def release_image_job(job_id: str, token: str, *, reason: str = ""):
    """Release a legacy lease through the shared job protocol."""
    from app.jobs.models import ReleaseJobRequest
    from app.jobs.store import default_job_store

    store = default_job_store()
    job = store.get_job(job_id)
    if not _lease_matches(job, token):
        return None
    released = store.release_job(
        job_id,
        ReleaseJobRequest(
            worker_id=job.lease.worker_id,
            lease_token=token,
            reason=reason,
        ),
    )
    return _legacy_job_view(released) if released else None


def list_image_jobs() -> list[dict[str, Any]]:
    from app.jobs.store import default_job_store

    return [
        _legacy_job_view(job)
        for job in default_job_store().list_jobs()
        if job.type == "image.generate" or job.module in {"image", "image-generation"}
    ]


def _lease_matches(job: Any, token: str) -> bool:
    return bool(job is not None and job.lease is not None and job.lease.token == token)


def _legacy_output_refs(result: dict[str, Any] | None) -> list[dict[str, Any]]:
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


def _legacy_job_view(job: Any) -> dict[str, Any]:
    status = getattr(getattr(job, "status", None), "value", str(getattr(job, "status", "queued")))
    if status == "completed":
        status = "complete"
    lease = getattr(job, "lease", None)
    result: dict[str, Any] | None = None
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
        "error": error.message if error is not None else None,
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
