"""Global image API routes."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Request

from app.image.downloads import download_flux_klein_model, get_flux_local_model_status
from app.image.runtime_status import validate_global_flux_klein_runtime, validate_global_image_runtime
from app.image.service import generate_image, enqueue_chat_image, enqueue_story_image
from app.image.job_queue import enqueue_image_job, list_image_jobs
from app.image.queue_runner import run_one_image_job
from app.image.asset_store import get_image_asset_manifest, cleanup_unused_image_assets
from app.image.lifecycle import load_image_provider, unload_image_provider, unload_all_image_providers, get_image_provider_cache_status
from app.image.settings_api import get_image_settings_payload, update_image_settings_payload
from app.image.providers.registry import list_image_providers
from app.image.config import get_active_image_provider_name
from app.shared import load_settings

router = APIRouter()


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


@router.post("/api/image/models/flux-klein/download")
async def download_flux_klein_route():
    result = download_flux_klein_model()
    return result


@router.get("/api/image/models/flux-klein/status")
async def flux_klein_status_route():
    settings = load_settings()
    image_cfg = _safe_dict(settings.get("image"))
    flux = _safe_dict(image_cfg.get("flux_klein"))
    local_dir = flux.get("local_dir", "")
    if not local_dir:
        from app.image.downloads import resolve_flux_local_dir_from_settings
        local_dir = resolve_flux_local_dir_from_settings(settings)
    return {
        "ok": True,
        "provider": "flux_klein",
        "local_dir": local_dir,
        "local_status": get_flux_local_model_status(local_dir),
        "runtime_status": validate_global_flux_klein_runtime(),
    }


@router.post("/api/image/generate")
async def image_generate_route(request: Request):
    payload = await request.json()
    response = generate_image(payload if isinstance(payload, dict) else {})
    return {
        "ok": response.ok,
        "provider": response.provider,
        "status": response.status,
        "error": response.error,
        "asset_url": response.asset_url,
        "local_path": response.local_path,
        "seed": response.seed,
        "width": response.width,
        "height": response.height,
        "mime_type": response.mime_type,
        "metadata": response.metadata,
    }


@router.post("/api/image/jobs/enqueue")
async def enqueue_image(payload: dict):
    return enqueue_image_job(payload)


@router.post("/api/image/chat/enqueue")
async def enqueue_chat(payload: dict):
    return enqueue_chat_image(payload)


@router.post("/api/image/story/enqueue")
async def enqueue_story(payload: dict):
    return enqueue_story_image(payload)


@router.post("/api/image/jobs/run_one")
async def run_one():
    return run_one_image_job()


@router.get("/api/image/jobs")
async def list_jobs():
    return list_image_jobs()


@router.get("/api/image/assets/manifest")
async def asset_manifest():
    return get_image_asset_manifest()


@router.post("/api/image/assets/cleanup")
async def cleanup_assets():
    return cleanup_unused_image_assets()


@router.get("/api/image/settings")
async def image_settings_get_route():
    return get_image_settings_payload()


@router.post("/api/image/settings")
async def image_settings_post_route(request: Request):
    payload = await request.json()
    return update_image_settings_payload(payload if isinstance(payload, dict) else {})


@router.get("/api/image/runtime")
async def image_runtime_route():
    return validate_global_image_runtime()


@router.get("/api/image/providers")
async def image_providers_route():
    return {
        "ok": True,
        "providers": list_image_providers(),
        "cache": get_image_provider_cache_status(),
        "active_provider": get_active_image_provider_name(),
    }


@router.post("/api/image/provider/load")
async def image_provider_load_route(request: Request):
    payload = await request.json()
    provider = ""
    if isinstance(payload, dict):
        provider = str(payload.get("provider") or "").strip()
    return load_image_provider(provider or None)


@router.post("/api/image/provider/unload")
async def image_provider_unload_route(request: Request):
    payload = await request.json()
    provider = ""
    if isinstance(payload, dict):
        provider = str(payload.get("provider") or "").strip()
    return unload_image_provider(provider or None)


@router.post("/api/image/provider/unload_all")
async def image_provider_unload_all_route():
    return unload_all_image_providers()
