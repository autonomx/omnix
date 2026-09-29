"""Global image API routes."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.image.asset_store import cleanup_unused_image_assets, get_image_asset_manifest
from app.image.config import get_active_image_provider_name
from app.image.downloads import download_flux_klein_model, get_flux_local_model_status
from app.image.job_queue import enqueue_image_job, list_image_jobs
from app.image.lifecycle import (
    get_image_provider_cache_status,
    load_image_provider,
    unload_all_image_providers,
    unload_image_provider,
)
from app.image.providers.registry import list_image_providers
from app.image.queue_runner import run_one_image_job
from app.image.runtime_status import (
    validate_global_flux_klein_runtime,
    validate_global_image_runtime,
)
from app.image.service import enqueue_chat_image, enqueue_story_image, generate_image
from app.image.settings_api import (
    get_image_settings_payload,
    update_image_settings_payload,
)
from app.settings.access import load_settings

from pydantic import BaseModel as _TypedRequestBaseModel, ConfigDict as _TypedRequestConfigDict, Field as _typed_field
from typing import Any as _TypedRequestAny

class _TypedRequestModel(_TypedRequestBaseModel):
    model_config = _TypedRequestConfigDict(extra="allow", populate_by_name=True)

class ImageGenerateRouteRequestBody(_TypedRequestModel):
    provider: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    width: int | None = _typed_field(default=None, ge=1, le=8192)
    height: int | None = _typed_field(default=None, ge=1, le=8192)
    seed: int | None = None
    steps: int | None = _typed_field(default=None, ge=1, le=200)
    guidance_scale: float | None = _typed_field(default=None, ge=0, le=50)
    kind: str | None = None
    source: str | None = None
    style: str | None = None
    reference_asset_ids: list[str] | None = None
    session_id: str | None = None
    request_id: str | None = None
    metadata: dict[str, _TypedRequestAny] | None = None

class EnqueueImageRequestBody(_TypedRequestModel):
    provider: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    width: int | None = _typed_field(default=None, ge=1, le=8192)
    height: int | None = _typed_field(default=None, ge=1, le=8192)
    seed: int | None = None
    steps: int | None = _typed_field(default=None, ge=1, le=200)
    guidance_scale: float | None = _typed_field(default=None, ge=0, le=50)
    kind: str | None = None
    source: str | None = None
    style: str | None = None
    reference_asset_ids: list[str] | None = None
    session_id: str | None = None
    request_id: str | None = None
    metadata: dict[str, _TypedRequestAny] | None = None

class EnqueueChatRequestBody(_TypedRequestModel):
    prompt: str | None = None
    negative_prompt: str | None = None
    provider: str | None = None
    width: int | None = _typed_field(default=None, ge=1, le=8192)
    height: int | None = _typed_field(default=None, ge=1, le=8192)
    seed: int | None = None
    steps: int | None = _typed_field(default=None, ge=1, le=200)
    guidance_scale: float | None = _typed_field(default=None, ge=0, le=50)
    kind: str | None = None
    style: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    metadata: dict[str, _TypedRequestAny] | None = None

class EnqueueStoryRequestBody(_TypedRequestModel):
    prompt: str | None = None
    negative_prompt: str | None = None
    provider: str | None = None
    width: int | None = _typed_field(default=None, ge=1, le=8192)
    height: int | None = _typed_field(default=None, ge=1, le=8192)
    seed: int | None = None
    steps: int | None = _typed_field(default=None, ge=1, le=200)
    guidance_scale: float | None = _typed_field(default=None, ge=0, le=50)
    kind: str | None = None
    style: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    metadata: dict[str, _TypedRequestAny] | None = None

class ImageSettingsPostRouteRequestBody(_TypedRequestModel):
    enabled: bool | None = None
    provider: str | None = None
    auto_unload_on_disable: bool | None = None
    chat: dict[str, _TypedRequestAny] | None = None
    story: dict[str, _TypedRequestAny] | None = None

class ImageProviderLoadRouteRequestBody(_TypedRequestModel):
    provider: _TypedRequestAny = None

class ImageProviderUnloadRouteRequestBody(_TypedRequestModel):
    provider: _TypedRequestAny = None


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
def image_generate_route(request: Request, request_body: ImageGenerateRouteRequestBody):
    payload = request_body.model_dump(exclude_unset=True, by_alias=True)
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
async def enqueue_image(payload: EnqueueImageRequestBody):
    payload = payload.model_dump(exclude_unset=True, by_alias=True)
    return enqueue_image_job(payload)


@router.post("/api/image/chat/enqueue")
async def enqueue_chat(payload: EnqueueChatRequestBody):
    payload = payload.model_dump(exclude_unset=True, by_alias=True)
    return enqueue_chat_image(payload)


@router.post("/api/image/story/enqueue")
async def enqueue_story(payload: EnqueueStoryRequestBody):
    payload = payload.model_dump(exclude_unset=True, by_alias=True)
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
def image_settings_post_route(request: Request, request_body: ImageSettingsPostRouteRequestBody):
    payload = request_body.model_dump(exclude_unset=True, by_alias=True)
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
def image_provider_load_route(request: Request, request_body: ImageProviderLoadRouteRequestBody):
    payload = request_body.model_dump(exclude_unset=True, by_alias=True)
    provider = ""
    if isinstance(payload, dict):
        provider = str(payload.get("provider") or "").strip()
    return load_image_provider(provider or None)


@router.post("/api/image/provider/unload")
def image_provider_unload_route(request: Request, request_body: ImageProviderUnloadRouteRequestBody):
    payload = request_body.model_dump(exclude_unset=True, by_alias=True)
    provider = ""
    if isinstance(payload, dict):
        provider = str(payload.get("provider") or "").strip()
    return unload_image_provider(provider or None)


@router.post("/api/image/provider/unload_all")
async def image_provider_unload_all_route():
    return unload_all_image_providers()
