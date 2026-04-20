from __future__ import annotations

from typing import Any, Dict

from app.shared import load_settings

from .base import BaseImageProvider, ImageGenerationResult
from .disabled_provider import DisabledImageProvider
from .flux_klein_provider import FluxKleinImageProvider
from .registry import (
    build_visual_provider,
    get_visual_provider_runtime_validator,
    has_visual_provider,
    list_visual_provider_keys,
    list_visual_provider_options,
    resolve_visual_provider_key,
)

_IMAGE_PROVIDER_CACHE: Dict[str, Any] = {
    "key": None,
    "instance": None,
    "provider_key": None,
}


def _visual_settings() -> Dict[str, Any]:
    settings = load_settings()
    return dict(settings.get("rpg_visual") or {})


def image_generation_enabled() -> bool:
    visual = _visual_settings()
    provider_key = resolve_visual_provider_key(visual)
    return provider_key != "disabled"


def is_image_provider_loaded() -> bool:
    return _IMAGE_PROVIDER_CACHE.get("instance") is not None


def get_loaded_image_provider_name() -> str:
    provider_key = _IMAGE_PROVIDER_CACHE.get("provider_key")
    if provider_key:
        return str(provider_key)
    instance = _IMAGE_PROVIDER_CACHE.get("instance")
    if instance is None:
        return ""
    return str(getattr(instance, "provider_name", "") or "").strip()


def unload_image_provider_cache() -> None:
    instance = _IMAGE_PROVIDER_CACHE.get("instance")
    if instance is not None:
        try:
            unload = getattr(instance, "unload", None)
            if callable(unload):
                unload()
        except Exception:
            pass
    _IMAGE_PROVIDER_CACHE["key"] = None
    _IMAGE_PROVIDER_CACHE["instance"] = None
    _IMAGE_PROVIDER_CACHE["provider_key"] = None


def get_image_provider() -> BaseImageProvider:
    """
    Backwards-compatible provider accessor.

    Existing routes still import and call this function. Keep it stable while
    the app migrates toward explicit registry-based construction.
    """
    visual = _visual_settings()
    provider_key = resolve_visual_provider_key(visual)
    cache_key = f"{provider_key}:{visual!r}"

    if (
        _IMAGE_PROVIDER_CACHE.get("key") == cache_key
        and _IMAGE_PROVIDER_CACHE.get("instance") is not None
    ):
        return _IMAGE_PROVIDER_CACHE["instance"]

    unload_image_provider_cache()

    selected_key, instance = build_visual_provider(visual)

    _IMAGE_PROVIDER_CACHE["key"] = cache_key
    _IMAGE_PROVIDER_CACHE["instance"] = instance
    _IMAGE_PROVIDER_CACHE["provider_key"] = selected_key
    return instance


__all__ = [
    "BaseImageProvider",
    "ImageGenerationResult",
    "DisabledImageProvider",
    "FluxKleinImageProvider",
    "image_generation_enabled",
    "is_image_provider_loaded",
    "get_loaded_image_provider_name",
    "unload_image_provider_cache",
    "get_image_provider",
    "build_visual_provider",
    "get_visual_provider_runtime_validator",
    "has_visual_provider",
    "list_visual_provider_keys",
    "list_visual_provider_options",
    "resolve_visual_provider_key",
]