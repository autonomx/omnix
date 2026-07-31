"""Global image model lifecycle helpers (IMG-6)."""
from __future__ import annotations

import contextlib
import threading
from typing import Any, Dict

from app.image.config import get_active_image_provider_name, get_provider_config
from app.image.providers.registry import (
    get_image_provider_definition,
    get_image_provider_keys,
    is_supported_image_provider,
)

_PROVIDER_CACHE: Dict[str, Any] = {}
_PROVIDER_LOCK = threading.RLock()
_LIFECYCLE_LOCK = threading.RLock()
_GIB = float(1024**3)


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


def _unload_instances(providers: Dict[str, Any]) -> list[str]:
    unloaded: list[str] = []
    for provider_name, provider in providers.items():
        try:
            if hasattr(provider, "unload"):
                provider.unload()
        except Exception:
            pass
        unloaded.append(provider_name)
    return unloaded


def _pop_cached_providers(*, keep: str = "") -> Dict[str, Any]:
    keep = _safe_str(keep).strip().lower()
    with _PROVIDER_LOCK:
        selected = {
            provider_name: provider
            for provider_name, provider in _PROVIDER_CACHE.items()
            if not keep or provider_name != keep
        }
        for provider_name in selected:
            _PROVIDER_CACHE.pop(provider_name, None)
    return selected


def _validate_load_budget(provider_name: str) -> None:
    definition = get_image_provider_definition(provider_name) or {}
    if bool(definition.get("default_cpu_offload")):
        return
    minimum = definition.get("min_load_free_gib")
    if minimum is None:
        return
    try:
        import torch
    except Exception:
        return
    if not torch.cuda.is_available():
        return
    try:
        free_bytes, total_bytes = torch.cuda.mem_get_info()
    except Exception:
        return
    free_gib = free_bytes / _GIB
    total_gib = total_bytes / _GIB
    required_gib = float(minimum)
    if free_gib < required_gib:
        raise RuntimeError(
            f"{provider_name}_insufficient_vram:"
            f"free_gib={free_gib:.2f} required_gib={required_gib:.2f} "
            f"total_gib={total_gib:.2f}; unload other GPU models before loading"
        )


def get_cached_provider(provider_name: str | None = None):
    provider_name = _safe_str(provider_name).strip().lower() or get_active_image_provider_name()
    with _PROVIDER_LOCK:
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
    if provider_name in {"krea2_turbo", "z_image_turbo"}:
        from app.image.providers.diffusers_turbo_provider import DiffusersTurboImageProvider

        return DiffusersTurboImageProvider(provider_name, config)
    if provider_name == "mock":
        from app.image.providers.mock_provider import MockImageProvider

        return MockImageProvider(config)

    raise RuntimeError(f"unsupported_image_provider:{provider_name}")


def _provider_is_loaded_instance(provider: Any) -> bool:
    checker = getattr(provider, "is_loaded", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return provider is not None


def is_image_provider_loaded(provider_name: str | None = None) -> bool:
    provider_name = _safe_str(provider_name).strip().lower() or get_active_image_provider_name()
    return _provider_is_loaded_instance(get_cached_provider(provider_name))


def load_image_provider(provider_name: str | None = None) -> Dict[str, Any]:
    """Atomically switch to one resident image provider and load it."""

    provider_name = _safe_str(provider_name).strip().lower() or get_active_image_provider_name()
    with _LIFECYCLE_LOCK:
        _unload_instances(_pop_cached_providers(keep=provider_name))
        provider = get_or_create_image_provider(provider_name)
        try:
            _validate_load_budget(provider_name)
            provider.load()
        except Exception:
            with _PROVIDER_LOCK:
                if _PROVIDER_CACHE.get(provider_name) is provider:
                    _PROVIDER_CACHE.pop(provider_name, None)
            with contextlib.suppress(Exception):
                provider.unload()
            raise

        result: Dict[str, Any] = {
            "ok": True,
            "provider": provider_name,
            "loaded": is_image_provider_loaded(provider_name),
        }
        runtime = _provider_runtime_status(provider)
        if runtime:
            result["runtime"] = runtime
        return result


def unload_image_provider(provider_name: str | None = None) -> Dict[str, Any]:
    provider_name = _safe_str(provider_name).strip().lower() or get_active_image_provider_name()

    with _LIFECYCLE_LOCK:
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
    with _LIFECYCLE_LOCK:
        unloaded = _unload_instances(_pop_cached_providers())
    return {"ok": True, "unloaded": unloaded}


def get_image_provider_cache_status() -> Dict[str, Any]:
    with _PROVIDER_LOCK:
        providers = dict(_PROVIDER_CACHE)
    loaded_providers = [
        provider_name
        for provider_name, provider in sorted(providers.items())
        if _provider_is_loaded_instance(provider)
    ]
    runtime = {
        provider_name: status
        for provider_name, provider in sorted(providers.items())
        if (status := _provider_runtime_status(provider))
    }
    result: Dict[str, Any] = {
        "ok": True,
        "loaded_providers": loaded_providers,
        "cached_providers": sorted(list(providers.keys())),
        "known_providers": get_image_provider_keys(),
    }
    if runtime:
        result["runtime"] = runtime
    return result
