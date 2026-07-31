"""Standalone image service runtime with explicit multi-model lifecycle."""
from __future__ import annotations

import os
import threading
from typing import Any, Dict

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool

os.environ["OMNIX_IMAGE_SERVICE_MODE"] = "1"

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

app = FastAPI(title="Omnix Image Service")

_MODEL_OPERATION_LOCK = threading.Lock()
_MODEL_OPERATION: Dict[str, str] = {"kind": "idle", "provider": ""}
_GENERATION_PROGRESS_LOCK = threading.Lock()
_GENERATION_PROGRESS: Dict[str, Dict[str, Any]] = {}


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _provider_name(value: Any) -> str:
    return str(value or "").strip().lower() or "flux_klein"


def _set_model_operation(kind: str, provider: str = "") -> None:
    with _MODEL_OPERATION_LOCK:
        _MODEL_OPERATION["kind"] = str(kind or "idle")
        _MODEL_OPERATION["provider"] = _provider_name(provider) if provider else ""


def _get_model_operation() -> Dict[str, str]:
    with _MODEL_OPERATION_LOCK:
        return dict(_MODEL_OPERATION)


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
        "explicit_load_required": _truthy(os.environ.get("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "1")),
    }


def _generation_response(result) -> Dict[str, Any]:
    return {
        "ok": result.ok,
        "provider": result.provider,
        "status": result.status,
        "error": result.error,
        "asset_url": result.asset_url,
        "local_path": result.local_path,
        "seed": result.seed,
        "width": result.width,
        "height": result.height,
        "mime_type": result.mime_type,
        "metadata": result.metadata,
    }


def _request_id(payload: Dict[str, Any]) -> str:
    request_id = str(payload.get("request_id") or "").strip()
    if request_id:
        return request_id
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return str(metadata.get("request_id") or "").strip()
    return ""


def _set_generation_progress(
    request_id: str,
    *,
    current: int,
    total: int,
    message: str,
    status: str,
) -> None:
    request_id = request_id.strip()
    if not request_id:
        return
    total = max(1, int(total or 1))
    current = max(0, min(total, int(current or 0)))
    with _GENERATION_PROGRESS_LOCK:
        _GENERATION_PROGRESS[request_id] = {
            "ok": True,
            "request_id": request_id,
            "current": current,
            "total": total,
            "percent": round((current / total) * 100),
            "message": message,
            "status": status,
        }


def _get_generation_progress(request_id: str) -> Dict[str, Any]:
    request_id = request_id.strip()
    with _GENERATION_PROGRESS_LOCK:
        progress = dict(_GENERATION_PROGRESS.get(request_id) or {})
    if progress:
        return progress
    return {
        "ok": False,
        "request_id": request_id,
        "current": 0,
        "total": 1,
        "percent": 0,
        "message": "No generation progress is available.",
        "status": "missing",
    }


@app.on_event("startup")
async def startup_load_provider():
    if not is_image_generation_enabled():
        print("[IMAGE SERVICE] Image generation disabled; models remain unloaded.")
        return

    if not _truthy(os.environ.get("OMNIX_IMAGE_PRELOAD", "0")):
        print("[IMAGE SERVICE] Ready for on-demand loading; image models are not resident.")
        return

    provider = os.environ.get("OMNIX_IMAGE_PROVIDER", "").strip() or None
    try:
        print("[IMAGE SERVICE] Preloading image provider...")
        result = await run_in_threadpool(load_image_provider, provider)
        print("[IMAGE SERVICE] Image provider preload complete:", result)
    except Exception as exc:
        print("[IMAGE SERVICE] Image provider preload failed:", repr(exc))

    if not _truthy(os.environ.get("OMNIX_IMAGE_WARMUP", "0")):
        return

    try:
        print("[IMAGE SERVICE] Running tiny image-model warmup...")
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
        print("[IMAGE SERVICE] Warmup complete:", {"ok": warmup.ok, "error": warmup.error})
    except Exception as exc:
        print("[IMAGE SERVICE] Warmup failed:", repr(exc))


@app.get("/health")
async def health():
    model = image_model_status()
    return {
        "ok": True,
        "status": "ready",
        "service": "image",
        "enabled": is_image_generation_enabled(),
        "provider_mode": os.environ.get("OMNIX_IMAGE_SERVICE_MODE", ""),
        "model": model,
        "details": {"model": model},
    }


@app.get("/provider/status")
async def provider_status(provider: str = ""):
    return image_model_status(provider or None)


@app.post("/provider/download")
async def provider_download(request: Request):
    if not is_image_generation_enabled():
        return {"ok": False, "provider": "disabled", "loaded": False, "error": "image_generation_disabled"}
    payload = await request.json()
    provider = _provider_name(payload.get("provider") if isinstance(payload, dict) else None)
    _set_model_operation("downloading", provider)
    try:
        result = await run_in_threadpool(download_image_model, provider)
        return {**result, "loaded": is_image_provider_loaded(provider), "status": image_model_status(provider)}
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "loaded": is_image_provider_loaded(provider),
            "error": str(exc) or repr(exc),
            "status": image_model_status(provider),
        }
    finally:
        _set_model_operation("idle")


@app.post("/generate")
async def generate(request: Request):
    payload = await request.json()
    payload = payload if isinstance(payload, dict) else {}
    request_id = _request_id(payload)
    provider = _provider_name(payload.get("provider") or get_active_image_provider_name())
    definition = _model_definition(provider)
    explicit_load = _truthy(os.environ.get("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "1"))
    if explicit_load and definition.get("supports_local_model") and not is_image_provider_loaded(provider):
        _set_generation_progress(
            request_id,
            current=0,
            total=1,
            message="Image model is not loaded.",
            status="failed",
        )
        return {
            "ok": False,
            "provider": provider,
            "status": "model_unloaded",
            "error": "image_model_not_loaded",
            "asset_url": "",
            "local_path": "",
            "seed": payload.get("seed"),
            "width": int(payload.get("width") or 0),
            "height": int(payload.get("height") or 0),
            "mime_type": "",
            "metadata": {"model": _model_label(provider), "load_endpoint": "/provider/load"},
        }

    def report_progress(current: int, total: int, message: str = "Generating image") -> None:
        _set_generation_progress(
            request_id,
            current=current,
            total=total,
            message=message,
            status="running",
        )

    if request_id:
        payload["_progress_callback"] = report_progress
        _set_generation_progress(
            request_id,
            current=0,
            total=int(payload.get("steps") or payload.get("num_inference_steps") or 1),
            message="Generating image",
            status="running",
        )
    result = await run_in_threadpool(generate_image_local, payload)
    _set_generation_progress(
        request_id,
        current=1,
        total=1,
        message="Generation complete" if result.ok else (result.error or "Image generation failed"),
        status="completed" if result.ok else "failed",
    )
    return _generation_response(result)


@app.get("/generate/progress/{request_id}")
async def generate_progress(request_id: str):
    return _get_generation_progress(request_id)


@app.post("/provider/load")
async def provider_load(request: Request):
    if not is_image_generation_enabled():
        return {"ok": False, "provider": "disabled", "loaded": False, "error": "image_generation_disabled"}
    payload = await request.json()
    provider = _provider_name(payload.get("provider") if isinstance(payload, dict) else None)
    _set_model_operation("loading", provider)
    try:
        local_status = _local_model_status(provider)
        if not local_status.get("complete", True):
            missing = ",".join(local_status.get("missing") or [])
            return {
                "ok": False,
                "provider": provider,
                "loaded": False,
                "error": f"image_model_not_downloaded:{provider} missing={missing}",
                "status": image_model_status(provider),
            }
        if not is_image_provider_loaded(provider):
            await run_in_threadpool(unload_all_image_providers)
            result = await run_in_threadpool(load_image_provider, provider)
        else:
            result = {"ok": True, "provider": provider, "loaded": True, "already_loaded": True}
        return {**result, "status": image_model_status(provider)}
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "loaded": False,
            "error": str(exc) or repr(exc),
            "status": image_model_status(provider),
        }
    finally:
        _set_model_operation("idle")


@app.post("/provider/unload")
async def provider_unload(request: Request):
    payload = await request.json()
    provider = _provider_name(payload.get("provider") if isinstance(payload, dict) else None)
    _set_model_operation("unloading", provider)
    try:
        result = await run_in_threadpool(unload_image_provider, provider)
        return {**result, "status": image_model_status(provider)}
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "loaded": is_image_provider_loaded(provider),
            "error": str(exc) or repr(exc),
            "status": image_model_status(provider),
        }
    finally:
        _set_model_operation("idle")


@app.post("/provider/unload_all")
async def provider_unload_all():
    _set_model_operation("unloading")
    try:
        return await run_in_threadpool(unload_all_image_providers)
    finally:
        _set_model_operation("idle")
