"""Background execution and shared asset persistence for image jobs."""
from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import ValidationError

from app.assets import AssetRecord, AssetType, SharedAssetStore, default_asset_store
from app.jobs.models import JobStatus
from app.runtime.hooks import invoke_runtime_hook

from app.jobs.inline_execution_compat import require_execution_authority
from app.jobs.models import (
    CompleteJobRequest,
    CreateJobRequest,
    FailJobRequest,
    JobRecord,
    JobStage,
    ResourceClass,
)

from app.image.job_contracts import (
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
        compat={
            "legacy_system": "src/app/image/job_queue.py",
            "legacy_queue_bypassed": True,
        },
    )
    if idempotency_key is None:
        return store.create_job(request)
    create_once = getattr(store, "create_job_once", None)
    if not callable(create_once):
        raise TypeError("image job store must support idempotent submission")
    return create_once(request, idempotency_key=idempotency_key)


def execute_image_job(
    job_store: Any,
    job: JobRecord,
    *,
    generate_fn: Callable[[dict[str, Any]], Any] | None = None,
    asset_store: SharedAssetStore | None = None,
) -> JobRecord:
    """Run one image job, index its file, and complete the shared job."""

    job_store.mark_running(job.id)
    _update_progress(
        job_store,
        job.id,
        1,
        4,
        "Preparing image request",
        stage_id="generate-image",
    )
    try:
        request = ImageGenerateInput.model_validate(job.input_payload or {})
        provider_payload = request.provider_payload()
        provider_payload["request_id"] = job.id
    except ValidationError as exc:
        return _fail(
            job_store,
            job,
            "image_invalid_request",
            str(exc),
            retryable=False,
        )
    except ValueError as exc:
        return _fail(
            job_store,
            job,
            "image_provider_unavailable",
            str(exc),
            retryable=False,
        )

    if generate_fn is None:
        from app.image.service import generate_image

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
    progress_poller = _start_image_generation_progress_poll(job_store, job.id)
    try:
        result = generate_fn(provider_payload)
    except Exception as exc:
        return _fail(
            job_store,
            job,
            "image_generation_failed",
            str(exc) or "Image generation failed",
            retryable=True,
        )
    finally:
        if progress_poller is not None:
            progress_poller()

    if not bool(getattr(result, "ok", False)):
        message = str(getattr(result, "error", "") or "Image generation failed")
        return _fail(
            job_store,
            job,
            "image_generation_failed",
            message,
            retryable=True,
            details={
                "provider": getattr(result, "provider", ""),
                "status": getattr(result, "status", ""),
            },
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
        return _fail(
            job_store,
            job,
            "image_output_missing",
            str(exc),
            retryable=True,
        )
    except Exception as exc:
        message = str(exc) or "Image asset could not be stored"
        code = (
            "avatar_frame_quality_rejected"
            if message.startswith("avatar_frame_quality_rejected:")
            else "image_asset_store_failed"
        )
        return _fail(job_store, job, code, message, retryable=True)

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
    invoke_runtime_hook("image.character_avatar.completed", job)
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
    store: SharedAssetStore,
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
    store: SharedAssetStore,
) -> dict[str, Any]:
    value = invoke_runtime_hook(
        "image.character_avatar.stabilize",
        job,
        request,
        storage_path,
        request_metadata,
        store,
        default={},
    )
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


def _start_image_generation_progress_poll(
    job_store: Any,
    job_id: str,
) -> Callable[[], None] | None:
    try:
        from app.image_http_client import (
            get_image_generation_progress,
            is_image_service_enabled,
        )
    except ImportError:
        return None

    if not is_image_service_enabled():
        return None

    stop = threading.Event()
    last_percent = -1

    def poll_once() -> None:
        nonlocal last_percent
        try:
            data = get_image_generation_progress(job_id)
        except RuntimeError:
            return
        if not bool(data.get("ok")):
            return
        total = int(data.get("total") or 1)
        current = int(data.get("current") or 0)
        generation_percent = max(
            0,
            min(100, round((current / max(1, total)) * 100)),
        )
        percent = (
            95
            if generation_percent >= 100
            else max(0, min(94, round(generation_percent * 0.95)))
        )
        if percent < last_percent:
            return
        if (
            percent == last_percent
            and str(data.get("message") or "").strip() == "Generating image"
        ):
            return
        last_percent = percent
        message = (
            str(data.get("message") or "Generating image").strip()
            or "Generating image"
        )
        if message.lower() == "generating image":
            message = (
                "Finalizing image..."
                if generation_percent >= 100
                else f"Generating image - {percent}%"
            )
        _update_progress(
            job_store,
            job_id,
            percent,
            100,
            message,
            stage_id="generate-image",
        )
        if generation_percent >= 100:
            stop.set()

    def poll_loop() -> None:
        while not stop.wait(0.5):
            poll_once()

    thread = threading.Thread(
        target=poll_loop,
        name=f"omnix-image-progress-{job_id.removeprefix('job:')[:8]}",
        daemon=True,
    )
    thread.start()

    def stop_polling() -> None:
        poll_once()
        stop.set()
        thread.join(timeout=1.5)

    return stop_polling


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
            details={
                "job_type": job.type,
                "module": job.module,
                **(details or {}),
            },
        ),
    )
    return failed or job
