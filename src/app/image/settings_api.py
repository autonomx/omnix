"""Global image settings helpers."""
from __future__ import annotations

from typing import Any, Dict

from app.shared import load_settings, save_settings
from app.image.lifecycle import unload_all_image_providers


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def get_image_settings_payload() -> Dict[str, Any]:
    settings = load_settings()
    image_cfg = _safe_dict(settings.get("image"))
    return {
        "ok": True,
        "settings": image_cfg,
    }


def update_image_settings_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    settings = load_settings()
    image_cfg = _safe_dict(settings.get("image"))

    if payload.get("enabled") is not None:
        image_cfg["enabled"] = bool(payload.get("enabled"))
    if payload.get("provider") is not None:
        image_cfg["provider"] = _safe_str(payload.get("provider")).strip() or "flux_klein"
    if payload.get("auto_unload_on_disable") is not None:
        image_cfg["auto_unload_on_disable"] = bool(payload.get("auto_unload_on_disable"))

    incoming_chat = _safe_dict(payload.get("chat"))
    if incoming_chat:
        current = _safe_dict(image_cfg.get("chat"))
        current.update(incoming_chat)
        image_cfg["chat"] = current

    incoming_story = _safe_dict(payload.get("story"))
    if incoming_story:
        current = _safe_dict(image_cfg.get("story"))
        current.update(incoming_story)
        image_cfg["story"] = current

    incoming_flux = _safe_dict(payload.get("flux_klein"))
    if incoming_flux:
        current = _safe_dict(image_cfg.get("flux_klein"))
        current.update(incoming_flux)
        image_cfg["flux_klein"] = current

    settings["image"] = image_cfg
    save_settings(settings)

    if not bool(image_cfg.get("enabled", False)) and bool(image_cfg.get("auto_unload_on_disable", True)):
        unload_all_image_providers()

    return {
        "ok": True,
        "settings": image_cfg,
    }
