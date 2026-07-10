"""Bounded browser projections and actions for the Image Generation workspace."""
from __future__ import annotations

from functools import wraps
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query

from app.assets import AssetListResponse, AssetRecord, AssetType, default_asset_store
from app.jobs import CreateJobRequest, JobListResponse, JobRecord, JobStatus, SQLiteJobStore, default_job_store

from .job_summaries import summarize_job

_ROUTE_SENTINEL = "_omnix_image_workspace_routes_registered"
_HOOK_SENTINEL = "_omnix_image_workspace_routes_hook_installed"
DEFAULT_IMAGE_JOB_LIMIT = 25
MAX_IMAGE_JOB_LIMIT = 100
DEFAULT_IMAGE_ASSET_LIMIT = 100
MAX_IMAGE_ASSET_LIMIT = 250
RETRYABLE_IMAGE_JOB_STATUSES = {JobStatus.FAILED, JobStatus.CANCELED, JobStatus.STALE}
SUPPORTED_IMAGE_MIME_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}


def register_image_workspace_routes(gateway: FastAPI) -> None:
    """Register bounded jobs/assets routes and image-specific actions."""

    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get("/api/image-generation/jobs", response_model=JobListResponse, include_in_schema=False)
    def image_jobs(limit: int = Query(default=DEFAULT_IMAGE_JOB_LIMIT, ge=1, le=MAX_IMAGE_JOB_LIMIT)) -> JobListResponse:
        try:
            store = default_job_store()
            jobs = _recent_image_jobs(store, limit)
            jobs = _prune_deleted_image_asset_jobs(store, jobs)
        except Exception:
            jobs = []
        summaries = []
        for job in jobs:
            try:
                summaries.append(summarize_job(job))
            except Exception:
                continue
        return JobListResponse(jobs=summaries)

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
        job_store = default_job_store()
        assets = [
            asset
            for asset in default_asset_store().list_assets().assets
            if asset.type == AssetType.IMAGE
            and asset.module in {"image", "image-generation"}
            and _is_usable_image_asset(asset)
            and not _is_character_avatar_asset(asset, job_store)
        ]
        assets.sort(key=lambda asset: (asset.created_at, asset.id), reverse=True)
        return AssetListResponse(assets=assets[:limit])

    @gateway.delete("/api/image-generation/assets/{asset_id}", include_in_schema=False)
    @gateway.post("/api/image-generation/assets/{asset_id}/delete", include_in_schema=False)
    def delete_image_asset(asset_id: str) -> dict[str, Any]:
        store = default_asset_store()
        asset = next((item for item in store.list_assets().assets if item.id == asset_id), None)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        if asset.type != AssetType.IMAGE or asset.module not in {"image", "image-generation"}:
            raise HTTPException(status_code=409, detail="asset_not_image_generation")

        shared_result = store.delete_asset(asset_id)
        legacy_result: dict[str, Any] | None = None
        legacy_asset_id = str((asset.compat or {}).get("legacy_asset_id") or "").strip()
        if legacy_asset_id:
            from app.image.asset_store import delete_image_asset as delete_legacy_image_asset

            legacy_result = delete_legacy_image_asset(
                legacy_asset_id,
                delete_file=not bool(shared_result.get("file_deleted")),
            )

        deleted = bool(shared_result.get("deleted")) or bool((legacy_result or {}).get("deleted"))
        if not deleted:
            raise HTTPException(status_code=404, detail="asset_not_deletable")

        _delete_jobs_for_image_asset(asset)

        result: dict[str, Any] = {
            "ok": True,
            "asset_id": asset_id,
            "deleted": True,
            "file_deleted": bool(shared_result.get("file_deleted"))
            or bool((legacy_result or {}).get("file_deleted")),
        }
        file_error = str(shared_result.get("file_error") or (legacy_result or {}).get("file_error") or "").strip()
        if file_error:
            result["file_error"] = file_error
        return result


def _is_usable_image_asset(asset: AssetRecord) -> bool:
    if str(asset.mime_type or "").lower() not in SUPPORTED_IMAGE_MIME_TYPES:
        return False
    storage_path = str(asset.storage_path or "").strip()
    if not storage_path:
        return False
    path = Path(storage_path)
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _is_character_avatar_asset(asset: AssetRecord, job_store: SQLiteJobStore) -> bool:
    source_job_id = str(asset.source_job_id or "").strip()
    if not source_job_id:
        return False
    source_job = job_store.get_job(source_job_id)
    return bool(source_job and source_job.module == "character-avatar")


def _delete_jobs_for_image_asset(asset: AssetRecord) -> None:
    job_ids = {str(asset.source_job_id or "").strip()}
    legacy_asset_id = str((asset.compat or {}).get("legacy_asset_id") or "").strip()
    asset_ids = {asset.id}
    if legacy_asset_id:
        asset_ids.add(legacy_asset_id)

    try:
        store = default_job_store()
        for job in store.list_jobs():
            if not _is_image_job(job):
                continue
            if _job_references_image_asset(job, asset_ids):
                job_ids.add(job.id)
        delete_job = getattr(store, "delete_job", None)
        if not callable(delete_job):
            return
        for job_id in sorted(job_id for job_id in job_ids if job_id):
            delete_job(job_id)
    except Exception:
        return


def _prune_deleted_image_asset_jobs(store: Any, jobs: list[JobRecord]) -> list[JobRecord]:
    delete_job = getattr(store, "delete_job", None)
    if not callable(delete_job):
        return jobs
    try:
        current_image_asset_ids = {
            asset.id
            for asset in default_asset_store().list_assets().assets
            if asset.type == AssetType.IMAGE
            and asset.module in {"image", "image-generation"}
            and _is_usable_image_asset(asset)
        }
    except Exception:
        return jobs

    retained: list[JobRecord] = []
    for job in jobs:
        if job.status == JobStatus.COMPLETED and _job_image_asset_ids(job) - current_image_asset_ids:
            try:
                delete_job(job.id)
            except Exception:
                retained.append(job)
            continue
        retained.append(job)
    return retained


def _job_image_asset_ids(job: JobRecord) -> set[str]:
    asset_ids: set[str] = set()
    for ref in getattr(job, "output_refs", []) or []:
        if not isinstance(ref, dict):
            continue
        if str(ref.get("type") or "") != "image":
            continue
        asset_id = str(ref.get("asset_id") or "").strip()
        if asset_id:
            asset_ids.add(asset_id)
    return asset_ids


def _job_references_image_asset(job: JobRecord, asset_ids: set[str]) -> bool:
    return bool(_job_image_asset_ids(job) & asset_ids)


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
        jobs = []
        for row in rows:
            try:
                jobs.append(store._row_to_job(row))  # noqa: SLF001
            except Exception:
                continue
        return jobs
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
