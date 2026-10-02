"""Standalone image service runtime with explicit multi-model lifecycle."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path

from app.config.env import environment

import os
import threading
from time import monotonic
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from app.security.model_service import ModelServiceMiddleware

environment()["OMNIX_IMAGE_SERVICE_MODE"] = "1"

from app.image.config import get_active_image_provider_name, is_image_generation_enabled
from app.image.downloads import download_image_model, get_image_local_model_status
from app.image.lifecycle import (
    get_image_provider_cache_status,
    is_image_provider_loaded,
    load_image_provider,
    unload_all_image_providers,
    unload_image_provider,
)
from app.image.providers.registry import get_image_provider_definition, list_image_providers
from app.image.service import generate_image_local

from pydantic import BaseModel as _TypedRequestBaseModel, ConfigDict as _TypedRequestConfigDict, Field as _typed_field
from typing import Any as _TypedRequestAny

class _TypedRequestModel(_TypedRequestBaseModel):
    model_config = _TypedRequestConfigDict(extra="allow", populate_by_name=True)

class ProviderDownloadRequestBody(_TypedRequestModel):
    hf_token: _TypedRequestAny = None
    provider: _TypedRequestAny = None

class GenerateRequestBody(_TypedRequestModel):
    num_inference_steps: _TypedRequestAny = None
    provider: _TypedRequestAny = None
    steps: _TypedRequestAny = None

class ProviderLoadRequestBody(_TypedRequestModel):
    provider: _TypedRequestAny = None

class ProviderUnloadRequestBody(_TypedRequestModel):
    provider: _TypedRequestAny = None


app = FastAPI(title="Omnix Image Service")
app.add_middleware(ModelServiceMiddleware)

_MODEL_OPERATION_LOCK = threading.Lock()
_MODEL_OPERATION_TTL_SECONDS = 3600.0
_MODEL_OPERATION: tuple[str, str, float] = ("idle", "", monotonic())
_NDJSON = "application/x-ndjson"
_LOG = logging.getLogger(__name__)


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _provider_name(value: Any) -> str:
    return str(value or "").strip().lower() or "flux_klein"


def _set_model_operation(kind: str, provider: str = "") -> None:
    global _MODEL_OPERATION
    with _MODEL_OPERATION_LOCK:
        _MODEL_OPERATION = (
            str(kind or "idle"),
            _provider_name(provider) if provider else "",
            monotonic(),
        )


def _get_model_operation() -> Dict[str, str]:
    with _MODEL_OPERATION_LOCK:
        now = monotonic()
        kind, provider, updated_at = _MODEL_OPERATION
        if now - updated_at > _MODEL_OPERATION_TTL_SECONDS:
            kind, provider = "idle", ""
        return {
            "kind": kind,
            "provider": provider,
        }


def _model_definition(provider: str) -> Dict[str, Any]:
    return get_image_provider_definition(provider) or {
        "key": provider,
        "label": provider or "Image provider",
        "supports_local_model": False,
        "supports_download": False,
    }


def _model_label(provider: str) -> str:
    return str(_model_definition(provider).get("label") or provider or "Image provider")


def _local_model_status(provider: str) -> Dict[str, Any]:
    definition = _model_definition(provider)
    if not definition.get("supports_local_model"):
        return {"ok": True, "exists": True, "complete": True, "missing": [], "local_dir": ""}
    return get_image_local_model_status(provider)


def _model_status_entry(provider: str, operation: Dict[str, str] | None = None) -> Dict[str, Any]:
    provider = _provider_name(provider)
    definition = _model_definition(provider)
    loaded = is_image_provider_loaded(provider)
    operation = operation or _get_model_operation()
    state = (
        operation.get("kind", "idle")
        if operation.get("kind") != "idle" and operation.get("provider") == provider
        else ("loaded" if loaded else "unloaded")
    )
    local_status = _local_model_status(provider)
    return {
        **definition,
        "provider": provider,
        "model": _model_label(provider),
        "loaded": loaded,
        "state": state,
        "local_model": local_status,
        "downloaded": bool(local_status.get("complete", True)),
    }


def image_model_status(provider: str | None = None) -> Dict[str, Any]:
    provider_name = _provider_name(provider or get_active_image_provider_name())
    operation = _get_model_operation()
    selected = _model_status_entry(provider_name, operation)
    enabled = is_image_generation_enabled()
    models = [
        _model_status_entry(str(definition.get("key") or ""), operation)
        for definition in list_image_providers()
        if definition.get("supports_local_model")
    ]
    return {
        "ok": bool(enabled and selected["local_model"].get("complete", True)),
        "service": "image",
        "enabled": enabled,
        "provider": provider_name,
        "model": selected["model"],
        "loaded": selected["loaded"],
        "state": selected["state"],
        "local_model": selected["local_model"],
        "downloaded": selected["downloaded"],
        "supports_download": bool(selected.get("supports_download")),
        "supports_image_to_image": bool(selected.get("supports_image_to_image")),
        "gated": bool(selected.get("gated")),
        "license": selected.get("license", ""),
        "repo_id": selected.get("repo_id", ""),
        "minimum_diffusers": selected.get("minimum_diffusers", ""),
        "minimum_torch": selected.get("minimum_torch", ""),
        "models": models,
        "cache": get_image_provider_cache_status(),
        "explicit_load_required": _truthy(environment().get("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "1")),
    }


def _publish_shared_output(local_path: str) -> dict[str, str]:
    """Copy the output to the shared bucket when blobs are remote (S3).

    Gateways on other hosts then read it from the bucket instead of this
    service's disk. Local blob storage keeps the single-host file handoff.
    """
    from app.persistence.blob_store import blob_backend, default_blob_store

    path = Path(local_path) if local_path else None
    if blob_backend() != "s3" or path is None or not path.is_file():
        return {}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    checksum = digest.hexdigest()
    record = default_blob_store().put_file(f"image-outputs/{checksum[:2]}/{checksum}{path.suffix or '.png'}", path)
    return {"blob_key": record["storage_key"], "checksum_sha256": record["checksum_sha256"]}


def _generation_response(result) -> Dict[str, Any]:
    return {
        "ok": result.ok,
        "provider": result.provider,
        "status": result.status,
        "error": result.error,
        "asset_url": result.asset_url,
        "local_path": result.local_path,
        **(_publish_shared_output(result.local_path) if result.ok else {}),
        "seed": result.seed,
        "width": result.width,
        "height": result.height,
        "mime_type": result.mime_type,
        "metadata": result.metadata,
    }


def configure_device_permits() -> None:
    """Coordinate this process's GPU use with the other Omnix processes.

    Image model residency and generation slots are granted by the shared
    PostgreSQL permit service, as in the gateway and the TTS server. A
    service started without a database runs uncoordinated, for local tools.
    """
    from app.config.runtime import DevicePermitSettings
    from app.persistence.config import DatabaseConfigurationError
    from app.persistence.database import default_database
    from app.persistence.device_permits import configure_default_device_permit_service

    try:
        database = default_database()
    except DatabaseConfigurationError:
        _LOG.warning("image service has no database; device permits are not coordinated")
        return
    permit_config = DevicePermitSettings.from_environment(environment())
    configure_default_device_permit_service(
        database,
        device_id=permit_config.device_id,
        capacities={
            model_class: (capacity, reserved)
            for model_class, capacity, reserved in permit_config.capacities
        },
        lease_seconds=permit_config.lease_seconds,
        tts_model_owner=permit_config.tts_model_owner,
    )


@app.on_event("startup")
async def startup_load_provider():
    if not is_image_generation_enabled():
        _LOG.info("[IMAGE SERVICE] Image generation disabled; models remain unloaded.")
        return

    if not _truthy(environment().get("OMNIX_IMAGE_PRELOAD", "0")):
        _LOG.info("[IMAGE SERVICE] Ready for on-demand loading; image models are not resident.")
        return

    provider = environment().get("OMNIX_IMAGE_PROVIDER", "").strip() or None
    try:
        _LOG.info("[IMAGE SERVICE] Preloading image provider...")
        result = await run_in_threadpool(load_image_provider, provider)
        _LOG.info('[IMAGE SERVICE] Image provider preload complete: %s', result)
    except Exception as exc:
        _LOG.warning('[IMAGE SERVICE] Image provider preload failed: %s', repr(exc))

    if not _truthy(environment().get("OMNIX_IMAGE_WARMUP", "0")):
        return

    try:
        _LOG.info("[IMAGE SERVICE] Running tiny image-model warmup...")
        warmup = await run_in_threadpool(
            generate_image_local,
            {
                "provider": provider or get_active_image_provider_name(),
                "prompt": "tiny warmup image, simple fantasy torch flame, no text",
                "negative_prompt": "text, watermark, logo",
                "width": 256,
                "height": 256,
                "steps": 1,
                "num_inference_steps": 1,
                "seed": 1,
                "warmup": True,
                "no_cache": True,
            },
        )
        _LOG.info('[IMAGE SERVICE] Warmup complete: %s', {"ok": warmup.ok, "error": warmup.error})
    except Exception as exc:
        _LOG.warning('[IMAGE SERVICE] Warmup failed: %s', repr(exc))


@app.get("/health")
def health():
    model = image_model_status()
    return {
        "ok": True,
        "status": "ready",
        "service": "image",
        "enabled": is_image_generation_enabled(),
        "provider_mode": environment().get("OMNIX_IMAGE_SERVICE_MODE", ""),
        "model": model,
        "details": {"model": model},
    }


@app.get("/provider/status")
def provider_status(provider: str = ""):
    return image_model_status(provider or None)


@app.post("/provider/download")
async def provider_download(request: Request, request_body: ProviderDownloadRequestBody):
    if not is_image_generation_enabled():
        raise HTTPException(status_code=503, detail="model_unavailable")
    payload = request_body.model_dump(exclude_unset=True, by_alias=True)
    payload = payload if isinstance(payload, dict) else {}
    provider = _provider_name(payload.get("provider"))
    hf_token = str(payload.get("hf_token") or "").strip()
    _set_model_operation("downloading", provider)
    try:
        if hf_token:
            result = await run_in_threadpool(download_image_model, provider, hf_token)
        else:
            result = await run_in_threadpool(download_image_model, provider)
        if result.get("ok") is False:
            raise HTTPException(status_code=500, detail="model_service_error")
        return {**result, "loaded": is_image_provider_loaded(provider), "status": image_model_status(provider)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="model_service_error") from exc
    finally:
        hf_token = ""
        _set_model_operation("idle")


@app.post("/generate")
async def generate(request: Request, request_body: GenerateRequestBody):
    """Generate one image.

    With ``Accept: application/x-ndjson`` the response streams one JSON line
    per provider step (``{"event": "progress", ...}``) and ends with
    ``{"event": "result", ...}`` or ``{"event": "error", ...}``; otherwise it
    is the result alone.
    """
    payload = request_body.model_dump(exclude_unset=True, by_alias=True)
    payload = payload if isinstance(payload, dict) else {}
    provider = _provider_name(payload.get("provider") or get_active_image_provider_name())
    definition = _model_definition(provider)
    explicit_load = _truthy(environment().get("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "1"))
    if explicit_load and definition.get("supports_local_model") and not is_image_provider_loaded(provider):
        raise HTTPException(status_code=503, detail="model_unavailable")
    if _NDJSON in request.headers.get("accept", ""):
        return StreamingResponse(_generation_events(payload), media_type=_NDJSON)
    result = await run_in_threadpool(generate_image_local, payload)
    if not result.ok:
        raise HTTPException(status_code=500, detail="model_service_error")
    return await run_in_threadpool(_generation_response, result)


async def _generation_events(payload: Dict[str, Any]) -> AsyncIterator[bytes]:
    loop = asyncio.get_running_loop()
    events: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    def report_progress(current: int, total: int, message: str = "Generating image") -> None:
        # Called on the generation thread; hand the step to the event loop.
        loop.call_soon_threadsafe(events.put_nowait, {
            "event": "progress", "current": int(current), "total": max(1, int(total)),
            "message": str(message),
        })

    payload["_progress_callback"] = report_progress
    generation = asyncio.ensure_future(run_in_threadpool(generate_image_local, payload))
    while not generation.done() or not events.empty():
        step = asyncio.ensure_future(events.get())
        await asyncio.wait({step, generation}, return_when=asyncio.FIRST_COMPLETED)
        if step.done():
            yield _ndjson_line(step.result())
        else:
            step.cancel()
    try:
        result = generation.result()
    except Exception:
        yield _ndjson_line({"event": "error", "error": "model_service_error"})
        return
    if not result.ok:
        yield _ndjson_line({"event": "error", "error": "model_service_error"})
        return
    response = await run_in_threadpool(_generation_response, result)
    yield _ndjson_line({"event": "result", **response})


def _ndjson_line(event: Dict[str, Any]) -> bytes:
    return (json.dumps(event, default=str) + "\n").encode("utf-8")


@app.post("/provider/load")
async def provider_load(request: Request, request_body: ProviderLoadRequestBody):
    if not is_image_generation_enabled():
        raise HTTPException(status_code=503, detail="model_unavailable")
    payload = request_body.model_dump(exclude_unset=True, by_alias=True)
    provider = _provider_name(payload.get("provider") if isinstance(payload, dict) else None)
    _set_model_operation("loading", provider)
    try:
        local_status = _local_model_status(provider)
        if not local_status.get("complete", True):
            raise HTTPException(status_code=503, detail="model_unavailable")
        if not is_image_provider_loaded(provider):
            await run_in_threadpool(unload_all_image_providers)
            result = await run_in_threadpool(load_image_provider, provider)
        else:
            result = {"ok": True, "provider": provider, "loaded": True, "already_loaded": True}
        if result.get("ok") is False:
            raise HTTPException(status_code=500, detail="model_service_error")
        return {**result, "status": image_model_status(provider)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="model_service_error") from exc
    finally:
        _set_model_operation("idle")


@app.post("/provider/unload")
async def provider_unload(request: Request, request_body: ProviderUnloadRequestBody):
    payload = request_body.model_dump(exclude_unset=True, by_alias=True)
    provider = _provider_name(payload.get("provider") if isinstance(payload, dict) else None)
    _set_model_operation("unloading", provider)
    try:
        result = await run_in_threadpool(unload_image_provider, provider)
        if result.get("ok") is False:
            raise HTTPException(status_code=500, detail="model_service_error")
        return {**result, "status": image_model_status(provider)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="model_service_error") from exc
    finally:
        _set_model_operation("idle")


@app.post("/provider/unload_all")
async def provider_unload_all():
    _set_model_operation("unloading")
    try:
        return await run_in_threadpool(unload_all_image_providers)
    finally:
        _set_model_operation("idle")
