"""Gateway controls for the external image model service."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.image_http_client import (
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


async def _call_service(function, *args: Any) -> dict[str, Any]:
    try:
        result = await run_in_threadpool(function, *args)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="invalid_image_service_response")
    return result


@router.get("/api/image-generation/model/status", include_in_schema=False)
async def image_model_status() -> dict[str, Any]:
    try:
        return await _call_service(get_image_service_status)
    except HTTPException as exc:
        return {
            "ok": False,
            "service": "image",
            "enabled": is_image_generation_enabled(),
            "provider": "flux_klein",
            "model": "FLUX.2 [klein] 4B",
            "loaded": False,
            "state": "unavailable",
            "error": str(exc.detail or "image_service_unavailable"),
            "explicit_load_required": True,
            "local_model": {"complete": True, "missing": [], "local_dir": ""},
        }


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
