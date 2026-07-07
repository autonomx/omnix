"""Bounded browser projections and actions for the Image Generation workspace."""
from __future__ import annotations

from functools import wraps
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query

from app.assets import AssetListResponse, AssetRecord, AssetType, default_asset_store
from app.image.cache import forget_image_cache_record
from app.jobs import CreateJobRequest, JobListResponse, JobRecord, JobStatus, SQLiteJobStore, default_job_store
from app.jobs.history_cleanup import purge_terminal_job_history
from app.jobs.models import TERMINAL_STATUSES

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
            jobs = _recent_image_jobs(default_job_store(), limit)
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
        assets = [
            asset
            for asset in default_asset_store().list_assets().assets
            if asset.type == AssetType.IMAGE
            and asset.module in {"image", "image-generation"}
            and _is_usable_image_asset(asset)
        ]
        assets.sort(key=lambda asset: (asset.created_at, asset.id), reverse=True)
        return AssetListResponse(assets=assets[:limit])

    @gateway.delete("/api/image-generation/assets/{asset_id}", include_in_schema=False)
    @gateway.post("/api/image-generation/assets/{asset_id}/delete", include_in_schema=False)
    def delete_image_asset(asset_id: str) -> dict[str, Any]:
        store = default_asset_store()
        all_assets = store.list_assets().assets
        asset = next((item for item in all_assets if item.id == asset_id), None)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset_not_found")
        if asset.type != AssetType.IMAGE or asset.module not in {"image", "image-generation"}:
            raise HTTPException(status_code=409, detail="asset_not_image_generation")

        related_assets = _related_image_assets(all_assets, asset)
        source_job_ids = sorted(
            {
                str(item.source_job_id or "").strip()
                for item in related_assets
                if str(item.source_job_id or "").strip()
            }
        )
        job_store: Any | None = default_job_store() if source_job_ids else None
        for source_job_id in source_job_ids:
            source_job = job_store.get_job(source_job_id) if job_store is not None else None
            if source_job is not None and source_job.status not in TERMINAL_STATUSES:
                raise HTTPException(status_code=409, detail="image_job_still_active")

        forgotten_keys: set[str] = set()
        for item in related_assets:
            cache_key = str((item.metadata or {}).get("cache_key") or "").strip()
            cache_result = forget_image_cache_record(cache_key=cache_key, file_path=item.storage_path)
            forgotten_keys.update(str(key) for key in cache_result.get("forgotten_keys") or [])

        removed_asset_ids: list[str] = []
        file_deleted = False
        file_error = ""
        for item in related_assets:
            shared_result = store.delete_asset(item.id)
            legacy_result: dict[str, Any] | None = None
            legacy_asset_id = str((item.compat or {}).get("legacy_asset_id") or "").strip()
            if legacy_asset_id:
                from app.image.asset_store import delete_image_asset as delete_legacy_image_asset

                legacy_result = delete_legacy_image_asset(
                    legacy_asset_id,
                    delete_file=not bool(shared_result.get("file_deleted")),
                )
            if bool(shared_result.get("deleted")) or bool((legacy_result or {}).get("deleted")):
                removed_asset_ids.append(item.id)
            file_deleted = file_deleted or bool(shared_result.get("file_deleted")) or bool(
                (legacy_result or {}).get("file_deleted")
            )
            file_error = file_error or str(
                shared_result.get("file_error") or (legacy_result or {}).get("file_error") or ""
            ).strip()

        if asset_id not in removed_asset_ids:
            raise HTTPException(status_code=404, detail="asset_not_deletable")

        removed_job_ids: list[str] = []
        events_removed = 0
        if job_store is not None:
            for source_job_id in source_job_ids:
                job_result = purge_terminal_job_history(job_store, source_job_id)
                if job_result.get("job_removed"):
                    removed_job_ids.append(source_job_id)
                events_removed += int(job_result.get("events_removed") or 0)

        result: dict[str, Any] = {
            "ok": True,
            "asset_id": asset_id,
            "deleted": True,
            "file_deleted": file_deleted,
        }
        if len(removed_asset_ids) > 1:
            result["deleted_asset_ids"] = removed_asset_ids
        if forgotten_keys:
            result["cache_keys_removed"] = sorted(forgotten_keys)
        if removed_job_ids:
            result["job_ids_removed"] = removed_job_ids
        if events_removed:
            result["job_events_removed"] = events_removed
        if file_error:
            result["file_error"] = file_error
        return result


def _related_image_assets(assets: list[AssetRecord], target: AssetRecord) -> list[AssetRecord]:
    target_path = _normalized_path(target.storage_path)
    target_cache_key = str((target.metadata or {}).get("cache_key") or "").strip()
    related: list[AssetRecord] = []
    for asset in assets:
        if asset.type != AssetType.IMAGE or asset.module not in {"image", "image-generation"}:
            continue
        same_path = bool(target_path and _normalized_path(asset.storage_path) == target_path)
        cache_key = str((asset.metadata or {}).get("cache_key") or "").strip()
        same_cache_key = bool(target_cache_key and cache_key == target_cache_key)
        if asset.id == target.id or same_path or same_cache_key:
            related.append(asset)
    return related


def _normalized_path(value: str) -> str:
    path = str(value or "").strip()
    return str(Path(path).resolve()) if path else ""


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
