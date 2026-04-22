"""Consumer-specific adapters for the global image service."""
from __future__ import annotations

from typing import Any, Dict


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_chat_image_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    return {
        "provider": _safe_str(payload.get("provider")).strip(),
        "prompt": _safe_str(payload.get("prompt")).strip(),
        "negative_prompt": _safe_str(payload.get("negative_prompt")).strip(),
        "width": int(payload.get("width") or 1024),
        "height": int(payload.get("height") or 1024),
        "seed": payload.get("seed"),
        "steps": payload.get("steps"),
        "guidance_scale": payload.get("guidance_scale"),
        "kind": _safe_str(payload.get("kind")).strip() or "image",
        "source": "chat",
        "style": _safe_str(payload.get("style")).strip(),
        "session_id": _safe_str(payload.get("session_id")).strip(),
        "request_id": _safe_str(payload.get("request_id")).strip(),
        "metadata": _safe_dict(payload.get("metadata")),
    }


def build_story_image_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    kind = _safe_str(payload.get("kind")).strip() or "scene"
    width = int(payload.get("width") or (1344 if kind in {"scene", "cover"} else 768))
    height = int(payload.get("height") or (768 if kind in {"scene", "cover"} else 1024))
    return {
        "provider": _safe_str(payload.get("provider")).strip(),
        "prompt": _safe_str(payload.get("prompt")).strip(),
        "negative_prompt": _safe_str(payload.get("negative_prompt")).strip(),
        "width": width,
        "height": height,
        "seed": payload.get("seed"),
        "steps": payload.get("steps"),
        "guidance_scale": payload.get("guidance_scale"),
        "kind": kind,
        "source": "story",
        "style": _safe_str(payload.get("style")).strip() or "story",
        "session_id": _safe_str(payload.get("session_id")).strip(),
        "request_id": _safe_str(payload.get("request_id")).strip(),
        "metadata": _safe_dict(payload.get("metadata")),
    }
