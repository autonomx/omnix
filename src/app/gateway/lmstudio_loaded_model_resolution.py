"""Prefer LM Studio's loaded LLM and use the configured model only as fallback.

LM Studio treats a supplied model identifier as a request to use or load that
model. A stale configured model therefore overrides a model that the user just
loaded in the LM Studio UI. Resolve the active loaded instance through the
native model-management API before each chat request, with a very short cache to
avoid duplicate discovery during speculative/final request pairs.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any
from weakref import WeakKeyDictionary

from app.providers.lmstudio_provider import LMStudioProvider

from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_loaded_model_resolution_installed"
_DEFAULT_CACHE_TTL_SECONDS = 0.25
_DEFAULT_DISCOVERY_TIMEOUT_SECONDS = 0.75
_CACHE_LOCK = threading.RLock()


@dataclass(frozen=True)
class _LoadedModel:
    instance_id: str
    model_key: str
    display_name: str

    def matches(self, value: str) -> bool:
        normalized = value.strip().casefold()
        return bool(normalized) and normalized in {
            self.instance_id.casefold(),
            self.model_key.casefold(),
            self.display_name.casefold(),
        }


@dataclass(frozen=True)
class _Discovery:
    available: bool
    endpoint: str | None
    models: tuple[_LoadedModel, ...]


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    discovery: _Discovery


_DISCOVERY_CACHE: WeakKeyDictionary[LMStudioProvider, _CacheEntry] = WeakKeyDictionary()


def _float_setting(name: str, fallback: float, *, minimum: float, maximum: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    try:
        value = float(raw) if raw else fallback
    except ValueError:
        value = fallback
    return min(maximum, max(minimum, value))


def _cache_ttl_seconds() -> float:
    return _float_setting(
        "OMNIX_LMSTUDIO_MODEL_DISCOVERY_CACHE_SECONDS",
        _DEFAULT_CACHE_TTL_SECONDS,
        minimum=0.0,
        maximum=30.0,
    )


def _discovery_timeout_seconds(provider: LMStudioProvider) -> float:
    configured = _float_setting(
        "OMNIX_LMSTUDIO_MODEL_DISCOVERY_TIMEOUT_SECONDS",
        _DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
        minimum=0.05,
        maximum=5.0,
    )
    try:
        provider_timeout = float(provider.config.timeout)
    except (TypeError, ValueError):
        provider_timeout = configured
    return max(0.05, min(configured, provider_timeout))


def _deduplicate(models: list[_LoadedModel]) -> tuple[_LoadedModel, ...]:
    seen: set[str] = set()
    unique: list[_LoadedModel] = []
    for model in models:
        key = model.instance_id.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(model)
    return tuple(unique)


def _parse_v1_models(payload: Any) -> tuple[_LoadedModel, ...] | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        return None
    loaded: list[_LoadedModel] = []
    for model in payload["models"]:
        if not isinstance(model, dict):
            continue
        model_type = str(model.get("type") or "").strip().casefold()
        if model_type == "embedding":
            continue
        model_key = str(model.get("key") or "").strip()
        display_name = str(model.get("display_name") or model_key).strip()
        instances = model.get("loaded_instances")
        if not isinstance(instances, list):
            continue
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            instance_id = str(instance.get("id") or model_key).strip()
            if not instance_id:
                continue
            loaded.append(
                _LoadedModel(
                    instance_id=instance_id,
                    model_key=model_key or instance_id,
                    display_name=display_name or model_key or instance_id,
                )
            )
    return _deduplicate(loaded)


def _parse_v0_models(payload: Any) -> tuple[_LoadedModel, ...] | None:
    raw_models = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(raw_models, list):
        return None
    loaded: list[_LoadedModel] = []
    for model in raw_models:
        if not isinstance(model, dict):
            continue
        model_type = str(model.get("type") or "").strip().casefold()
        if model_type in {"embedding", "embeddings"}:
            continue
        state = str(model.get("state") or "").strip().casefold().replace("_", "-")
        if not state.startswith("loaded"):
            continue
        model_id = str(model.get("id") or model.get("model") or "").strip()
        if not model_id:
            continue
        loaded.append(
            _LoadedModel(
                instance_id=model_id,
                model_key=model_id,
                display_name=str(model.get("name") or model_id).strip(),
            )
        )
    return _deduplicate(loaded)


def _fetch_json(provider: LMStudioProvider, endpoint: str) -> Any:
    response = provider._make_request(
        "get",
        endpoint,
        timeout=_discovery_timeout_seconds(provider),
    )
    return response.json()


def _discover_loaded_models_uncached(provider: LMStudioProvider) -> _Discovery:
    try:
        parsed = _parse_v1_models(_fetch_json(provider, "/api/v1/models"))
    except (AttributeError, OSError, TypeError, ValueError):
        parsed = None
    if parsed is not None:
        return _Discovery(available=True, endpoint="/api/v1/models", models=parsed)

    try:
        parsed = _parse_v0_models(_fetch_json(provider, "/api/v0/models"))
    except (AttributeError, OSError, TypeError, ValueError):
        parsed = None
    if parsed is not None:
        return _Discovery(available=True, endpoint="/api/v0/models", models=parsed)
    return _Discovery(available=False, endpoint=None, models=())


def _discover_loaded_models(provider: LMStudioProvider) -> tuple[_Discovery, bool]:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _DISCOVERY_CACHE.get(provider)
        if cached is not None and cached.expires_at >= now:
            return cached.discovery, True

    discovery = _discover_loaded_models_uncached(provider)
    ttl = _cache_ttl_seconds()
    with _CACHE_LOCK:
        _DISCOVERY_CACHE[provider] = _CacheEntry(
            expires_at=time.monotonic() + ttl,
            discovery=discovery,
        )
    return discovery, False


def _resolve_lmstudio_model(
    provider: LMStudioProvider,
    requested_model: str | None,
) -> tuple[str | None, dict[str, Any]]:
    explicit = str(requested_model or "").strip()
    configured = str(provider.config.model or "").strip()
    if explicit:
        return explicit, {
            "source": "explicit_request",
            "selected_model": explicit,
            "configured_fallback": configured or None,
            "discovery_available": None,
            "discovery_endpoint": None,
            "discovery_cache_hit": None,
            "loaded_model_count": None,
        }

    discovery, cache_hit = _discover_loaded_models(provider)
    selected: str | None
    source: str
    if discovery.models:
        configured_match = next(
            (model for model in discovery.models if configured and model.matches(configured)),
            None,
        )
        chosen = configured_match or discovery.models[0]
        selected = chosen.instance_id
        source = (
            "loaded_instance_config_match"
            if configured_match is not None
            else "loaded_instance"
        )
    elif discovery.available and configured:
        selected = configured
        source = "configured_fallback_no_loaded_model"
    elif discovery.available:
        selected = None
        source = "runtime_default_no_loaded_model"
    else:
        # Do not send a possibly stale configured model when we could not prove
        # that LM Studio has no loaded model. Omitting it lets LM Studio use its
        # runtime default and avoids an unintended auto-load.
        selected = None
        source = "runtime_default_discovery_unavailable"

    return selected, {
        "source": source,
        "selected_model": selected,
        "configured_fallback": configured or None,
        "discovery_available": discovery.available,
        "discovery_endpoint": discovery.endpoint,
        "discovery_cache_hit": cache_hit,
        "loaded_model_count": len(discovery.models),
        "loaded_instance_ids": [model.instance_id for model in discovery.models],
    }


def _clear_lmstudio_model_discovery_cache() -> None:
    """Clear the short-lived cache; exposed for deterministic tests."""
    with _CACHE_LOCK:
        _DISCOVERY_CACHE.clear()


def install_lmstudio_loaded_model_resolution_hook() -> None:
    """Install loaded-instance-first model selection for LM Studio requests."""
    if getattr(LMStudioProvider, _HOOK_SENTINEL, False):
        return
    original_chat_completion = LMStudioProvider.chat_completion

    @wraps(original_chat_completion)
    def patched_chat_completion(
        self: LMStudioProvider,
        messages,
        model=None,
        stream: bool = False,
        **kwargs,
    ):
        resolved_model, diagnostics = _resolve_lmstudio_model(self, model)
        log_fields = dict(diagnostics)
        model_source = log_fields.pop("source")
        stream_log(
            "gateway-live-chat-first-token",
            "runtime",
            "live_chat_lmstudio_model_resolved",
            stream=bool(stream),
            model_source=model_source,
            **log_fields,
        )
        return original_chat_completion(
            self,
            messages,
            model=resolved_model,
            stream=stream,
            _use_configured_model=False,
            **kwargs,
        )

    LMStudioProvider.chat_completion = patched_chat_completion
    setattr(LMStudioProvider, _HOOK_SENTINEL, True)


__all__ = [
    "install_lmstudio_loaded_model_resolution_hook",
]
