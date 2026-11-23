"""Background execution and shared asset persistence for image jobs."""
from __future__ import annotations

from app.assets.protocol import AssetStore
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.assets import AssetRecord, AssetType, default_asset_store
from app.jobs.models import JobStatus
from app.runtime.ports import optional

from app.jobs.errors import JobClaimConflict
from app.jobs.handlers import JobRun, PermanentJobError, RetryableJobError
from app.jobs.inline_execution import require_execution_authority
from app.jobs.models import (
    CompleteJobRequest,
    CreateJobRequest,
    JobRecord,
    JobStage,
    ResourceClass,
)

from app.platform.image.contracts import (
    CHARACTER_AVATAR_FINISHER,
    ImageGenerateInput,
    ImageOutputRef,
    image_title_from_prompt,
)

IMAGE_JOB_TYPE = "image.generate"


def enqueue_image_job(
    store: Any,
    *,
    payload: dict[str, Any],
    owner_id: str | None = None,
    priority: int = 0,
    idempotency_key: str | None = None,
) -> JobRecord:
    """Submit image generation through the durable shared job store."""
    request = CreateJobRequest(
        owner_id=owner_id,
        module="image-generation",
        type=IMAGE_JOB_TYPE,
        resource_class=ResourceClass.GPU_IMAGE,
        priority=priority,
        stages=[
            JobStage(
                id="generate-image",
                label="Generate image",
                resource_class=ResourceClass.GPU_IMAGE,
            ),
            JobStage(
                id="store-asset",
                label="Store image asset",
                resource_class=ResourceClass.CPU,
            ),
        ],
        input_payload=payload,
    )
    if idempotency_key is None:
        return store.create_job(request)
    create_once = getattr(store, "create_job_once", None)
    if not callable(create_once):
        raise TypeError("image job store must support idempotent submission")
    return create_once(request, idempotency_key=idempotency_key)


def run_image_job(
    run: JobRun[ImageGenerateInput],
    *,
    generate_fn: Callable[[dict[str, Any]], Any] | None = None,
    asset_store: AssetStore | None = None,
) -> JobRecord:
    """Generate one image, index its file and complete the job; a failure raises under its own code.

    The run completes the job itself, because the avatar finisher reconciles a character's avatars only once
    its job reads as completed.
    """
    job_store, job, request = run.store, run.job, run.input
    _update_progress(
        job_store,
        job.id,
        1,
        4,
        "Preparing image request",
        stage_id="generate-image",
    )
    try:
        provider_payload = request.provider_payload()
    except ValueError as exc:
        raise PermanentJobError("image_provider_unavailable", str(exc)) from exc
    provider_payload["request_id"] = job.id

    if generate_fn is None:
        from app.platform.image.service import generate_image

        generate_fn = generate_image
    provider_payload["_device_permit_priority"] = "batch"

    _update_progress(
        job_store,
        job.id,
        0,
        100,
        "Waiting for image service",
        stage_id="generate-image",
    )
    _update_progress(
        job_store,
        job.id,
        0,
        100,
        "Generating image - 0%",
        stage_id="generate-image",
    )
    provider_payload["_progress_callback"] = _generation_progress(job_store, job.id)
    try:
        result = generate_fn(provider_payload)
    except Exception as exc:
        raise RetryableJobError("image_generation_failed", str(exc) or "Image generation failed") from exc

    if not bool(getattr(result, "ok", False)):
        raise RetryableJobError(
            "image_generation_failed",
            str(getattr(result, "error", "") or "Image generation failed"),
            details={"provider": getattr(result, "provider", ""), "status": getattr(result, "status", "")},
        )

    _update_progress(
        job_store,
        job.id,
        100,
        100,
        "Storing image asset",
        stage_id="generate-image",
        stage_status=JobStatus.COMPLETED,
    )
    _update_progress(
        job_store,
        job.id,
        100,
        100,
        "Storing image asset",
        stage_id="store-asset",
    )
    try:
        require_execution_authority(job_store, job.id)
        asset, output_ref = _store_image_asset(
            job,
            request,
            result,
            asset_store or default_asset_store(),
        )
    except FileNotFoundError as exc:
        raise RetryableJobError("image_output_missing", str(exc)) from exc
    except JobClaimConflict:
        raise
    except Exception as exc:
        message = str(exc) or "Image asset could not be stored"
        code = (
            "avatar_frame_quality_rejected"
            if message.startswith("avatar_frame_quality_rejected:")
            else "image_asset_store_failed"
        )
        raise RetryableJobError(code, message) from exc

    completed = job_store.complete_job(
        job.id,
        CompleteJobRequest(
            output_refs=[output_ref.model_dump(mode="json")],
            logs=[
                {
                    "level": "info",
                    "message": "Image generated and stored",
                    "asset_id": asset.id,
                }
            ],
        ),
    )
    finisher = optional(CHARACTER_AVATAR_FINISHER)
    if finisher is not None:
        finisher.completed(job)
    return completed or job


def _shared_output_path(result: Any) -> str:
    """Verified local copy of an output the image service put in the shared bucket."""
    blob_key = str(getattr(result, "blob_key", "") or "").strip()
    checksum = str(getattr(result, "checksum_sha256", "") or "").strip()
    if not blob_key or not checksum:
        return ""
    from app.assets.content import AssetContentUnavailable, materialize_asset

    try:
        return str(materialize_asset(SimpleNamespace(id=blob_key, storage_key=blob_key, checksum_sha256=checksum)))
    except AssetContentUnavailable:
        return ""


def _store_image_asset(
    job: JobRecord,
    request: ImageGenerateInput,
    result: Any,
    store: AssetStore,
) -> tuple[AssetRecord, ImageOutputRef]:
    storage_path = str(getattr(result, "local_path", "") or "").strip()
    if not storage_path or not Path(storage_path).is_file():
        storage_path = _shared_output_path(result)
    if not storage_path:
        raise FileNotFoundError(
            "Image provider did not produce a readable local file"
        )

    title = image_title_from_prompt(request.prompt)
    provider_key = str(getattr(result, "provider", "") or request.provider_key())
    width = int(getattr(result, "width", 0) or request.width)
    height = int(getattr(result, "height", 0) or request.height)
    mime_type = str(getattr(result, "mime_type", "") or "image/png")
    seed = getattr(result, "seed", request.seed)
    metadata = dict(getattr(result, "metadata", {}) or {})
    request_metadata = dict(request.metadata or {})
    stabilization_metadata = _stabilize_character_avatar_frame(
        job,
        request,
        storage_path,
        request_metadata,
        store,
    )
    is_rpg_world_image = bool(
        str(request_metadata.get("world_id") or "").strip()
        and str(request_metadata.get("target_id") or "").strip()
    )
    asset_id = f"image:image-generation-{job.id.removeprefix('job:')}"

    asset_module = (
        "rpg-world-authoring"
        if is_rpg_world_image
        else job.module if job.module == "character-avatar" else "image-generation"
    )
    asset = store.upsert_asset(
        AssetRecord(
            id=asset_id,
            module=asset_module,
            type=AssetType.IMAGE,
            mime_type=mime_type,
            storage_path=storage_path,
            source_job_id=job.id,
            parent_asset_ids=list(request.reference_asset_ids),
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
                "source_module": job.module,
                "rpg_world_image": is_rpg_world_image,
                "rpg_world_id": str(request_metadata.get("world_id") or ""),
                "rpg_world_target_id": str(
                    request_metadata.get("target_id") or ""
                ),
                **stabilization_metadata,
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


def _stabilize_character_avatar_frame(
    job: JobRecord,
    request: ImageGenerateInput,
    storage_path: str,
    request_metadata: dict[str, Any],
    store: AssetStore,
) -> dict[str, Any]:
    finisher = optional(CHARACTER_AVATAR_FINISHER)
    if finisher is None:
        return {}
    value = finisher.stabilize(job, request, storage_path, request_metadata, store)
    return value if isinstance(value, dict) else {}


def _update_progress(
    job_store: Any,
    job_id: str,
    current: int,
    total: int,
    message: str,
    *,
    stage_id: str,
    stage_status: JobStatus = JobStatus.RUNNING,
) -> None:
    update_progress = getattr(job_store, "update_progress", None)
    if callable(update_progress):
        update_progress(
            job_id,
            current=current,
            total=total,
            message=message,
            stage_id=stage_id,
            stage_status=stage_status,
        )


def _generation_progress(job_store: Any, job_id: str) -> Callable[[int, int, str], None]:
    """Turn provider steps into job progress: up to 94 % while generating, 95 % at the end."""
    last_percent = -1

    def report(current: int, total: int, message: str = "Generating image") -> None:
        nonlocal last_percent
        generation_percent = max(0, min(100, round((current / max(1, total)) * 100)))
        percent = (
            95
            if generation_percent >= 100
            else max(0, min(94, round(generation_percent * 0.95)))
        )
        message = str(message or "Generating image").strip() or "Generating image"
        if percent < last_percent or (percent == last_percent and message == "Generating image"):
            return
        last_percent = percent
        if message.lower() == "generating image":
            message = (
                "Finalizing image..."
                if generation_percent >= 100
                else f"Generating image - {percent}%"
            )
        _update_progress(job_store, job_id, percent, 100, message, stage_id="generate-image")

    return report

