"""Global image configuration helpers."""
from __future__ import annotations

from typing import Any, Dict

from app.shared import load_settings
from app.image.providers.registry import is_supported_image_provider


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def get_image_settings() -> Dict[str, Any]:
    settings = load_settings()
    image_cfg = _safe_dict(settings.get("image"))
    if image_cfg:
        return image_cfg

    # Migration fallback to RPG visual config until everything is moved.
    rpg_visual = _safe_dict(settings.get("rpg_visual"))
    if rpg_visual:
        return rpg_visual

    return {}


def get_active_image_provider_name() -> str:
    image_cfg = get_image_settings()
    provider = _safe_str(image_cfg.get("provider")).strip()
    if not provider:
        return "flux_klein"
    if is_supported_image_provider(provider):
        return provider
    return "flux_klein"


def get_provider_config(provider_name: str) -> Dict[str, Any]:
    image_cfg = get_image_settings()
    provider_name = _safe_str(provider_name).strip() or get_active_image_provider_name()

    if provider_name == "flux_klein":
        return _safe_dict(image_cfg.get("flux_klein"))
    if provider_name == "mock":
        return _safe_dict(image_cfg.get("mock"))

    return {}
