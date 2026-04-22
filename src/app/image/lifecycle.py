"""Global image model lifecycle helpers (IMG-6)."""
from __future__ import annotations

from typing import Any, Dict

from app.image.config import get_active_image_provider_name, get_provider_config
from app.image.providers.registry import is_supported_image_provider, get_image_provider_keys

_PROVIDER_CACHE: Dict[str, Any] = {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def get_cached_provider(provider_name: str | None = None):
    provider_name = _safe_str(provider_name).strip() or get_active_image_provider_name()
    return _PROVIDER_CACHE.get(provider_name)


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
    provider = _PROVIDER_CACHE.get(provider_name)
    if provider is None:
        provider = _build_provider(provider_name)
        _PROVIDER_CACHE[provider_name] = provider

    provider.load()
    return {
        "ok": True,
        "provider": provider_name,
        "loaded": True,
    }


def unload_image_provider(provider_name: str | None = None) -> Dict[str, Any]:
    provider_name = _safe_str(provider_name).strip() or get_active_image_provider_name()
    provider = _PROVIDER_CACHE.get(provider_name)
    if provider is not None:
        try:
            provider.unload()
        finally:
            _PROVIDER_CACHE.pop(provider_name, None)
    return {
        "ok": True,
        "provider": provider_name,
        "loaded": False,
    }


def unload_all_image_providers() -> Dict[str, Any]:
    for provider_name in list(_PROVIDER_CACHE.keys()):
        try:
            _PROVIDER_CACHE[provider_name].unload()
        except Exception:
            pass
        _PROVIDER_CACHE.pop(provider_name, None)
    return {"ok": True}


def get_image_provider_cache_status() -> Dict[str, Any]:
    return {
        "ok": True,
        "loaded_providers": sorted(list(_PROVIDER_CACHE.keys())),
        "known_providers": get_image_provider_keys(),
    }
