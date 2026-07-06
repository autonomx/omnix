"""Standalone image service.

The service process is intentionally lightweight at startup. FLUX.2 [klein] 4B
is loaded only through ``POST /provider/load`` and released through
``POST /provider/unload``.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool

os.environ["OMNIX_IMAGE_SERVICE_MODE"] = "1"

from app.image.config import get_active_image_provider_name, is_image_generation_enabled
from app.image.downloads import get_flux_local_model_status, resolve_flux_local_dir_from_settings
from app.image.lifecycle import (
    get_image_provider_cache_status,
    is_image_provider_loaded,
    load_image_provider,
    unload_all_image_providers,
    unload_image_provider,
)
from app.image.service import generate_image_local
from app.shared import load_settings

app = FastAPI(title="Omnix Image Service")

_MODEL_OPERATION_LOCK = threading.Lock()
_MODEL_OPERATION = "idle"


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _set_model_operation(value: str) -> None:
    global _MODEL_OPERATION
    with _MODEL_OPERATION_LOCK:
        _MODEL_OPERATION = value


def _get_model_operation() -> str:
    with _MODEL_OPERATION_LOCK:
        return _MODEL_OPERATION


def _model_label(provider: str) -> str:
    if provider == "flux_klein":
        return "FLUX.2 [klein] 4B"
    if provider == "mock":
        return "Mock image provider"
    return provider or "Image provider"


def _local_model_status(provider: str) -> Dict[str, Any]:
    if provider != "flux_klein":
        return {"ok": True, "exists": True, "complete": True, "missing": [], "local_dir": ""}
    settings = load_settings()
    local_dir = resolve_flux_local_dir_from_settings(settings)
    return get_flux_local_model_status(local_dir)


def image_model_status(provider: str | None = None) -> Dict[str, Any]:
    provider_name = (provider or get_active_image_provider_name()).strip().lower() or "flux_klein"
    loaded = is_image_provider_loaded(provider_name)
    operation = _get_model_operation()
    state = operation if operation != "idle" else ("loaded" if loaded else "unloaded")
    local_status = _local_model_status(provider_name)
    enabled = is_image_generation_enabled()
    return {
        "ok": bool(enabled and local_status.get("complete", True)),
        "service": "image",
        "enabled": enabled,
        "provider": provider_name,
        "model": _model_label(provider_name),
        "loaded": loaded,
        "state": state,
        "local_model": local_status,
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


@app.on_event("startup")
async def startup_load_provider():
    if not is_image_generation_enabled():
        print("[IMAGE SERVICE] Image generation disabled; model remains unloaded.")
        return

    if not _truthy(os.environ.get("OMNIX_IMAGE_PRELOAD", "0")):
        print("[IMAGE SERVICE] Ready for on-demand loading; FLUX model is not resident.")
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
        print("[IMAGE SERVICE] Running tiny FLUX warmup...")
        warmup = await run_in_threadpool(
            generate_image_local,
            {
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
async def provider_status():
    return image_model_status()


@app.post("/generate")
async def generate(request: Request):
    payload = await request.json()
    payload = payload if isinstance(payload, dict) else {}
    provider = str(payload.get("provider") or get_active_image_provider_name()).strip().lower() or "flux_klein"
    explicit_load = _truthy(os.environ.get("OMNIX_IMAGE_REQUIRE_EXPLICIT_LOAD", "1"))
    if explicit_load and provider == "flux_klein" and not is_image_provider_loaded(provider):
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
    result = await run_in_threadpool(generate_image_local, payload)
    return _generation_response(result)


@app.post("/provider/load")
async def provider_load(request: Request):
    if not is_image_generation_enabled():
        return {"ok": False, "provider": "disabled", "loaded": False, "error": "image_generation_disabled"}
    payload = await request.json()
    provider = payload.get("provider") if isinstance(payload, dict) else None
    _set_model_operation("loading")
    try:
        result = await run_in_threadpool(load_image_provider, provider)
        return {**result, "status": image_model_status(provider)}
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider or get_active_image_provider_name(),
            "loaded": False,
            "error": str(exc) or repr(exc),
            "status": image_model_status(provider),
        }
    finally:
        _set_model_operation("idle")


@app.post("/provider/unload")
async def provider_unload(request: Request):
    payload = await request.json()
    provider = payload.get("provider") if isinstance(payload, dict) else None
    _set_model_operation("unloading")
    try:
        result = await run_in_threadpool(unload_image_provider, provider)
        return {**result, "status": image_model_status(provider)}
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider or get_active_image_provider_name(),
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
