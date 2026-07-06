"""Global image model lifecycle helpers (IMG-6)."""
from __future__ import annotations

import threading
from typing import Any, Dict

from app.image.config import get_active_image_provider_name, get_provider_config
from app.image.providers.registry import (
    get_image_provider_keys,
    is_supported_image_provider,
)

_PROVIDER_CACHE: Dict[str, Any] = {}
_PROVIDER_LOCK = threading.Lock()


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _provider_runtime_status(provider: Any) -> Dict[str, Any]:
    reader = getattr(provider, "runtime_status", None)
    if not callable(reader):
        return {}
    try:
        status = reader()
        return status if isinstance(status, dict) else {}
    except Exception:
        return {}


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


def is_image_provider_loaded(provider_name: str | None = None) -> bool:
    provider_name = _safe_str(provider_name).strip().lower() or get_active_image_provider_name()
    provider = get_cached_provider(provider_name)
    if provider is None:
        return False
    checker = getattr(provider, "is_loaded", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return True


def load_image_provider(provider_name: str | None = None) -> Dict[str, Any]:
    provider_name = _safe_str(provider_name).strip() or get_active_image_provider_name()
    provider = get_or_create_image_provider(provider_name)
    provider.load()
    return {
        "ok": True,
        "provider": provider_name,
        "loaded": is_image_provider_loaded(provider_name),
        "runtime": _provider_runtime_status(provider),
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
        "loaded": False,
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
    loaded_providers = [
        provider_name
        for provider_name in sorted(_PROVIDER_CACHE.keys())
        if is_image_provider_loaded(provider_name)
    ]
    runtime = {
        provider_name: _provider_runtime_status(provider)
        for provider_name, provider in sorted(_PROVIDER_CACHE.items())
    }
    return {
        "ok": True,
        "loaded_providers": loaded_providers,
        "cached_providers": sorted(list(_PROVIDER_CACHE.keys())),
        "known_providers": get_image_provider_keys(),
        "runtime": runtime,
    }
