"""Process-local provider service formerly embedded in app.shared."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import weakref
from typing import Any, Optional

from app.config.env import env_str
from app.settings.access import current_settings_service, load_secrets, load_settings
from app.config.defaults import DEFAULT_SYSTEM_PROMPT
from app.runtime.config import GatewayRole, get_runtime_config
from app.runtime.capabilities import RuntimeCapabilities, RuntimeCapability

from .base import BaseProvider, ChatMessage, ProviderConfig
from .registry import get_registry
from .audio_registry import get_audio_registry

_PROVIDER_CACHE_TTL_SECONDS = 3600.0
_PROVIDER_CACHE: tuple[str | None, Any, float] = (None, None, 0.0)
_PROVIDER_SETTINGS_LOCK = threading.RLock()
_PROVIDER_SETTINGS_SUBSCRIPTIONS: weakref.WeakSet[Any] = weakref.WeakSet()
_tts_provider_instance: Any = None
_tts_provider_name: str | None = None
_tts_model_owner_guard: Any = None
_stt_provider_instance: Any = None
_stt_provider_name: str | None = None
_LOG = logging.getLogger(__name__)
_GLOBAL_PROMPT_LOCK = threading.RLock()
_GLOBAL_PROMPT_CACHE: tuple[int, float, str] | None = None
_GLOBAL_PROMPT_SUBSCRIPTIONS: weakref.WeakSet[Any] = weakref.WeakSet()
_GLOBAL_PROMPT_CACHE_HIT = False
_GLOBAL_PROMPT_CACHE_MODE = "defaults"


def _global_prompt_ttl_seconds() -> float:
    raw = env_str("OMNIX_LIVE_GLOBAL_PROMPT_CACHE_TTL_SECONDS", "60")
    try:
        return max(0.0, float(raw or "60"))
    except (TypeError, ValueError):
        return 60.0


def invalidate_global_system_prompt_cache() -> None:
    global _GLOBAL_PROMPT_CACHE
    with _GLOBAL_PROMPT_LOCK:
        _GLOBAL_PROMPT_CACHE = None


def global_system_prompt_cache_state() -> dict[str, Any]:
    with _GLOBAL_PROMPT_LOCK:
        return {"hit": _GLOBAL_PROMPT_CACHE_HIT, "mode": _GLOBAL_PROMPT_CACHE_MODE}


def _chatgpt_codex_settings(settings: dict[str, Any]) -> dict[str, Any]:
    profile = settings.get("settings_control_center", {})
    if not isinstance(profile, dict):
        return {}
    configs = profile.get("providerConfigs", {})
    if not isinstance(configs, dict):
        return {}
    value = configs.get("chatgptCodex", {})
    return dict(value) if isinstance(value, dict) else {}


def _cache_key(name: str, config: ProviderConfig) -> str:
    raw_key = config.api_key or ""
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16] if raw_key else ""
    extra = json.dumps(config.extra_params or {}, sort_keys=True, separators=(",", ":"), default=str)
    extra_hash = hashlib.sha256(extra.encode("utf-8")).hexdigest()[:16]
    return "|".join([name, config.base_url or "", config.model or "", key_hash, extra_hash])


def _close(instance: Any) -> None:
    close = getattr(instance, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            _LOG.warning("Provider close failed; cached instance was still retired")


def invalidate_provider_cache() -> None:
    global _PROVIDER_CACHE
    instance = _PROVIDER_CACHE[1]
    _PROVIDER_CACHE = (None, None, 0.0)
    if instance is not None:
        _close(instance)


def _subscribe_provider_cache_invalidation() -> None:
    try:
        service = current_settings_service()
    except RuntimeError:
        return
    with _PROVIDER_SETTINGS_LOCK:
        if service in _PROVIDER_SETTINGS_SUBSCRIPTIONS:
            return
        _PROVIDER_SETTINGS_SUBSCRIPTIONS.add(service)
        for key in (
            "provider",
            "lmstudio",
            "openrouter",
            "cerebras",
        ):
            service.subscribe(key, lambda _key, _value: invalidate_provider_cache())


def get_provider(provider_name: Optional[str] = None) -> Optional[BaseProvider]:
    global _PROVIDER_CACHE
    _subscribe_provider_cache_invalidation()
    settings = load_settings()
    secrets = load_secrets()
    name = provider_name or str(settings.get("provider") or "lmstudio")
    if name == "openrouter":
        cfg = dict(settings.get("openrouter") or {})
        config = ProviderConfig(
            provider_type=name,
            api_key=str((secrets.get("api_keys") or {}).get("openrouter") or cfg.get("api_key") or ""),
            base_url="https://openrouter.ai/api/v1",
            model=str(cfg.get("model") or "openai/gpt-4o-mini"),
            extra_params={
                "thinking_budget": cfg.get("thinking_budget", 0),
                "context_size": cfg.get("context_size", 128000),
            },
        )
    elif name == "cerebras":
        cfg = dict(settings.get("cerebras") or {})
        config = ProviderConfig(
            provider_type=name,
            api_key=str((secrets.get("api_keys") or {}).get("cerebras") or cfg.get("api_key") or ""),
            base_url="https://api.cerebras.ai",
            model=str(cfg.get("model") or "llama-3.3-70b-versatile"),
        )
    elif name == "chatgpt_codex":
        cfg = _chatgpt_codex_settings(settings)
        config = ProviderConfig(
            provider_type=name,
            model=str(cfg.get("model") or "gpt-5.6-sol"),
            extra_params={
                "reasoning_effort": str(cfg.get("reasoningEffort") or "medium"),
                "fast_mode": bool(cfg.get("fastMode", False)),
                "codex_path": str(cfg.get("codexPath") or "codex"),
                "transport": str(cfg.get("transport") or "app_server"),
            },
        )
    elif name == "llamacpp":
        cfg = dict(settings.get("llamacpp") or {})
        config = ProviderConfig(
            provider_type=name,
            base_url=str(cfg.get("base_url") or "http://localhost:8080"),
            model=str(cfg.get("model") or ""),
            extra_params={
                "download_location": str(cfg.get("download_location") or "server"),
                "auto_start": bool(cfg.get("auto_start", False)),
            },
        )
    else:
        name = "lmstudio" if not name else name
        cfg = dict(settings.get(name) or settings.get("lmstudio") or {})
        config = ProviderConfig(
            provider_type=name,
            base_url=str(cfg.get("base_url") or "http://localhost:1234"),
            model=str(cfg.get("model") or ""),
        )

    key = _cache_key(name, config)
    cached_key, cached, expires_at = _PROVIDER_CACHE
    now = time.monotonic()
    if cached is not None and expires_at <= now:
        invalidate_provider_cache()
        cached = None
        cached_key = None
    if cached_key == key and cached is not None:
        return cached
    instance = get_registry().create_provider(name, provider_config=config)
    if cached is not None and cached is not instance:
        _close(cached)
    _PROVIDER_CACHE = (key, instance, now + _PROVIDER_CACHE_TTL_SECONDS)
    return instance


def get_provider_config() -> dict[str, Any]:
    settings = load_settings()
    name = str(settings.get("provider") or "lmstudio")
    cfg = dict(settings.get(name) or {})
    return {
        "provider": name,
        "base_url": cfg.get("base_url"),
        "model": cfg.get("model"),
    }


def get_global_system_prompt() -> str:
    global _GLOBAL_PROMPT_CACHE, _GLOBAL_PROMPT_CACHE_HIT, _GLOBAL_PROMPT_CACHE_MODE
    try:
        service = current_settings_service()
    except RuntimeError:
        service = None
    service_id = id(service) if service is not None else 0
    _GLOBAL_PROMPT_CACHE_MODE = "service" if service is not None else "defaults"
    if service is not None:
        with _GLOBAL_PROMPT_LOCK:
            if service not in _GLOBAL_PROMPT_SUBSCRIPTIONS:
                service.subscribe(
                    "global_system_prompt",
                    lambda _key, _value: invalidate_global_system_prompt_cache(),
                )
                _GLOBAL_PROMPT_SUBSCRIPTIONS.add(service)
    now = time.monotonic()
    ttl = _global_prompt_ttl_seconds()
    with _GLOBAL_PROMPT_LOCK:
        cached = _GLOBAL_PROMPT_CACHE
        if cached is not None and cached[0] == service_id and now - cached[1] <= ttl:
            _GLOBAL_PROMPT_CACHE_HIT = True
            return cached[2]
    prompt = str(load_settings().get("global_system_prompt") or DEFAULT_SYSTEM_PROMPT)
    with _GLOBAL_PROMPT_LOCK:
        _GLOBAL_PROMPT_CACHE = (service_id, now, prompt)
        _GLOBAL_PROMPT_CACHE_HIT = False
    return prompt


def invalidate_audio_provider_cache(kind: str | None = None) -> None:
    """Stop and clear cached TTS/STT providers owned by this service."""
    global _tts_provider_instance, _tts_provider_name
    global _stt_provider_instance, _stt_provider_name
    global _tts_model_owner_guard

    if kind in (None, "tts"):
        instance = _tts_provider_instance
        _tts_provider_instance = None
        _tts_provider_name = None
        stop = getattr(instance, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                _LOG.warning("Audio provider stop failed during cache invalidation")
        guard, _tts_model_owner_guard = _tts_model_owner_guard, None
        if guard is not None:
            try:
                guard.close()
            except Exception:
                _LOG.warning("TTS model-owner lease release failed during cache invalidation")
    if kind in (None, "stt"):
        instance = _stt_provider_instance
        _stt_provider_instance = None
        _stt_provider_name = None
        stop = getattr(instance, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                _LOG.warning("Audio provider stop failed during cache invalidation")


def get_tts_provider(provider_name: str | None = None) -> Any:
    global _tts_provider_instance, _tts_provider_name, _tts_model_owner_guard
    settings = load_settings()
    name = provider_name or str(settings.get("audio_provider_tts") or "faster-qwen3-tts")
    runtime = get_runtime_config()
    endpoint = runtime.tts.url if runtime.tts else ""
    api_replica = runtime.gateway_role is GatewayRole.API
    use_http = name == "faster-qwen3-tts" and runtime.use_remote_tts
    if name == "faster-qwen3-tts" and api_replica and not use_http:
        raise RuntimeError(
            "API replicas cannot construct the local GPU TTS provider; configure OMNIX_TTS_URL"
        )
    if use_http:
        from .qwen_http_gateway import QwenHttpGatewayProvider
        if not endpoint:
            raise ValueError("Gateway HTTP TTS requires OMNIX_TTS_URL")
        key = f"{name}:http:{endpoint}"
        if _tts_provider_instance is None or _tts_provider_name != key:
            _tts_provider_instance = QwenHttpGatewayProvider(endpoint)
            _tts_provider_name = key
        return _tts_provider_instance

    RuntimeCapabilities.from_config(runtime).require(RuntimeCapability.RUN_LOCAL_TTS)
    if _tts_provider_instance is not None and _tts_provider_name == name:
        return _tts_provider_instance
    if _tts_provider_instance is not None:
        stop = getattr(_tts_provider_instance, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                _LOG.warning("TTS provider stop failed during replacement")
        guard, _tts_model_owner_guard = _tts_model_owner_guard, None
        if guard is not None:
            try:
                guard.close()
            except Exception:
                _LOG.warning("TTS model-owner lease release failed during replacement")
    provider_settings = dict(settings.get(name) or {})
    if name == "faster-qwen3-tts":
        config = provider_settings
    else:
        config = {
            "base_url": provider_settings.get("base_url"),
            "timeout": provider_settings.get("timeout", 300),
            "max_retries": provider_settings.get("max_retries", 3),
            "extra_params": provider_settings.get("extra_params", {}),
        }
    claimed_guard = None
    instance = None
    try:
        if name == "faster-qwen3-tts":
            from app.persistence.device_permits import default_device_permit_service

            permit_service = default_device_permit_service()
            if permit_service is not None and _tts_model_owner_guard is None:
                claimed_guard = permit_service.hold_model_owner(
                    "tts",
                    holder_id=f"{runtime.gateway_role.value}:{os.getpid()}",
                    process_role=(
                        "gateway"
                        if runtime.gateway_role is GatewayRole.WORKER
                        else runtime.gateway_role.value
                    ),
                )
                _tts_model_owner_guard = claimed_guard
        instance = get_audio_registry().create_tts_provider(name, config=config)
        if instance is not None and hasattr(instance, "start"):
            state = instance.start()
            if isinstance(state, dict) and not state.get("running", False):
                raise RuntimeError(str(state.get("message") or "TTS provider failed to start"))
        _tts_provider_instance = instance
        _tts_provider_name = name
        if claimed_guard is not None:
            stop = getattr(instance, "stop", None)
            if callable(stop):
                def stop_unowned_provider() -> None:
                    global _tts_provider_instance, _tts_provider_name, _tts_model_owner_guard
                    stop()
                    if _tts_provider_instance is instance:
                        _tts_provider_instance = None
                        _tts_provider_name = None
                    if _tts_model_owner_guard is claimed_guard:
                        _tts_model_owner_guard = None

                if not claimed_guard.set_on_lost(stop_unowned_provider):
                    raise RuntimeError(
                        "local TTS model-owner lease was lost during provider startup"
                    )
    except Exception:
        if _tts_provider_instance is instance:
            _tts_provider_instance = None
            _tts_provider_name = None
        if claimed_guard is not None:
            _tts_model_owner_guard = None
            claimed_guard.close()
        raise
    return instance


def get_stt_provider(provider_name: str | None = None) -> Any:
    global _stt_provider_instance, _stt_provider_name
    settings = load_settings()
    name = provider_name or str(settings.get("audio_provider_stt") or "parakeet")
    if _stt_provider_instance is not None and _stt_provider_name == name:
        return _stt_provider_instance
    if _stt_provider_instance is not None:
        stop = getattr(_stt_provider_instance, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                _LOG.warning("STT provider stop failed during replacement")
    cfg = dict(settings.get(name) or {})
    instance = get_audio_registry().create_stt_provider(
        name,
        config={
            "base_url": cfg.get("base_url"),
            "timeout": cfg.get("timeout", 300),
            "max_retries": cfg.get("max_retries", 3),
            "extra_params": cfg.get("extra_params", {}),
        },
    )
    if instance is not None and hasattr(instance, "start"):
        state = instance.start()
        if isinstance(state, dict) and not state.get("running", False):
            raise RuntimeError(str(state.get("message") or "STT provider failed to start"))
    _stt_provider_instance = instance
    _stt_provider_name = name
    return instance


def chat_completion(
    messages: list[dict[str, Any]] | list[ChatMessage],
    *,
    provider_name: str | None = None,
    model: str | None = None,
    stream: bool = False,
    **kwargs: Any,
):
    provider = get_provider(provider_name)
    if provider is None:
        raise RuntimeError("LLM provider is unavailable")
    normalized = [
        item if isinstance(item, ChatMessage) else ChatMessage(**item)
        for item in messages
    ]
    return provider.chat_completion(normalized, model=model, stream=stream, **kwargs)
