"""HTTP client for the external image generation service."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def is_image_generation_enabled() -> bool:
    """Return whether image generation is explicitly enabled.

    The lightweight image service can be started without loading model weights.
    ``OMNIX_IMAGE_ENABLED`` controls whether model load and generation actions
    are allowed.
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


def request_image_service(
    method: str,
    path: str,
    payload: Dict[str, Any] | None = None,
    timeout: float = 600.0,
) -> Dict[str, Any]:
    base = _image_service_url()
    if not base:
        raise RuntimeError("image_service_not_configured")

    method = method.strip().upper() or "GET"
    body = None
    headers = {"Accept": "application/json"}
    if method != "GET":
        body = json.dumps(payload or {}).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        f"{base}{path}",
        data=body,
        headers=headers,
        method=method,
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


def post_image_service(path: str, payload: Dict[str, Any] | None = None, timeout: float = 600.0) -> Dict[str, Any]:
    return request_image_service("POST", path, payload, timeout)


def get_image_service_status(provider: str = "") -> Dict[str, Any]:
    provider = str(provider or "").strip().lower()
    query = f"?provider={urllib.parse.quote(provider, safe='')}" if provider else ""
    return request_image_service("GET", f"/provider/status{query}", timeout=5.0)


def get_image_generation_progress(request_id: str) -> Dict[str, Any]:
    encoded = urllib.parse.quote(str(request_id or ""), safe="")
    return request_image_service("GET", f"/generate/progress/{encoded}", timeout=5.0)


def download_image_model_via_service(provider: str = "flux_klein") -> Dict[str, Any]:
    return post_image_service("/provider/download", {"provider": provider}, timeout=7200.0)


def load_image_model_via_service(provider: str = "flux_klein") -> Dict[str, Any]:
    return post_image_service("/provider/load", {"provider": provider}, timeout=900.0)


def unload_image_model_via_service(provider: str = "flux_klein") -> Dict[str, Any]:
    return post_image_service("/provider/unload", {"provider": provider}, timeout=120.0)


def generate_image_via_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not is_image_generation_enabled():
        return image_disabled_response(source="image_http_client")
    return post_image_service("/generate", payload, timeout=900.0)
