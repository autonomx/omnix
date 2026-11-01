from __future__ import annotations

import logging

import time
from typing import Any, Dict

from app.settings.access import load_settings

from .base import BaseImageProvider
from .registry import build_visual_provider, resolve_visual_provider_key

logger = logging.getLogger(__name__)

_IMAGE_PROVIDER_CACHE: Dict[str, Any] = {}
MAX_CACHED_IMAGE_PROVIDERS = 1
IMAGE_PROVIDER_CACHE_TTL_SECONDS = 24 * 60 * 60.0
_IMAGE_PROVIDER_CACHE_TOUCHED_AT = 0.0


def _expire_image_provider_cache() -> None:
    if (
        _IMAGE_PROVIDER_CACHE.get("entry") is not None
        and time.monotonic() - _IMAGE_PROVIDER_CACHE_TOUCHED_AT
        > IMAGE_PROVIDER_CACHE_TTL_SECONDS
    ):
        unload_image_provider_cache()


def _store_image_provider(cache_key: str, provider_key: str, instance: BaseImageProvider) -> None:
    global _IMAGE_PROVIDER_CACHE_TOUCHED_AT
    if len(_IMAGE_PROVIDER_CACHE) >= MAX_CACHED_IMAGE_PROVIDERS:
        unload_image_provider_cache()
    _IMAGE_PROVIDER_CACHE["entry"] = (cache_key, instance, provider_key)
    _IMAGE_PROVIDER_CACHE_TOUCHED_AT = time.monotonic()


def __getattr__(name: str) -> Any:
    if name == "FluxKleinImageProvider":
        from .flux_klein_provider import FluxKleinImageProvider

        return FluxKleinImageProvider
    raise AttributeError(name)


def _visual_settings() -> Dict[str, Any]:
    settings = load_settings()
    return dict(settings.get("rpg_visual") or {})


def get_loaded_image_provider() -> BaseImageProvider | None:
    _expire_image_provider_cache()
    entry = _IMAGE_PROVIDER_CACHE.get("entry")
    return entry[1] if entry else None


def get_image_provider_cache_key() -> str:
    _expire_image_provider_cache()
    entry = _IMAGE_PROVIDER_CACHE.get("entry")
    return str(entry[0] or "") if entry else ""


def unload_image_provider_cache() -> None:
    global _IMAGE_PROVIDER_CACHE_TOUCHED_AT
    entry = _IMAGE_PROVIDER_CACHE.get("entry")
    instance = entry[1] if entry else None
    if instance is not None:
        try:
            unload = getattr(instance, "unload", None)
            if callable(unload):
                unload()
        except Exception:
            logger.debug("suppressed error in %s", "unload_image_provider_cache", exc_info=True)
    _IMAGE_PROVIDER_CACHE.clear()
    _IMAGE_PROVIDER_CACHE_TOUCHED_AT = 0.0


def get_image_provider() -> BaseImageProvider:
    """
    Backwards-compatible provider accessor.

    Existing routes still import and call this function. Keep it stable while
    the app migrates toward explicit registry-based construction.
    """
    visual = _visual_settings()
    _expire_image_provider_cache()
    provider_key = resolve_visual_provider_key(visual)
    cache_key = f"{provider_key}:{visual!r}"

    if (
        (entry := _IMAGE_PROVIDER_CACHE.get("entry")) is not None
        and entry[0] == cache_key
        and entry[1] is not None
    ):
        global _IMAGE_PROVIDER_CACHE_TOUCHED_AT
        _IMAGE_PROVIDER_CACHE_TOUCHED_AT = time.monotonic()
        return entry[1]

    unload_image_provider_cache()

    selected_key, instance = build_visual_provider(visual)

    _store_image_provider(cache_key, selected_key, instance)
    return instance


__all__ = [
    "BaseImageProvider",
    "FluxKleinImageProvider",
    "get_loaded_image_provider",
    "get_image_provider_cache_key",
    "unload_image_provider_cache",
    "get_image_provider",
    "build_visual_provider",
    "resolve_visual_provider_key",
]
