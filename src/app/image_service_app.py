"""Standalone image service.

Run this in the rpg-flux environment:

    python -m uvicorn app.image_service_app:app --host 127.0.0.1 --port 5301
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request

os.environ["OMNIX_IMAGE_SERVICE_MODE"] = "1"

from app.image.lifecycle import load_image_provider, unload_image_provider, unload_all_image_providers
from app.image.runtime_status import validate_global_image_runtime
from app.image.service import generate_image_local


app = FastAPI(title="Omnix Image Service")


@app.on_event("startup")
async def startup_load_provider():
    provider = os.environ.get("OMNIX_IMAGE_PROVIDER", "").strip() or None
    try:
        print("[IMAGE SERVICE] Preloading image provider...")
        result = load_image_provider(provider)
        print("[IMAGE SERVICE] Image provider preload complete:", result)
    except Exception as exc:
        print("[IMAGE SERVICE] Image provider preload failed:", repr(exc))

    if os.environ.get("OMNIX_IMAGE_WARMUP", "1").strip().lower() not in {"1", "true", "yes", "on"}:
        return

    try:
        print("[IMAGE SERVICE] Running tiny FLUX warmup...")
        warmup = generate_image_local({
            "prompt": "tiny warmup image, simple fantasy torch flame, no text",
            "negative_prompt": "text, watermark, logo",
            "width": 256,
            "height": 256,
            "steps": 1,
            "num_inference_steps": 1,
            "seed": 1,
            "warmup": True,
            "no_cache": True,
        })
        print("[IMAGE SERVICE] Warmup complete:", {"ok": warmup.ok, "error": warmup.error})
    except Exception as exc:
        print("[IMAGE SERVICE] Warmup failed:", repr(exc))


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "image",
        "provider_mode": os.environ.get("OMNIX_IMAGE_SERVICE_MODE", ""),
        "runtime": validate_global_image_runtime(),
    }


@app.post("/generate")
async def generate(request: Request):
    payload = await request.json()
    result = generate_image_local(payload if isinstance(payload, dict) else {})
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


@app.post("/provider/load")
async def provider_load(request: Request):
    payload = await request.json()
    provider = payload.get("provider") if isinstance(payload, dict) else None
    return load_image_provider(provider)


@app.post("/provider/unload")
async def provider_unload(request: Request):
    payload = await request.json()
    provider = payload.get("provider") if isinstance(payload, dict) else None
    return unload_image_provider(provider)


@app.post("/provider/unload_all")
async def provider_unload_all():
    return unload_all_image_providers()
