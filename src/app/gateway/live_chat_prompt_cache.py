"""Cache stable live-voice prompt inputs and expose prompt-stage timings.

The live call runtime resolves the active character before the first user turn.
Prompt assembly previously discarded that work and resolved the same immutable
character snapshot again for every response. This module reuses version-pinned
snapshots, caches file-backed Live Conversation profiles by file signature, and
adds content-free stage timings around the bounded live prompt path.
"""
from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import Any

from app.characters.interaction import InteractionSelection, resolve_interaction_context
from app.characters.live_conversation_profile import LiveConversationProfileStore
from app.characters.service import CharacterService, default_character_service
from app.chat import prompt_assembly as prompt_assembly_module

from . import live_chat_companion_context as companion_context
from . import live_chat_live_voice_profile as live_voice_profile
from .tts_stream_diagnostics import stream_log

_HOOK_SENTINEL = "_omnix_live_chat_prompt_cache_installed"
_CHARACTER_SERVICE_SENTINEL = "_omnix_live_prompt_character_cache_installed"
_PROFILE_STORE_SENTINEL = "_omnix_live_prompt_profile_cache_installed"
_MAX_CACHE_ENTRIES = 256

_CACHE_LOCK = threading.RLock()
_CHARACTER_SNAPSHOTS: OrderedDict[tuple[str, int], Any] = OrderedDict()
_IDENTITY_CONTEXTS: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
_PROFILE_ENVELOPES: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
_PROMPT_STAGE_TIMINGS: ContextVar[dict[str, Any] | None] = ContextVar(
    "omnix_live_prompt_stage_timings",
    default=None,
)


def _clone(value: Any) -> Any:
    model_copy = getattr(value, "model_copy", None)
    if callable(model_copy):
        return model_copy(deep=True)
    return copy.deepcopy(value)


def _bounded_put(cache: OrderedDict[Any, Any], key: Any, value: Any) -> None:
    cache[key] = _clone(value)
    cache.move_to_end(key)
    while len(cache) > _MAX_CACHE_ENTRIES:
        cache.popitem(last=False)


def _character_snapshot_version(snapshot: Any) -> int:
    try:
        return int(getattr(snapshot, "version", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _cache_character_snapshot(snapshot: Any) -> None:
    character_id = str(getattr(snapshot, "id", "") or "").strip()
    version = _character_snapshot_version(snapshot)
    if not character_id or version < 1:
        return
    with _CACHE_LOCK:
        _bounded_put(_CHARACTER_SNAPSHOTS, (character_id, version), snapshot)


def _invalidate_character(character_id: str) -> None:
    normalized = str(character_id or "").strip()
    if not normalized:
        return
    with _CACHE_LOCK:
        for key in [key for key in _CHARACTER_SNAPSHOTS if key[0] == normalized]:
            _CHARACTER_SNAPSHOTS.pop(key, None)
        for key in [key for key in _IDENTITY_CONTEXTS if key[1] == normalized]:
            _IDENTITY_CONTEXTS.pop(key, None)


def _identity_key(session: Any) -> tuple[Any, ...]:
    return (
        str(getattr(session, "interaction_mode", "system") or "system"),
        str(getattr(session, "character_id", "") or ""),
        getattr(session, "character_profile_version", None),
        str(getattr(session, "effective_identity_hash", "") or ""),
        str(getattr(session, "voice_asset_id", "") or ""),
        bool(getattr(session, "read_memory", False)),
        bool(getattr(session, "write_memory", False)),
        str(getattr(session, "shared_memory_access", "none") or "none"),
        str(getattr(session, "transcript_policy", "persistent") or "persistent"),
    )


def _record_stage(name: str, elapsed_ms: float) -> None:
    timings = _PROMPT_STAGE_TIMINGS.get()
    if timings is not None:
        timings[name] = timings.get(name, 0.0) + elapsed_ms


def _record_flag(name: str, value: bool) -> None:
    timings = _PROMPT_STAGE_TIMINGS.get()
    if timings is not None:
        timings[name] = value


def _resolve_system_session_identity_cached(session: Any) -> Any:
    started = time.perf_counter()
    key = _identity_key(session)
    with _CACHE_LOCK:
        cached = _IDENTITY_CONTEXTS.get(key)
        if cached is not None:
            _IDENTITY_CONTEXTS.move_to_end(key)
            result = _clone(cached)
            _record_flag("identity_cache_hit", True)
            _record_stage("identity_ms", (time.perf_counter() - started) * 1000.0)
            return result

    interaction_mode = key[0]
    if interaction_mode != "character":
        result = _ORIGINAL_IDENTITY_RESOLVER(session)
    else:
        character_id = key[1]
        expected_version = key[2]
        snapshot = None
        if character_id and isinstance(expected_version, int) and expected_version > 0:
            with _CACHE_LOCK:
                snapshot = _CHARACTER_SNAPSHOTS.get((character_id, expected_version))
                if snapshot is not None:
                    _CHARACTER_SNAPSHOTS.move_to_end((character_id, expected_version))
                    snapshot = _clone(snapshot)
        if snapshot is None:
            snapshot = default_character_service().resolve_snapshot(character_id)
            _cache_character_snapshot(snapshot)
        selection = InteractionSelection(
            interaction_mode="character",
            character_id=character_id,
            voice_asset_id=getattr(session, "voice_asset_id", None),
            read_memory=bool(getattr(session, "read_memory", False)),
            write_memory=bool(getattr(session, "write_memory", False)),
            shared_memory_access=getattr(session, "shared_memory_access", "none"),
            transcript_policy=getattr(session, "transcript_policy", "persistent"),
        )
        result = resolve_interaction_context(selection, character=snapshot)

    with _CACHE_LOCK:
        _bounded_put(_IDENTITY_CONTEXTS, key, result)
    _record_flag("identity_cache_hit", False)
    _record_stage("identity_ms", (time.perf_counter() - started) * 1000.0)
    return _clone(result)


def _profile_signature(store: Any) -> tuple[str, int, int] | None:
    path = getattr(store, "path", None)
    if not isinstance(path, Path):
        return None
    try:
        stat = path.stat()
        return str(path), int(stat.st_mtime_ns), int(stat.st_size)
    except FileNotFoundError:
        return str(path), 0, 0
    except OSError:
        return None


def _invalidate_profile_store(store: Any) -> None:
    store_id = id(store)
    with _CACHE_LOCK:
        for key in [key for key in _PROFILE_ENVELOPES if key[0] == store_id]:
            _PROFILE_ENVELOPES.pop(key, None)


def _install_character_snapshot_cache() -> None:
    if getattr(CharacterService, _CHARACTER_SERVICE_SENTINEL, False):
        return

    original_resolve_snapshot = CharacterService.resolve_snapshot
    original_create = CharacterService.create
    original_update = CharacterService.update
    original_archive = CharacterService.archive

    @wraps(original_resolve_snapshot)
    def cached_resolve_snapshot(self: CharacterService, character_id: str) -> Any:
        snapshot = original_resolve_snapshot(self, character_id)
        _cache_character_snapshot(snapshot)
        return snapshot

    @wraps(original_create)
    def cached_create(self: CharacterService, request: Any) -> Any:
        result = original_create(self, request)
        _invalidate_character(str(getattr(result, "id", "") or ""))
        return result

    @wraps(original_update)
    def cached_update(self: CharacterService, character_id: str, request: Any) -> Any:
        result = original_update(self, character_id, request)
        _invalidate_character(character_id)
        return result

    @wraps(original_archive)
    def cached_archive(self: CharacterService, character_id: str) -> Any:
        result = original_archive(self, character_id)
        _invalidate_character(character_id)
        return result

    CharacterService.resolve_snapshot = cached_resolve_snapshot
    CharacterService.create = cached_create
    CharacterService.update = cached_update
    CharacterService.archive = cached_archive
    setattr(CharacterService, _CHARACTER_SERVICE_SENTINEL, True)


def _install_profile_cache() -> None:
    if getattr(LiveConversationProfileStore, _PROFILE_STORE_SENTINEL, False):
        return

    original_get = LiveConversationProfileStore.get
    original_update_defaults = LiveConversationProfileStore.update_defaults
    original_update = LiveConversationProfileStore.update
    original_clear = LiveConversationProfileStore.clear

    @wraps(original_get)
    def cached_get(self: LiveConversationProfileStore, session_id: str) -> Any:
        started = time.perf_counter()
        signature = _profile_signature(self)
        key = (id(self), signature, session_id)
        if signature is not None:
            with _CACHE_LOCK:
                cached = _PROFILE_ENVELOPES.get(key)
                if cached is not None:
                    _PROFILE_ENVELOPES.move_to_end(key)
                    _record_flag("profile_cache_hit", True)
                    _record_stage("profile_store_ms", (time.perf_counter() - started) * 1000.0)
                    return _clone(cached)
        result = original_get(self, session_id)
        if signature is not None:
            refreshed_signature = _profile_signature(self)
            refreshed_key = (id(self), refreshed_signature, session_id)
            with _CACHE_LOCK:
                _bounded_put(_PROFILE_ENVELOPES, refreshed_key, result)
        _record_flag("profile_cache_hit", False)
        _record_stage("profile_store_ms", (time.perf_counter() - started) * 1000.0)
        return result

    @wraps(original_update_defaults)
    def cached_update_defaults(self: LiveConversationProfileStore, update: Any) -> Any:
        result = original_update_defaults(self, update)
        _invalidate_profile_store(self)
        return result

    @wraps(original_update)
    def cached_update(self: LiveConversationProfileStore, session_id: str, update: Any) -> Any:
        result = original_update(self, session_id, update)
        _invalidate_profile_store(self)
        return result

    @wraps(original_clear)
    def cached_clear(self: LiveConversationProfileStore, session_id: str) -> Any:
        result = original_clear(self, session_id)
        _invalidate_profile_store(self)
        return result

    LiveConversationProfileStore.get = cached_get
    LiveConversationProfileStore.update_defaults = cached_update_defaults
    LiveConversationProfileStore.update = cached_update
    LiveConversationProfileStore.clear = cached_clear
    setattr(LiveConversationProfileStore, _PROFILE_STORE_SENTINEL, True)


def _timed_dependency(name: str, function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def timed(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            _record_stage(name, (time.perf_counter() - started) * 1000.0)

    return timed


def _install_prompt_stage_timings() -> None:
    companion_context.resolve_prompt_memory = _timed_dependency(
        "memory_ms",
        companion_context.resolve_prompt_memory,
    )
    companion_context._effective_profile = _timed_dependency(
        "profile_ms",
        companion_context._effective_profile,
    )
    companion_context.build_prompt_assembly = _timed_dependency(
        "assembly_ms",
        companion_context.build_prompt_assembly,
    )
    companion_context.render_prompt_assembly = _timed_dependency(
        "render_ms",
        companion_context.render_prompt_assembly,
    )

    original_builder = live_voice_profile._build_live_voice_prompt

    @wraps(original_builder)
    def timed_builder(
        self: Any,
        session: Any,
        user_message: Any,
        context_items: list[dict[str, Any]] | None,
    ) -> Any:
        timings: dict[str, Any] = {}
        token = _PROMPT_STAGE_TIMINGS.set(timings)
        started = time.perf_counter()
        try:
            return original_builder(self, session, user_message, context_items)
        finally:
            total_ms = (time.perf_counter() - started) * 1000.0
            _PROMPT_STAGE_TIMINGS.reset(token)
            accounted_ms = sum(
                float(timings.get(name, 0.0) or 0.0)
                for name in ("memory_ms", "profile_ms", "assembly_ms", "render_ms")
            )
            stream_log(
                "gateway-live-chat-first-token",
                "runtime",
                "live_chat_prompt_stages",
                session_message_count=len(getattr(session, "messages", []) or []),
                total_ms=round(total_ms, 3),
                memory_ms=round(float(timings.get("memory_ms", 0.0) or 0.0), 3),
                profile_ms=round(float(timings.get("profile_ms", 0.0) or 0.0), 3),
                profile_store_ms=round(
                    float(timings.get("profile_store_ms", 0.0) or 0.0),
                    3,
                ),
                profile_cache_hit=timings.get("profile_cache_hit"),
                assembly_ms=round(float(timings.get("assembly_ms", 0.0) or 0.0), 3),
                identity_ms=round(float(timings.get("identity_ms", 0.0) or 0.0), 3),
                identity_cache_hit=timings.get("identity_cache_hit"),
                render_ms=round(float(timings.get("render_ms", 0.0) or 0.0), 3),
                residual_ms=round(max(0.0, total_ms - accounted_ms), 3),
            )

    live_voice_profile._build_live_voice_prompt = timed_builder


def _reset_live_prompt_cache_for_tests() -> None:
    with _CACHE_LOCK:
        _CHARACTER_SNAPSHOTS.clear()
        _IDENTITY_CONTEXTS.clear()
        _PROFILE_ENVELOPES.clear()


def install_live_chat_prompt_cache_hook() -> None:
    """Install stable-input caches after the live companion prompt hook."""

    if getattr(live_voice_profile, _HOOK_SENTINEL, False):
        return
    _install_character_snapshot_cache()
    _install_profile_cache()
    prompt_assembly_module.resolve_system_session_identity = (
        _resolve_system_session_identity_cached
    )
    _install_prompt_stage_timings()
    setattr(live_voice_profile, _HOOK_SENTINEL, True)


_ORIGINAL_IDENTITY_RESOLVER = prompt_assembly_module.resolve_system_session_identity


__all__ = [
    "install_live_chat_prompt_cache_hook",
]
