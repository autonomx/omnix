"""HTTP client for the external image generation service."""
from __future__ import annotations

import json
import os
import time
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
    configured = os.environ.get("OMNIX_IMAGE_URL", "").strip()
    return (configured or "http://127.0.0.1:5301").rstrip("/")


def _launcher_control_url() -> str:
    configured = os.environ.get("OMNIX_LAUNCHER_URL", "").strip()
    return (configured or "http://127.0.0.1:5055").rstrip("/")


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


def _request_json(
    method: str,
    url: str,
    payload: Dict[str, Any] | None = None,
    timeout: float = 600.0,
) -> Dict[str, Any]:
    method = method.strip().upper() or "GET"
    body = None
    headers = {"Accept": "application/json"}
    if method != "GET":
        body = json.dumps(payload or {}).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http_{exc.code}:{raw}") from exc
    except Exception as exc:
        raise RuntimeError(f"unreachable:{exc}") from exc


def request_image_service(
    method: str,
    path: str,
    payload: Dict[str, Any] | None = None,
    timeout: float = 600.0,
) -> Dict[str, Any]:
    base = _image_service_url()
    if not base:
        raise RuntimeError("image_service_not_configured")

    try:
        return _request_json(method, f"{base}{path}", payload, timeout)
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("http_"):
            raise RuntimeError(f"image_service_{message}") from exc
        raise RuntimeError(f"image_service_{message}") from exc


def post_image_service(path: str, payload: Dict[str, Any] | None = None, timeout: float = 600.0) -> Dict[str, Any]:
    return request_image_service("POST", path, payload, timeout)


def get_image_service_status(provider: str = "") -> Dict[str, Any]:
    provider = str(provider or "").strip().lower()
    query = f"?provider={urllib.parse.quote(provider, safe='')}" if provider else ""
    return request_image_service("GET", f"/provider/status{query}", timeout=5.0)


def start_image_service_via_launcher(
    provider: str = "flux_klein",
    *,
    startup_timeout: float = 30.0,
) -> Dict[str, Any]:
    """Start the lightweight image service and wait until its status endpoint responds.

    Starting the service does not download a model or load weights into memory.
    The launcher remains the process owner so service logs and stop/restart actions
    continue to work from the launcher dashboard.
    """

    if not is_image_generation_enabled():
        return {
            "ok": False,
            "provider": provider,
            "loaded": False,
            "state": "disabled",
            "error": "image_generation_disabled",
        }

    launcher_url = _launcher_control_url()
    if not launcher_url:
        return {
            "ok": False,
            "provider": provider,
            "loaded": False,
            "state": "unavailable",
            "error": "launcher_not_configured",
        }

    try:
        launcher_result = _request_json(
            "POST",
            f"{launcher_url}/api/services/image/start",
            {},
            timeout=10.0,
        )
    except RuntimeError as exc:
        return {
            "ok": False,
            "provider": provider,
            "loaded": False,
            "state": "unavailable",
            "error": f"launcher_{exc}",
        }

    if not launcher_result.get("ok"):
        return {
            "ok": False,
            "provider": provider,
            "loaded": False,
            "state": "unavailable",
            "error": launcher_result.get("error") or "image_service_start_failed",
            "launcher": launcher_result,
        }

    deadline = time.monotonic() + max(1.0, float(startup_timeout))
    last_error = "image_service_unreachable"
    while time.monotonic() < deadline:
        try:
            status = get_image_service_status(provider)
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(0.25)
            continue
        status = dict(status)
        status["started"] = True
        status["launcher"] = launcher_result
        return status

    return {
        "ok": False,
        "provider": provider,
        "loaded": False,
        "state": "unavailable",
        "error": f"image_service_start_timeout:{last_error}",
        "launcher": launcher_result,
    }


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
