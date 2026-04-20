from __future__ import annotations

from typing import Any, Dict, Tuple

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


def get_loaded_image_provider() -> BaseImageProvider | None:
    instance = _IMAGE_PROVIDER_CACHE.get("instance")
    if instance is None:
        return None
    return instance


def get_image_provider_cache_key() -> str:
    return str(_IMAGE_PROVIDER_CACHE.get("key") or "")


def is_loaded_image_provider_ready() -> bool:
    instance = _IMAGE_PROVIDER_CACHE.get("instance")
    if instance is None:
        return False
    is_available = getattr(instance, "is_available", None)
    if callable(is_available):
        return bool(is_available())
    return True


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


def preload_image_provider(force_reload: bool = False) -> BaseImageProvider:
    """
    Force provider materialization so the UI can warm the runtime and VRAM.
    """
    if force_reload:
        unload_image_provider_cache()
    return get_image_provider()


def switch_image_provider_runtime(
    *,
    provider_key: str | None,
    enabled: bool = True,
    provider_config: Dict[str, Any] | None = None,
    force_reload: bool = True,
) -> Tuple[str, BaseImageProvider]:
    """
    Runtime-only hot switch. This does not persist settings by itself.
    """
    cfg: Dict[str, Any] = dict(provider_config or {})
    cfg["enabled"] = bool(enabled)
    if provider_key is not None:
        cfg["visual_provider"] = str(provider_key)

    if force_reload:
        unload_image_provider_cache()

    selected_key, provider = build_visual_provider(cfg)
    _IMAGE_PROVIDER_CACHE["key"] = f"runtime:{selected_key}:{cfg!r}"
    _IMAGE_PROVIDER_CACHE["instance"] = provider
    _IMAGE_PROVIDER_CACHE["provider_key"] = selected_key
    return selected_key, provider


def get_visual_provider_status_payload() -> Dict[str, Any]:
    provider = get_loaded_image_provider()
    loaded_provider = get_loaded_image_provider_name()
    runtime_status: Dict[str, Any] = {}
    if provider is not None:
        runtime = getattr(provider, "runtime_status", None)
        if callable(runtime):
            try:
                runtime_status = dict(runtime() or {})
            except Exception as exc:
                runtime_status = {"ready": False, "error": str(exc)}

    return {
        "loaded": provider is not None,
        "loaded_provider": loaded_provider,
        "cache_key": get_image_provider_cache_key(),
        "ready": is_loaded_image_provider_ready(),
        "runtime_status": runtime_status,
        "options": list_visual_provider_options(),
    }


__all__ = [
    "BaseImageProvider",
    "ImageGenerationResult",
    "DisabledImageProvider",
    "FluxKleinImageProvider",
    "image_generation_enabled",
    "is_image_provider_loaded",
    "get_loaded_image_provider_name",
    "get_loaded_image_provider",
    "get_image_provider_cache_key",
    "is_loaded_image_provider_ready",
    "unload_image_provider_cache",
    "get_image_provider",
    "preload_image_provider",
    "switch_image_provider_runtime",
    "get_visual_provider_status_payload",
    "build_visual_provider",
    "get_visual_provider_runtime_validator",
    "has_visual_provider",
    "list_visual_provider_keys",
    "list_visual_provider_options",
    "resolve_visual_provider_key",
]