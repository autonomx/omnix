"""Phase 12.10 / 12.12 — Visual provider registry."""
from __future__ import annotations

from typing import Any, Dict

from app.shared import load_settings
from .base import BaseImageProvider
from .comfy_provider import ComfyImageProvider
from .flux_klein_provider import FluxKleinImageProvider
from .mock_provider import MockImageProvider
from .openai_provider import OpenAIImageProvider

_IMAGE_PROVIDER_CACHE: Dict[str, Any] = {
    "key": None,
    "instance": None,
}


def _visual_settings() -> Dict[str, Any]:
    settings = load_settings()
    return dict(settings.get("rpg_visual") or {})


def image_generation_enabled() -> bool:
    visual = _visual_settings()
    return bool(visual.get("enabled", False))


def is_image_provider_loaded() -> bool:
    return _IMAGE_PROVIDER_CACHE.get("instance") is not None


def get_loaded_image_provider_name() -> str:
    instance = _IMAGE_PROVIDER_CACHE.get("instance")
    if instance is None:
        return ""
    return str(getattr(instance, "provider_name", "") or "").strip()


def unload_image_provider_cache() -> None:
    instance = _IMAGE_PROVIDER_CACHE.get("instance")
    if instance is not None:
        try:
            instance.unload()
        except Exception:
            pass
    _IMAGE_PROVIDER_CACHE["key"] = None
    _IMAGE_PROVIDER_CACHE["instance"] = None


def get_image_provider() -> BaseImageProvider:
    """Return the configured image provider."""
    visual = _visual_settings()
    provider = str(visual.get("provider") or "mock").strip().lower()
    enabled = bool(visual.get("enabled", False))
    cache_key = f"{enabled}:{provider}:{visual}"

    if _IMAGE_PROVIDER_CACHE.get("key") == cache_key and _IMAGE_PROVIDER_CACHE.get("instance") is not None:
        return _IMAGE_PROVIDER_CACHE["instance"]

    unload_image_provider_cache()

    if not enabled:
        instance = MockImageProvider()
    elif provider == "comfy":
        instance = ComfyImageProvider()
    elif provider == "openai":
        instance = OpenAIImageProvider()
    elif provider == "flux_klein":
        instance = FluxKleinImageProvider(dict(visual.get("flux_klein") or {}))
    else:
        instance = MockImageProvider()

    _IMAGE_PROVIDER_CACHE["key"] = cache_key
    _IMAGE_PROVIDER_CACHE["instance"] = instance
    return instance
