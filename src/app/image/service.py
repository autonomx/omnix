"""Global image generation service."""
from __future__ import annotations
import os

from typing import Any, Dict

from app.image.config import get_active_image_provider_name, get_provider_config
from app.image.lifecycle import get_or_create_image_provider
from app.image_http_client import generate_image_via_service, is_image_service_enabled
from app.image.job_queue import enqueue_image_job
from app.image.models import ImageGenerationRequest, ImageGenerationResponse
from app.image.consumer_adapters import build_chat_image_request, build_story_image_request
from app.image.providers.registry import is_supported_image_provider


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _normalize_request(payload: Dict[str, Any]) -> ImageGenerationRequest:
    payload = payload if isinstance(payload, dict) else {}
    provider = _safe_str(payload.get("provider")).strip() or get_active_image_provider_name()
    if not is_supported_image_provider(provider):
        provider = get_active_image_provider_name()
    return ImageGenerationRequest(
        provider=provider,
        prompt=_safe_str(payload.get("prompt")).strip(),
        negative_prompt=_safe_str(payload.get("negative_prompt")).strip(),
        width=_safe_int(payload.get("width"), 1024),
        height=_safe_int(payload.get("height"), 1024),
        seed=payload.get("seed"),
        steps=payload.get("steps"),
        guidance_scale=payload.get("guidance_scale"),
        kind=_safe_str(payload.get("kind")).strip() or "image",
        source=_safe_str(payload.get("source")).strip() or "app",
        style=_safe_str(payload.get("style")).strip(),
        session_id=_safe_str(payload.get("session_id")).strip(),
        request_id=_safe_str(payload.get("request_id")).strip(),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )



def _map_to_provider_payload(req: ImageGenerationRequest, provider_config: Dict[str, Any]) -> Dict[str, Any]:
    steps = req.steps
    if steps is None:
        steps = _safe_int(provider_config.get("num_inference_steps"), 4)

    guidance_scale = req.guidance_scale
    if guidance_scale is None:
        guidance_scale = _safe_float(provider_config.get("guidance_scale"), 1.0)

    return {
        "prompt": req.prompt,
        "negative_prompt": req.negative_prompt,
        "width": req.width,
        "height": req.height,
        "seed": req.seed,
        "num_inference_steps": steps,
        "guidance_scale": guidance_scale,
        "kind": req.kind,
        "style": req.style,
        "metadata": req.metadata,
    }


def generate_image_local(payload: Dict[str, Any]) -> ImageGenerationResponse:
    req = _normalize_request(payload)
    provider_name = req.provider or get_active_image_provider_name()
    provider_config = get_provider_config(provider_name)
    provider = get_or_create_image_provider(provider_name)

    provider_payload = _map_to_provider_payload(req, provider_config)
    result = provider.generate(provider_payload)

    local_path = _safe_str(getattr(result, "file_path", "")).strip()
    asset_url = _safe_str(getattr(result, "asset_url", "")).strip()
    error = _safe_str(getattr(result, "error", "")).strip()
    status = _safe_str(getattr(result, "status", "")).strip() or ("completed" if getattr(result, "ok", False) else "failed")
    mime_type = _safe_str(getattr(result, "mime_type", "")).strip() or "image/png"
    revised_prompt = _safe_str(getattr(result, "revised_prompt", "")).strip()
    result_metadata = getattr(result, "metadata", None)
    if not isinstance(result_metadata, dict):
        result_metadata = {}

    return ImageGenerationResponse(
        ok=bool(getattr(result, "ok", False)),
        provider=provider_name,
        status=status,
        error=error,
        asset_url=asset_url,
        local_path=local_path,
        seed=req.seed,
        width=req.width,
        height=req.height,
        mime_type=mime_type,
        metadata={
            "source": req.source,
            "kind": req.kind,
            "style": req.style,
            "request_id": req.request_id,
            "session_id": req.session_id,
            "revised_prompt": revised_prompt,
            **result_metadata,
        },
    )


def generate_image(payload: Dict[str, Any]) -> ImageGenerationResponse:
    if is_image_service_enabled() and os.environ.get("OMNIX_IMAGE_SERVICE_MODE") != "1":
        data = generate_image_via_service(payload if isinstance(payload, dict) else {})
        return ImageGenerationResponse(
            ok=bool(data.get("ok")),
            provider=_safe_str(data.get("provider")),
            status=_safe_str(data.get("status")) or ("completed" if data.get("ok") else "failed"),
            error=_safe_str(data.get("error")),
            asset_url=_safe_str(data.get("asset_url")),
            local_path=_safe_str(data.get("local_path")),
            seed=data.get("seed"),
            width=_safe_int(data.get("width"), 0),
            height=_safe_int(data.get("height"), 0),
            mime_type=_safe_str(data.get("mime_type")) or "image/png",
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        )

    return generate_image_local(payload)


def enqueue_chat_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    return enqueue_image_job(build_chat_image_request(payload))


def enqueue_story_image(payload: Dict[str, Any]) -> Dict[str, Any]:
    return enqueue_image_job(build_story_image_request(payload))
