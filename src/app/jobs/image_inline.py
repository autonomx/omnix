"""Background execution and shared asset persistence for image jobs."""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.assets import AssetRecord, AssetType, SharedAssetStore, default_asset_store

from .image_contracts import ImageGenerateInput, ImageOutputRef, image_title_from_prompt
from .models import CompleteJobRequest, FailJobRequest, JobRecord

IMAGE_JOB_TYPE = "image.generate"
IMAGE_EXECUTOR_ENV = "OMNIX_INLINE_IMAGE_JOB_EXECUTOR"


def install_image_job_execution(sqlite_job_store_cls: Any) -> None:
    """Patch job creation once so image jobs execute off the request thread."""

    if getattr(sqlite_job_store_cls, "_omnix_image_jobs_installed", False):
        return
    original_create_job = sqlite_job_store_cls.create_job

    def create_job_with_image_execution(self: Any, request: Any) -> JobRecord:
        job = original_create_job(self, request)
        if job.type == IMAGE_JOB_TYPE and _executor_enabled():
            _start_image_job(self, job)
        return job

    sqlite_job_store_cls.create_job = create_job_with_image_execution
    sqlite_job_store_cls._omnix_image_jobs_installed = True


def _executor_enabled() -> bool:
    return os.environ.get(IMAGE_EXECUTOR_ENV, "1").strip().lower() not in {"0", "false", "off", "disabled"}


def _start_image_job(job_store: Any, job: JobRecord) -> None:
    thread = threading.Thread(
        target=execute_image_job,
        args=(job_store, job),
        name=f"omnix-image-{job.id.removeprefix('job:')[:8]}",
        daemon=True,
    )
    thread.start()


def execute_image_job(
    job_store: Any,
    job: JobRecord,
    *,
    generate_fn: Callable[[dict[str, Any]], Any] | None = None,
    asset_store: SharedAssetStore | None = None,
) -> JobRecord:
    """Run one image job, index its file, and complete the shared job."""

    job_store.mark_running(job.id)
    try:
        request = ImageGenerateInput.model_validate(job.input_payload or {})
        provider_payload = request.provider_payload()
    except ValidationError as exc:
        return _fail(job_store, job, "image_invalid_request", str(exc), retryable=False)
    except ValueError as exc:
        return _fail(job_store, job, "image_provider_unavailable", str(exc), retryable=False)

    if generate_fn is None:
        from app.image.service import generate_image

        generate_fn = generate_image

    try:
        result = generate_fn(provider_payload)
    except Exception as exc:
        return _fail(job_store, job, "image_generation_failed", str(exc) or "Image generation failed", retryable=True)

    if not bool(getattr(result, "ok", False)):
        message = str(getattr(result, "error", "") or "Image generation failed")
        return _fail(
            job_store,
            job,
            "image_generation_failed",
            message,
            retryable=True,
            details={"provider": getattr(result, "provider", ""), "status": getattr(result, "status", "")},
        )

    try:
        asset, output_ref = _store_image_asset(job, request, result, asset_store or default_asset_store())
    except FileNotFoundError as exc:
        return _fail(job_store, job, "image_output_missing", str(exc), retryable=True)
    except Exception as exc:
        return _fail(job_store, job, "image_asset_store_failed", str(exc) or "Image asset could not be stored", retryable=True)

    completed = job_store.complete_job(
        job.id,
        CompleteJobRequest(
            output_refs=[output_ref.model_dump(mode="json")],
            logs=[{"level": "info", "message": "Image generated and stored", "asset_id": asset.id}],
        ),
    )
    return completed or job


def _store_image_asset(
    job: JobRecord,
    request: ImageGenerateInput,
    result: Any,
    store: SharedAssetStore,
) -> tuple[AssetRecord, ImageOutputRef]:
    storage_path = str(getattr(result, "local_path", "") or "").strip()
    if not storage_path or not Path(storage_path).is_file():
        raise FileNotFoundError("Image provider did not produce a readable local file")

    title = image_title_from_prompt(request.prompt)
    provider_key = str(getattr(result, "provider", "") or request.provider_key())
    width = int(getattr(result, "width", 0) or request.width)
    height = int(getattr(result, "height", 0) or request.height)
    mime_type = str(getattr(result, "mime_type", "") or "image/png")
    seed = getattr(result, "seed", request.seed)
    metadata = dict(getattr(result, "metadata", {}) or {})
    asset_id = f"image:image-generation-{job.id.removeprefix('job:')}"

    asset = store.upsert_asset(
        AssetRecord(
            id=asset_id,
            module="image-generation",
            type=AssetType.IMAGE,
            mime_type=mime_type,
            storage_path=storage_path,
            source_job_id=job.id,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "title": title,
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "provider_id": request.provider_id,
                "provider_key": provider_key,
                "width": width,
                "height": height,
                "seed": seed,
                "style": request.style,
                "steps": request.steps,
                "guidance_scale": request.guidance_scale,
                "cache_hit": bool(metadata.get("cache_hit")),
            },
            compat={"contract": "image_generation_asset_v1"},
        )
    )
    output_ref = ImageOutputRef(
        asset_id=asset.id,
        title=title,
        mime_type=mime_type,
        width=width,
        height=height,
        provider_id=request.provider_id,
        seed=seed,
    )
    return asset, output_ref


def _fail(
    job_store: Any,
    job: JobRecord,
    code: str,
    message: str,
    *,
    retryable: bool,
    details: dict[str, Any] | None = None,
) -> JobRecord:
    failed = job_store.fail_job(
        job.id,
        FailJobRequest(
            code=code,
            message=message,
            retryable=retryable,
            details={"job_type": job.type, "module": job.module, **(details or {})},
        ),
    )
    return failed or job
