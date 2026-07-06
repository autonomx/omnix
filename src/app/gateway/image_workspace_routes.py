"""Bounded browser projections and actions for the Image Generation workspace."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query

from app.assets import AssetListResponse, AssetType, default_asset_store
from app.jobs import CreateJobRequest, JobListResponse, JobRecord, JobStatus, SQLiteJobStore, default_job_store

from .job_summaries import summarize_job

_ROUTE_SENTINEL = "_omnix_image_workspace_routes_registered"
_HOOK_SENTINEL = "_omnix_image_workspace_routes_hook_installed"
DEFAULT_IMAGE_JOB_LIMIT = 25
MAX_IMAGE_JOB_LIMIT = 100
DEFAULT_IMAGE_ASSET_LIMIT = 100
MAX_IMAGE_ASSET_LIMIT = 250
RETRYABLE_IMAGE_JOB_STATUSES = {JobStatus.FAILED, JobStatus.CANCELED, JobStatus.STALE}


def register_image_workspace_routes(gateway: FastAPI) -> None:
    """Register bounded jobs/assets routes and image-specific actions."""

    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get("/api/image-generation/jobs", response_model=JobListResponse, include_in_schema=False)
    def image_jobs(limit: int = Query(default=DEFAULT_IMAGE_JOB_LIMIT, ge=1, le=MAX_IMAGE_JOB_LIMIT)) -> JobListResponse:
        jobs = _recent_image_jobs(default_job_store(), limit)
        return JobListResponse(jobs=[summarize_job(job) for job in jobs])

    @gateway.post("/api/image-generation/jobs/{job_id}/retry", response_model=JobRecord, include_in_schema=False)
    def retry_image_job(job_id: str) -> JobRecord:
        store = default_job_store()
        source = store.get_job(job_id)
        if source is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        if not _is_image_job(source):
            raise HTTPException(status_code=409, detail="job_not_image_generation")
        if source.status not in RETRYABLE_IMAGE_JOB_STATUSES:
            raise HTTPException(status_code=409, detail="job_not_retryable")
        return store.create_job(_retry_request(source))

    @gateway.get("/api/image-generation/assets", response_model=AssetListResponse, include_in_schema=False)
    def image_assets(limit: int = Query(default=DEFAULT_IMAGE_ASSET_LIMIT, ge=1, le=MAX_IMAGE_ASSET_LIMIT)) -> AssetListResponse:
        assets = [
            asset
            for asset in default_asset_store().list_assets().assets
            if asset.type == AssetType.IMAGE and asset.module in {"image", "image-generation"}
        ]
        assets.sort(key=lambda asset: (asset.created_at, asset.id), reverse=True)
        return AssetListResponse(assets=assets[:limit])


def _retry_request(source: JobRecord) -> CreateJobRequest:
    return CreateJobRequest(
        owner_id=source.owner_id,
        module=source.module,
        type=source.type,
        resource_class=source.resource_class,
        priority=source.priority,
        stages=[
            {
                "id": stage.id,
                "label": stage.label,
                "status": JobStatus.QUEUED,
                "resource_class": stage.resource_class,
            }
            for stage in source.stages
        ],
        input_ref=source.input_ref,
        input_payload=source.input_payload,
        compat={**source.compat, "retry_of": source.id},
    )


def _is_image_job(job: JobRecord) -> bool:
    return job.type == "image.generate" or job.module in {"image", "image-generation"}


def _recent_image_jobs(store: Any, limit: int) -> list[Any]:
    if isinstance(store, SQLiteJobStore):
        with store._connect() as conn:  # noqa: SLF001 - bounded read adapter
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE type = ? OR module IN (?, ?)
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                ("image.generate", "image", "image-generation", limit),
            ).fetchall()
        return [store._row_to_job(row) for row in rows]  # noqa: SLF001
    return [job for job in store.list_jobs() if _is_image_job(job)][:limit]


def install_image_workspace_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_image_workspace_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
