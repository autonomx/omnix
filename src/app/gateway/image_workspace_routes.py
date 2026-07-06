"""Bounded browser projections for the Image Generation workspace."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, Query

from app.assets import AssetListResponse, AssetType, default_asset_store
from app.jobs import JobListResponse, SQLiteJobStore, default_job_store

from .job_summaries import summarize_job

_ROUTE_SENTINEL = "_omnix_image_workspace_routes_registered"
_HOOK_SENTINEL = "_omnix_image_workspace_routes_hook_installed"
DEFAULT_IMAGE_JOB_LIMIT = 25
MAX_IMAGE_JOB_LIMIT = 100
DEFAULT_IMAGE_ASSET_LIMIT = 100
MAX_IMAGE_ASSET_LIMIT = 250


def register_image_workspace_routes(gateway: FastAPI) -> None:
    """Register bounded jobs and assets routes for image-generation UI state."""

    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.get("/api/image-generation/jobs", response_model=JobListResponse, include_in_schema=False)
    def image_jobs(limit: int = Query(default=DEFAULT_IMAGE_JOB_LIMIT, ge=1, le=MAX_IMAGE_JOB_LIMIT)) -> JobListResponse:
        jobs = _recent_image_jobs(default_job_store(), limit)
        return JobListResponse(jobs=[summarize_job(job) for job in jobs])

    @gateway.get("/api/image-generation/assets", response_model=AssetListResponse, include_in_schema=False)
    def image_assets(limit: int = Query(default=DEFAULT_IMAGE_ASSET_LIMIT, ge=1, le=MAX_IMAGE_ASSET_LIMIT)) -> AssetListResponse:
        assets = [
            asset
            for asset in default_asset_store().list_assets().assets
            if asset.type == AssetType.IMAGE and asset.module in {"image", "image-generation"}
        ]
        assets.sort(key=lambda asset: (asset.created_at, asset.id), reverse=True)
        return AssetListResponse(assets=assets[:limit])


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
    return [
        job
        for job in store.list_jobs()
        if job.type == "image.generate" or job.module in {"image", "image-generation"}
    ][:limit]


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
