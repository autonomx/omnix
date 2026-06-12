"""HTTP client for the external image generation service."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def is_image_generation_enabled() -> bool:
    """Return whether image generation is explicitly enabled.

    Image generation is opt-in because FLUX/diffusers can consume substantial
    GPU/VRAM when started or called. Set OMNIX_IMAGE_ENABLED=1 to re-enable.
    """

    return _truthy(os.environ.get("OMNIX_IMAGE_ENABLED", "0"))


def _image_service_url() -> str:
    if not is_image_generation_enabled():
        return ""
    return os.environ.get("OMNIX_IMAGE_URL", "").strip().rstrip("/")


def is_image_service_enabled() -> bool:
    return bool(_image_service_url())


def image_disabled_response(source: str = "app") -> Dict[str, Any]:
    return {
        "ok": False,
        "provider": "disabled",
        "status": "disabled",
        "error": "image_generation_disabled",
        "asset_url": "",
        "local_path": "",
        "seed": None,
        "width": 0,
        "height": 0,
        "mime_type": "",
        "metadata": {
            "source": source,
            "disabled_by": "OMNIX_IMAGE_ENABLED",
            "enable_hint": "Set OMNIX_IMAGE_ENABLED=1 to enable image generation.",
        },
    }


def post_image_service(path: str, payload: Dict[str, Any] | None = None, timeout: float = 600.0) -> Dict[str, Any]:
    base = _image_service_url()
    if not base:
        raise RuntimeError("image_service_not_configured")

    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"image_service_http_{exc.code}:{raw}") from exc
    except Exception as exc:
        raise RuntimeError(f"image_service_unreachable:{exc}") from exc


def generate_image_via_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not is_image_generation_enabled():
        return image_disabled_response(source="image_http_client")
    return post_image_service("/generate", payload, timeout=900.0)
