"""Gateway controls for the external image model service."""
from __future__ import annotations

import inspect
import os
import threading
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
    start_image_service_via_launcher,
    unload_image_model_via_service,
)

router = APIRouter()

_DOWNLOAD_TOTALS_LOCK = threading.Lock()
_DOWNLOAD_TOTALS: dict[str, int] = {}


class ImageModelActionRequest(BaseModel):
    provider: str = "flux_klein"


def _provider(value: str | None) -> str:
    return str(value or "flux_klein").strip().lower() or "flux_klein"


def _model_definition(provider: str) -> dict[str, Any]:
    return get_image_provider_definition(provider) or {}


def _model_label(provider: str) -> str:
    definition = _model_definition(provider)
    return str(definition.get("label") or provider or "Image model")


def _read_service_status(provider: str) -> dict[str, Any]:
    """Forward provider selection while preserving zero-argument test doubles."""

    try:
        accepts_provider = bool(inspect.signature(get_image_service_status).parameters)
    except (TypeError, ValueError):
        accepts_provider = True
    return get_image_service_status(provider) if accepts_provider else get_image_service_status()


def _repository_total_bytes(provider: str) -> int:
    with _DOWNLOAD_TOTALS_LOCK:
        cached = _DOWNLOAD_TOTALS.get(provider)
    if cached is not None:
        return cached

    definition = _model_definition(provider)
    repo_id = str(definition.get("repo_id") or "").strip()
    if not repo_id:
        return 0
    try:
        from huggingface_hub import HfApi

        info = HfApi().repo_info(
            repo_id=repo_id,
            files_metadata=True,
            token=os.environ.get("HF_TOKEN", "").strip() or None,
        )
        total = sum(
            max(0, int(getattr(sibling, "size", 0) or 0))
            for sibling in (getattr(info, "siblings", None) or [])
        )
    except Exception:
        total = 0

    with _DOWNLOAD_TOTALS_LOCK:
        _DOWNLOAD_TOTALS[provider] = total
    return total


def _downloaded_bytes(local_dir: str) -> int:
    local_dir = str(local_dir or "").strip()
    if not local_dir or not os.path.isdir(local_dir):
        return 0

    total = 0
    for root, _dirs, files in os.walk(local_dir):
        normalized_root = root.replace("\\", "/")
        in_download_cache = "/.cache/huggingface/download" in normalized_root
        for name in files:
            if in_download_cache and not name.endswith(".incomplete"):
                continue
            path = os.path.join(root, name)
            try:
                total += max(0, os.path.getsize(path))
            except OSError:
                continue
    return total


def _download_progress(provider: str, model: dict[str, Any]) -> dict[str, Any]:
    local_model = model.get("local_model")
    local_model = local_model if isinstance(local_model, dict) else {}
    current = _downloaded_bytes(str(local_model.get("local_dir") or ""))
    total = _repository_total_bytes(provider)
    percent = round(min(100.0, (current / total) * 100.0), 1) if total > 0 else None
    return {
        "status": "downloading",
        "bytes_downloaded": current,
        "bytes_total": total,
        "percent": percent,
        "indeterminate": total <= 0,
    }


def _attach_download_progress(payload: dict[str, Any], provider: str) -> dict[str, Any]:
    if payload.get("state") == "downloading" and payload.get("provider") == provider:
        payload["download_progress"] = _download_progress(provider, payload)

    models = payload.get("models")
    if isinstance(models, list):
        for model in models:
            if not isinstance(model, dict):
                continue
            model_provider = _provider(str(model.get("provider") or model.get("key") or ""))
            if model.get("state") == "downloading":
                model["download_progress"] = _download_progress(model_provider, model)
    return payload


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
        result = await _call_service(_read_service_status, provider_name)
        return await run_in_threadpool(_attach_download_progress, result, provider_name)
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


@router.post("/api/image-generation/service/start", include_in_schema=False)
async def start_image_service(request: ImageModelActionRequest) -> dict[str, Any]:
    result = await _call_service(start_image_service_via_launcher, _provider(request.provider))
    if not result.get("ok"):
        raise HTTPException(
            status_code=503,
            detail=result.get("error") or "image_service_start_failed",
        )
    return result


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
