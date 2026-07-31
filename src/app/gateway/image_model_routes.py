"""Gateway controls for the external image model service."""
from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.image.providers.registry import get_image_provider_definition, list_image_providers
from app.image_http_client import (
    download_image_model_via_service,
    get_image_service_status,
    is_image_generation_enabled,
    load_image_model_via_service,
    unload_image_model_via_service,
)

router = APIRouter()


class ImageModelActionRequest(BaseModel):
    provider: str = "flux_klein"


def _provider(value: str | None) -> str:
    return str(value or "flux_klein").strip().lower() or "flux_klein"


def _model_label(provider: str) -> str:
    definition = get_image_provider_definition(provider) or {}
    return str(definition.get("label") or provider or "Image model")


def _read_service_status(provider: str) -> dict[str, Any]:
    """Forward provider selection while preserving zero-argument test doubles."""

    try:
        accepts_provider = bool(inspect.signature(get_image_service_status).parameters)
    except (TypeError, ValueError):
        accepts_provider = True
    return get_image_service_status(provider) if accepts_provider else get_image_service_status()


async def _call_service(function, *args: Any) -> dict[str, Any]:
    try:
        result = await run_in_threadpool(function, *args)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="invalid_image_service_response")
    return result


@router.get("/api/image-generation/model/status", include_in_schema=False)
async def image_model_status(
    provider: str = Query(default="flux_klein"),
) -> dict[str, Any]:
    provider_name = _provider(provider)
    try:
        return await _call_service(_read_service_status, provider_name)
    except HTTPException as exc:
        return {
            "ok": False,
            "service": "image",
            "enabled": is_image_generation_enabled(),
            "provider": provider_name,
            "model": _model_label(provider_name),
            "loaded": False,
            "state": "unavailable",
            "error": str(exc.detail or "image_service_unavailable"),
            "explicit_load_required": True,
            "local_model": {"complete": False, "missing": [], "local_dir": ""},
            "models": [
                {
                    **definition,
                    "provider": definition.get("key"),
                    "model": definition.get("label"),
                    "loaded": False,
                    "state": "unavailable",
                    "local_model": {"complete": False, "missing": [], "local_dir": ""},
                }
                for definition in list_image_providers()
                if definition.get("supports_local_model")
            ],
        }


@router.post("/api/image-generation/model/download", include_in_schema=False)
async def download_image_model(request: ImageModelActionRequest) -> dict[str, Any]:
    result = await _call_service(download_image_model_via_service, _provider(request.provider))
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error") or "image_model_download_failed")
    return result


@router.post("/api/image-generation/model/load", include_in_schema=False)
async def load_image_model(request: ImageModelActionRequest) -> dict[str, Any]:
    result = await _call_service(load_image_model_via_service, _provider(request.provider))
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error") or "image_model_load_failed")
    return result


@router.post("/api/image-generation/model/unload", include_in_schema=False)
async def unload_image_model(request: ImageModelActionRequest) -> dict[str, Any]:
    result = await _call_service(unload_image_model_via_service, _provider(request.provider))
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error") or "image_model_unload_failed")
    return result
