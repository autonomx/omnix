"""Adapters from RPG image requests to the global image service."""
from __future__ import annotations

from typing import Any, Dict

from app.image.service import generate_image


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_rpg_kind(kind: str) -> str:
    kind = _safe_str(kind).strip()
    if kind in {"portrait", "character_portrait"}:
        return "character_portrait"
    if kind in {"scene", "scene_illustration", "illustration", "environment"}:
        return "scene_illustration"
    if kind in {"item", "item_illustration"}:
        return "item_illustration"
    return kind or "image"


def _default_dimensions_for_kind(kind: str) -> tuple[int, int]:
    kind = _normalize_rpg_kind(kind)
    if kind == "character_portrait":
        return 768, 1024
    if kind == "scene_illustration":
        return 1344, 768
    if kind == "item_illustration":
        return 1024, 1024
    return 1024, 1024


def generate_rpg_image(payload: Dict[str, Any]):
    payload = _safe_dict(payload)
    kind = _normalize_rpg_kind(_safe_str(payload.get("kind")))
    default_width, default_height = _default_dimensions_for_kind(kind)
    adapted = {
        "provider": payload.get("provider", "flux_klein"),
        "prompt": _safe_str(payload.get("prompt")),
        "negative_prompt": _safe_str(payload.get("negative_prompt")),
        "width": payload.get("width", default_width),
        "height": payload.get("height", default_height),
        "seed": payload.get("seed"),
        "steps": payload.get("num_inference_steps"),
        "guidance_scale": payload.get("guidance_scale"),
        "kind": kind,
        "source": "rpg",
        "style": _safe_str(payload.get("style")),
        "session_id": _safe_str(payload.get("session_id")),
        "request_id": _safe_str(payload.get("request_id")),
        "metadata": {
            **_safe_dict(payload.get("metadata")),
            "target_id": _safe_str(payload.get("target_id")),
            "model": _safe_str(payload.get("model")),
        },
    }
    return generate_image(adapted)


def generate_rpg_scene_image(payload: Dict[str, Any]):
    payload = dict(_safe_dict(payload))
    payload["kind"] = "scene_illustration"
    return generate_rpg_image(payload)


def generate_rpg_portrait_image(payload: Dict[str, Any]):
    payload = dict(_safe_dict(payload))
    payload["kind"] = "character_portrait"
    return generate_rpg_image(payload)
