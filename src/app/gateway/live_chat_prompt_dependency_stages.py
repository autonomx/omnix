"""Cache stable live-prompt inputs and expose dependency-level timings.

The bounded live-voice prompt path previously loaded and validated the same
assistant-memory settings several times per turn. Some calls happened inside
``resolve_prompt_memory`` and therefore bypassed the first cache implementation.
The global system prompt also reloaded the complete application settings
document on every turn.

This hook reuses both values while their backing signatures, environment
overrides, or in-process settings revision remain unchanged. PostgreSQL-backed
settings use a bounded TTL so out-of-process changes cannot remain stale
indefinitely.
"""
from __future__ import annotations

import copy
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any

from app import shared
from app.assistant_memory import settings as memory_settings_module
from app.chat import context_budget as context_budget_module
from app.chat import memory_prompt as memory_prompt_module
from app.chat import retention_policy as retention_policy_module

from . import live_chat_companion_context as companion_context
from . import live_chat_live_voice_profile as live_voice_profile
from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_prompt_dependency_stages_installed"
_MAX_SETTINGS_CACHE_ENTRIES = 8
_MAX_GLOBAL_PROMPT_CACHE_ENTRIES = 8
_DEFAULT_OVERRIDE_PROMPT_TTL_SECONDS = 60.0
_SETTINGS_ENV_NAMES = (
    "OMNIX_CHAT_MEMORY_ENABLED",
    "OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED",
    "OMNIX_CHAT_HISTORY_RECALL_ENABLED",
    "OMNIX_CHAT_COMPACTION_ENABLED",
    "OMNIX_HERMES_MEMORY_SYNC_ENABLED",
    "OMNIX_MEMORY_AUTOMATIC_DIRECT_ASSERTIONS",
    "OMNIX_COMPANION_PROACTIVE_MEMORY_ENABLED",
    "OMNIX_COMPANION_PARALINGUISTIC_ENABLED",
    "OMNIX_CHAT_TRANSCRIPT_RETENTION_ENABLED",
    "OMNIX_COMPANION_MASTER_ENABLED",
    "OMNIX_COMPANION_ROLLOUT_STAGE",
    "OMNIX_CHAT_MEMORY_TOKEN_BUDGET",
    "OMNIX_CHAT_HISTORY_TOKEN_BUDGET",
)
_STAGE_NAMES = (
    "budget_ms",
    "memory_service_ms",
    "memory_ms",
    "settings_ms",
    "rollout_ms",
    "scope_ms",
    "profile_ms",
    "temporal_ms",
    "temporal_materialize_ms",
    "memory_merge_ms",
    "packet_ms",
    "memory_usage_ms",
    "global_prompt_ms",
    "assembly_ms",
    "initiative_ms",
    "paralinguistic_ms",
    "render_ms",
    "diagnostics_ms",
)
# Settings calls can occur inside memory resolution and prompt-budget resolution,
# as well as directly in the builder. Keep their aggregate visible, but exclude
# it from the non-overlapping accounted total so nested time is not subtracted
# twice.
_ACCOUNTED_STAGE_NAMES = tuple(
    name for name in _STAGE_NAMES if name != "settings_ms"
)

_CACHE_LOCK = threading.RLock()
_MEMORY_SETTINGS_CACHE: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
_GLOBAL_SYSTEM_PROMPT_CACHE: OrderedDict[
    tuple[Any, ...],
    tuple[float, str],
] = OrderedDict()
_GLOBAL_PROMPT_OVERRIDE_REVISION = 0
_DEPENDENCY_TIMINGS: ContextVar[dict[str, Any] | None] = ContextVar(
    "omnix_live_prompt_dependency_timings",
    default=None,
)


def _clone(value: Any) -> Any:
    model_copy = getattr(value, "model_copy", None)
    if callable(model_copy):
        return model_copy(deep=True)
    return copy.deepcopy(value)


def _path_signature(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
        return str(path), int(stat.st_mtime_ns), int(stat.st_size)
    except FileNotFoundError:
        return str(path), 0, 0
    except OSError:
        return str(path), -1, -1


def _settings_cache_key() -> tuple[Any, ...]:
    path = memory_settings_module.default_memory_settings_path()
    environment = tuple((name, os.environ.get(name)) for name in _SETTINGS_ENV_NAMES)
    return (*_path_signature(path), environment)


def _global_prompt_override_ttl_seconds() -> float:
    raw = os.environ.get("OMNIX_LIVE_GLOBAL_PROMPT_CACHE_TTL_SECONDS")
    try:
        return max(0.0, float(raw or _DEFAULT_OVERRIDE_PROMPT_TTL_SECONDS))
    except (TypeError, ValueError):
        return _DEFAULT_OVERRIDE_PROMPT_TTL_SECONDS


def _global_prompt_cache_key() -> tuple[Any, ...]:
    override = getattr(shared, "_settings_load_override", None)
    if override is None:
        return ("file", *_path_signature(Path(shared.SETTINGS_FILE)))
    return ("override", id(override), _GLOBAL_PROMPT_OVERRIDE_REVISION)


def _global_prompt_cache_entry_valid(
    key: tuple[Any, ...],
    cached_at: float,
    now: float,
) -> bool:
    if key and key[0] == "file":
        return True
    return (now - cached_at) <= _global_prompt_override_ttl_seconds()


def _record_stage(name: str, elapsed_ms: float) -> None:
    timings = _DEPENDENCY_TIMINGS.get()
    if timings is not None:
        timings[name] = float(timings.get(name, 0.0) or 0.0) + elapsed_ms


def _record_flag(name: str, value: Any) -> None:
    timings = _DEPENDENCY_TIMINGS.get()
    if timings is not None:
        timings[name] = value


def _load_memory_runtime_settings_cached() -> Any:
    started = time.perf_counter()
    key = _settings_cache_key()
    with _CACHE_LOCK:
        cached = _MEMORY_SETTINGS_CACHE.get(key)
        if cached is not None:
            _MEMORY_SETTINGS_CACHE.move_to_end(key)
            _record_flag("settings_cache_hit", True)
            _record_stage("settings_ms", (time.perf_counter() - started) * 1000.0)
            return _clone(cached)

    result = _ORIGINAL_LOAD_MEMORY_SETTINGS()
    with _CACHE_LOCK:
        _MEMORY_SETTINGS_CACHE[key] = _clone(result)
        _MEMORY_SETTINGS_CACHE.move_to_end(key)
        while len(_MEMORY_SETTINGS_CACHE) > _MAX_SETTINGS_CACHE_ENTRIES:
            _MEMORY_SETTINGS_CACHE.popitem(last=False)
    _record_flag("settings_cache_hit", False)
    _record_stage("settings_ms", (time.perf_counter() - started) * 1000.0)
    return _clone(result)


def _get_global_system_prompt_cached() -> str:
    started = time.perf_counter()
    key = _global_prompt_cache_key()
    now = time.monotonic()
    mode = str(key[0]) if key else "unknown"
    with _CACHE_LOCK:
        cached = _GLOBAL_SYSTEM_PROMPT_CACHE.get(key)
        if cached is not None and _global_prompt_cache_entry_valid(
            key,
            cached[0],
            now,
        ):
            _GLOBAL_SYSTEM_PROMPT_CACHE.move_to_end(key)
            _record_flag("global_prompt_cache_hit", True)
            _record_flag("global_prompt_cache_mode", mode)
            _record_stage("global_prompt_ms", (time.perf_counter() - started) * 1000.0)
            return cached[1]
        if cached is not None:
            _GLOBAL_SYSTEM_PROMPT_CACHE.pop(key, None)

    result = str(_ORIGINAL_GET_GLOBAL_SYSTEM_PROMPT() or "")
    with _CACHE_LOCK:
        _GLOBAL_SYSTEM_PROMPT_CACHE[key] = (now, result)
        _GLOBAL_SYSTEM_PROMPT_CACHE.move_to_end(key)
        while len(_GLOBAL_SYSTEM_PROMPT_CACHE) > _MAX_GLOBAL_PROMPT_CACHE_ENTRIES:
            _GLOBAL_SYSTEM_PROMPT_CACHE.popitem(last=False)
    _record_flag("global_prompt_cache_hit", False)
    _record_flag("global_prompt_cache_mode", mode)
    _record_stage("global_prompt_ms", (time.perf_counter() - started) * 1000.0)
    return result


def _invalidate_global_prompt_cache() -> None:
    global _GLOBAL_PROMPT_OVERRIDE_REVISION
    with _CACHE_LOCK:
        _GLOBAL_PROMPT_OVERRIDE_REVISION += 1
        _GLOBAL_SYSTEM_PROMPT_CACHE.clear()


def _save_settings_and_invalidate(*args: Any, **kwargs: Any) -> Any:
    result = _ORIGINAL_SAVE_SETTINGS(*args, **kwargs)
    _invalidate_global_prompt_cache()
    return result


def _cached_compaction_enabled() -> bool:
    return bool(_load_memory_runtime_settings_cached().compaction_enabled)


def _timed_dependency(
    name: str,
    function: Callable[..., Any],
) -> Callable[..., Any]:
    @wraps(function)
    def timed(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            _record_stage(name, (time.perf_counter() - started) * 1000.0)

    return timed


def _install_dependency_wrappers() -> None:
    companion_context.load_memory_runtime_settings = (
        _load_memory_runtime_settings_cached
    )
    companion_context.compaction_enabled = _cached_compaction_enabled
    # Imported loader references are held in the consumer modules' globals.
    # Patch every live-prompt consumer; otherwise each missed reference performs
    # a full PostgreSQL-backed settings read despite the outer cache.
    memory_prompt_module.load_memory_runtime_settings = (
        _load_memory_runtime_settings_cached
    )
    context_budget_module.load_memory_runtime_settings = (
        _load_memory_runtime_settings_cached
    )
    retention_policy_module.load_memory_runtime_settings = (
        _load_memory_runtime_settings_cached
    )
    live_voice_profile._live_voice_prompt_budget = _timed_dependency(
        "budget_ms",
        live_voice_profile._live_voice_prompt_budget,
    )
    companion_context._create_memory_service = _timed_dependency(
        "memory_service_ms",
        companion_context._create_memory_service,
    )
    companion_context.resolve_prompt_memory = _timed_dependency(
        "memory_ms",
        companion_context.resolve_prompt_memory,
    )
    companion_context.companion_rollout_policy = _timed_dependency(
        "rollout_ms",
        companion_context.companion_rollout_policy,
    )
    companion_context.resolve_session_memory_scope = _timed_dependency(
        "scope_ms",
        companion_context.resolve_session_memory_scope,
    )
    companion_context._effective_profile = _timed_dependency(
        "profile_ms",
        companion_context._effective_profile,
    )
    companion_context.retrieve_temporal_context = _timed_dependency(
        "temporal_ms",
        companion_context.retrieve_temporal_context,
    )
    companion_context._temporal_prompt_memory = _timed_dependency(
        "temporal_materialize_ms",
        companion_context._temporal_prompt_memory,
    )
    companion_context._merge_memory = _timed_dependency(
        "memory_merge_ms",
        companion_context._merge_memory,
    )
    companion_context.build_companion_context_packet = _timed_dependency(
        "packet_ms",
        companion_context.build_companion_context_packet,
    )
    companion_context.record_memory_usage = _timed_dependency(
        "memory_usage_ms",
        companion_context.record_memory_usage,
    )
    companion_context.build_prompt_assembly = _timed_dependency(
        "assembly_ms",
        companion_context.build_prompt_assembly,
    )
    companion_context.plan_companion_initiative = _timed_dependency(
        "initiative_ms",
        companion_context.plan_companion_initiative,
    )
    companion_context.observe_paralinguistic_turn = _timed_dependency(
        "paralinguistic_ms",
        companion_context.observe_paralinguistic_turn,
    )
    companion_context.render_prompt_assembly = _timed_dependency(
        "render_ms",
        companion_context.render_prompt_assembly,
    )
    companion_context.record_companion_diagnostics = _timed_dependency(
        "diagnostics_ms",
        companion_context.record_companion_diagnostics,
    )
    shared.get_global_system_prompt = _get_global_system_prompt_cached
    shared.save_settings = _save_settings_and_invalidate


def _install_builder_breakdown() -> None:
    original_builder = live_voice_profile._build_live_voice_prompt

    @wraps(original_builder)
    def timed_builder(
        self: Any,
        session: Any,
        user_message: Any,
        context_items: list[dict[str, Any]] | None,
    ) -> Any:
        timings: dict[str, Any] = {}
        token = _DEPENDENCY_TIMINGS.set(timings)
        started = time.perf_counter()
        try:
            return original_builder(self, session, user_message, context_items)
        finally:
            total_ms = (time.perf_counter() - started) * 1000.0
            _DEPENDENCY_TIMINGS.reset(token)
            accounted_ms = sum(
                float(timings.get(name, 0.0) or 0.0)
                for name in _ACCOUNTED_STAGE_NAMES
            )
            stream_log(
                "gateway-live-chat-first-token",
                "runtime",
                "live_chat_prompt_dependency_stages",
                session_message_count=len(getattr(session, "messages", []) or []),
                total_ms=round(total_ms, 3),
                settings_cache_hit=timings.get("settings_cache_hit"),
                global_prompt_cache_hit=timings.get("global_prompt_cache_hit"),
                global_prompt_cache_mode=timings.get("global_prompt_cache_mode"),
                **{
                    name: round(float(timings.get(name, 0.0) or 0.0), 3)
                    for name in _STAGE_NAMES
                },
                unclassified_ms=round(max(0.0, total_ms - accounted_ms), 3),
            )

    live_voice_profile._build_live_voice_prompt = timed_builder


def _reset_live_prompt_dependency_state_for_tests() -> None:
    global _GLOBAL_PROMPT_OVERRIDE_REVISION
    with _CACHE_LOCK:
        _MEMORY_SETTINGS_CACHE.clear()
        _GLOBAL_SYSTEM_PROMPT_CACHE.clear()
        _GLOBAL_PROMPT_OVERRIDE_REVISION = 0


def install_live_chat_prompt_dependency_stage_hook() -> None:
    """Install after the stable prompt cache and companion-context hook."""

    if getattr(live_voice_profile, _HOOK_SENTINEL, False):
        return
    _install_dependency_wrappers()
    _install_builder_breakdown()
    setattr(live_voice_profile, _HOOK_SENTINEL, True)


_ORIGINAL_LOAD_MEMORY_SETTINGS = companion_context.load_memory_runtime_settings
_ORIGINAL_GET_GLOBAL_SYSTEM_PROMPT = shared.get_global_system_prompt
_ORIGINAL_SAVE_SETTINGS = shared.save_settings


__all__ = ["install_live_chat_prompt_dependency_stage_hook"]
