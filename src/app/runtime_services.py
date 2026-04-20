from __future__ import annotations

import os
from typing import Any, Dict

import requests

from app.rpg.visual.runtime_status import validate_flux_klein_runtime


def _normalize_base_url(value: str | None, default: str) -> str:
    raw = (value or default).strip().strip('"').strip("'")
    raw = raw.replace(" ", "")
    return raw.rstrip("/")


def _service_status_payload(
    *,
    name: str,
    ok: bool,
    status: str,
    details: Dict[str, Any] | None = None,
    error: str = "",
) -> Dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "status": status,
        "details": dict(details or {}),
        "error": error,
    }


def get_flux_runtime_status() -> Dict[str, Any]:
    result = validate_flux_klein_runtime()
    return _service_status_payload(
        name="flux",
        ok=bool(result.get("ready")),
        status=result.get("status", "unknown"),
        details=result.get("details", {}),
        error=result.get("error", ""),
    )


def _probe_http_service(name: str, url: str, timeout: float = 4.0) -> Dict[str, Any]:
    try:
        response = requests.get(url.rstrip("/") + "/health", timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return _service_status_payload(
            name=name,
            ok=bool(data.get("ok", True)),
            status=data.get("status", "ready" if data.get("ok", True) else "not_ready"),
            details=data.get("details", data),
            error=data.get("error", ""),
        )
    except Exception as exc:
        return _service_status_payload(
            name=name,
            ok=False,
            status="unreachable",
            details={"url": url},
            error=str(exc),
        )


def get_tts_runtime_status() -> Dict[str, Any]:
    url = _normalize_base_url(
        os.environ.get("OMNIX_TTS_URL"),
        "http://127.0.0.1:5101",
    )
    return _probe_http_service("tts", url)


def get_stt_runtime_status() -> Dict[str, Any]:
    url = _normalize_base_url(
        os.environ.get("OMNIX_STT_URL"),
        "http://127.0.0.1:5201",
    )
    return _probe_http_service("stt", url)


def get_runtime_status_bundle() -> Dict[str, Any]:
    flux = get_flux_runtime_status()
    tts = get_tts_runtime_status()
    stt = get_stt_runtime_status()
    overall_ok = bool(flux.get("ok")) and bool(tts.get("ok")) and bool(stt.get("ok"))
    return {
        "ok": overall_ok,
        "services": {
            "flux": flux,
            "tts": tts,
            "stt": stt,
        },
    }