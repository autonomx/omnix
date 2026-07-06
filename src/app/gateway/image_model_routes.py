"""Gateway-owned controls for the external image model service."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from starlette.concurrency import run_in_threadpool

from app.image_http_client import (
    get_image_service_status,
    load_image_model_via_service,
    unload_image_model_via_service,
)

router = APIRouter()


def _provider(payload: dict[str, Any] | None) -> str:
    value = (payload or {}).get("provider")
    return str(value or "flux_klein").strip().lower() or "flux_klein"


async def _call_service(function, *args):
    try:
        result = await run_in_threadpool(function, *args)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="invalid_image_service_response")
    return result


@router.get("/api/image-generation/model/status", include_in_schema=False)
async def image_model_status() -> dict[str, Any]:
    return await _call_service(get_image_service_status)


@router.post("/api/image-generation/model/load", include_in_schema=False)
async def load_image_model(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    result = await _call_service(load_image_model_via_service, _provider(payload))
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error") or "image_model_load_failed")
    return result


@router.post("/api/image-generation/model/unload", include_in_schema=False)
async def unload_image_model(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    result = await _call_service(unload_image_model_via_service, _provider(payload))
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error") or "image_model_unload_failed")
    return result
