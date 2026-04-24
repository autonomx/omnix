"""Global image model lifecycle helpers (IMG-6)."""
from __future__ import annotations

import threading
from typing import Any, Dict

from app.image.config import get_active_image_provider_name, get_provider_config
from app.image.providers.registry import is_supported_image_provider, get_image_provider_keys

_PROVIDER_CACHE: Dict[str, Any] = {}
_PROVIDER_LOCK = threading.Lock()


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def get_cached_provider(provider_name: str | None = None):
    provider_name = _safe_str(provider_name).strip() or get_active_image_provider_name()
    return _PROVIDER_CACHE.get(provider_name)


def get_or_create_image_provider(provider_name: str | None = None):
    provider_name = _safe_str(provider_name).strip().lower() or "flux_klein"

    with _PROVIDER_LOCK:
        provider = _PROVIDER_CACHE.get(provider_name)
        if provider is None:
            provider = _build_provider(provider_name)
            _PROVIDER_CACHE[provider_name] = provider
        return provider


def _build_provider(provider_name: str):
    provider_name = _safe_str(provider_name).strip().lower() or "flux_klein"
    if not is_supported_image_provider(provider_name):
        raise RuntimeError(f"unsupported_image_provider:{provider_name}")
    config = get_provider_config(provider_name)

    if provider_name == "flux_klein":
        from app.image.providers.flux_klein_provider import FluxKleinImageProvider
        return FluxKleinImageProvider(config)
    if provider_name == "mock":
        from app.image.providers.mock_provider import MockImageProvider
        return MockImageProvider(config)

    raise RuntimeError(f"unsupported_image_provider:{provider_name}")


def load_image_provider(provider_name: str | None = None) -> Dict[str, Any]:
    provider_name = _safe_str(provider_name).strip() or get_active_image_provider_name()
    provider = get_or_create_image_provider(provider_name)
    provider.load()
    return {
        "ok": True,
        "provider": provider_name,
        "loaded": True,
    }


def unload_image_provider(provider_name: str | None = None) -> Dict[str, Any]:
    provider_name = _safe_str(provider_name).strip() or get_active_image_provider_name()
    provider_name = _safe_str(provider_name).strip().lower() or "flux_klein"

    with _PROVIDER_LOCK:
        provider = _PROVIDER_CACHE.pop(provider_name, None)

    if provider is not None and hasattr(provider, "unload"):
        provider.unload()

    return {
        "ok": True,
        "provider": provider_name,
        "unloaded": provider is not None,
    }


def unload_all_image_providers() -> Dict[str, Any]:
    with _PROVIDER_LOCK:
        providers = dict(_PROVIDER_CACHE)
        _PROVIDER_CACHE.clear()

    unloaded = []
    for provider_name, provider in providers.items():
        try:
            if hasattr(provider, "unload"):
                provider.unload()
        except Exception:
            pass
        unloaded.append(provider_name)

    return {"ok": True, "unloaded": unloaded}


def get_image_provider_cache_status() -> Dict[str, Any]:
    return {
        "ok": True,
        "loaded_providers": sorted(list(_PROVIDER_CACHE.keys())),
        "known_providers": get_image_provider_keys(),
    }
