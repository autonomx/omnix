"""Hardware-gated policies for the local low-latency live-voice path.

The RTX 4090 validation path uses a Faster Qwen provider that explicitly reports
that generations cannot overlap. The live execution lane now serializes that
provider with accepted-first priority and bounded speculative chunk sizes, so
serial speculative TTS is safe by default and can be preempted when accepted
speech arrives. ``OMNIX_LIVE_TTS_ALLOW_SERIAL_SPECULATION=false`` remains an
explicit fail-closed kill switch if a provider proves unable to stop cleanly at
scheduler chunk boundaries.

This module is installed by the gateway entry point before the FastAPI app is
created. It also makes LM Studio Responses state reuse default-on for accepted
live-voice turns when the environment variable is absent, while preserving an
explicit false opt-out and logging the final eligibility decision. The loaded
model discovery cache is widened for the live hardware profile so a stable LM
Studio model does not require a management-API round trip on every accepted
turn; users can still override the cache TTL explicitly.
"""
from __future__ import annotations

import os
from functools import wraps
from typing import Any

from app.live_speech.performance_contract import resolve_tts_provider_capabilities

_STATE_ENV = "OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES"
_LMSTUDIO_DISCOVERY_CACHE_ENV = "OMNIX_LMSTUDIO_MODEL_DISCOVERY_CACHE_SECONDS"
_LMSTUDIO_DISCOVERY_CACHE_DEFAULT = "15"
_ALLOW_SERIAL_TTS_SPECULATION_ENV = "OMNIX_LIVE_TTS_ALLOW_SERIAL_SPECULATION"
_INSTALL_SENTINEL = "_omnix_live_voice_hardware_policy_installed"
_DEFERRED_TTS_ERROR = "speculative_tts_deferred_nonconcurrent_provider"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _bool_setting(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


def stateful_live_responses_enabled(raw: str | None) -> bool:
    """Default state reuse on for accepted live voice, preserving explicit opt-out."""
    return _bool_setting(raw, default=True)


def apply_live_voice_process_defaults() -> None:
    """Install process-level defaults before gateway modules capture env-backed gates.

    ``setdefault`` is intentional: an explicit operator value remains authoritative.
    The process-level value also makes the Responses default survive import-order or
    worker-start differences where the later function monkey-patch is not observed.
    """

    os.environ.setdefault(_STATE_ENV, "true")
    os.environ.setdefault(
        _LMSTUDIO_DISCOVERY_CACHE_ENV,
        _LMSTUDIO_DISCOVERY_CACHE_DEFAULT,
    )


def should_defer_speculative_tts(provider: Any, allow_serial: str | None = None) -> bool:
    """Defer serial speculation only when the explicit scheduler kill switch is off."""
    if _bool_setting(allow_serial, default=True):
        return False
    capabilities = resolve_tts_provider_capabilities(provider)
    return not capabilities.supports_concurrent_generation


def _deferred_speculative_entry(
    runtime: Any,
    generation_id: str,
    request: Any,
    provider: Any,
    lane: str,
) -> Any:
    """Create a terminal, non-claimable cache entry without touching the TTS model."""
    text = runtime._normalized_text(runtime.remove_emojis(request.text or ""))
    if not text:
        raise ValueError("text_required")
    speaker = runtime._normalized_speaker(request.speaker)
    language = runtime._normalized_language(request.language or "en")
    kwargs = runtime._stream_kwargs(request, provider)
    entry = runtime._SpeculativeTtsEntry(
        generation_id=generation_id,
        created_at=runtime.time.time(),
        text=text,
        speaker=speaker,
        language=language,
        stable_kwargs=runtime._stable_kwargs(kwargs),
        lane=lane,
        completed=True,
        error=_DEFERRED_TTS_ERROR,
    )
    with runtime._CACHE_LOCK:
        runtime._prune_entries_locked()
        previous = runtime._ENTRIES.pop(generation_id, None)
        runtime._ENTRIES[generation_id] = entry
        runtime._prune_entries_locked()
    if previous is not None:
        with previous.condition:
            previous.cancelled = True
            previous.condition.notify_all()

    capabilities = resolve_tts_provider_capabilities(provider)
    runtime.stream_log(
        "gateway-live-speculative-tts",
        "scheduler",
        "speculative_tts_prefetch_deferred_nonconcurrent",
        generation_id=generation_id,
        provider_name=getattr(provider, "provider_name", None),
        supports_concurrent_generation=capabilities.supports_concurrent_generation,
        execution_lane=lane,
        text_length=len(text),
    )
    return entry


def install_live_voice_hardware_policy() -> None:
    """Install scheduler-safe serial-TTS and stateful LM Studio live-voice policies."""
    # Apply env-backed defaults before importing gateway modules. Some gates are
    # evaluated by code reached during package import, and a process-level default
    # is more robust than relying solely on the later runtime monkey-patch.
    apply_live_voice_process_defaults()

    from app.gateway import live_chat_lmstudio_responses as responses_runtime
    from app.gateway import live_chat_provider_metrics as metrics_runtime
    from app.gateway import live_voice_speculative_tts as speculative_tts_runtime
    from app.gateway.tts_stream_diagnostics import stream_log

    if getattr(speculative_tts_runtime, _INSTALL_SENTINEL, False):
        return

    original_stateful_enabled = responses_runtime.stateful_responses_enabled

    @wraps(original_stateful_enabled)
    def patched_stateful_enabled() -> bool:
        raw = os.environ.get(_STATE_ENV)
        if raw is None:
            return True
        return stateful_live_responses_enabled(raw)

    responses_runtime.stateful_responses_enabled = patched_stateful_enabled

    original_start_prefetch = speculative_tts_runtime._start_prefetch

    @wraps(original_start_prefetch)
    def patched_start_prefetch(
        generation_id: str,
        request: Any,
        provider: Any,
        lane: str,
    ) -> Any:
        if should_defer_speculative_tts(
            provider,
            os.environ.get(_ALLOW_SERIAL_TTS_SPECULATION_ENV),
        ):
            return _deferred_speculative_entry(
                speculative_tts_runtime,
                generation_id,
                request,
                provider,
                lane,
            )
        return original_start_prefetch(generation_id, request, provider, lane)

    speculative_tts_runtime._start_prefetch = patched_start_prefetch

    # Observe the final Responses gate after the existing hook has wrapped the
    # LM Studio stream function. This is privacy-safe: no prompt or transcript is
    # logged, only eligibility booleans and provider type/name.
    responses_stream = metrics_runtime._stream_lmstudio_reply

    @wraps(responses_stream)
    def observed_responses_stream(
        self: Any,
        session: Any,
        user_message: Any,
        *,
        provider_id: str | None,
        model_id: str | None,
        context_items: list[dict[str, Any]] | None,
        provider: Any | None = None,
    ):
        is_live_voice = responses_runtime._is_live_voice_user_message(user_message)
        provider_name = str(getattr(provider, "provider_name", "") or "").strip().casefold()
        stateful_enabled = responses_runtime.stateful_responses_enabled()
        class_compatible = isinstance(provider, responses_runtime.LMStudioProvider)
        if is_live_voice and provider_name == "lmstudio":
            stream_log(
                "gateway-live-chat-first-token",
                "runtime",
                "live_chat_lmstudio_responses_eligibility",
                stateful_enabled=stateful_enabled,
                live_voice_message=True,
                provider_name=provider_name,
                provider_type=(
                    f"{type(provider).__module__}.{type(provider).__qualname__}"
                    if provider is not None
                    else None
                ),
                provider_class_compatible=class_compatible,
                provider_request_capable=callable(getattr(provider, "_make_request", None)),
                model_id=model_id,
                model_discovery_cache_seconds=os.environ.get(
                    _LMSTUDIO_DISCOVERY_CACHE_ENV
                ),
            )
        yield from responses_stream(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            context_items=context_items,
            provider=provider,
        )

    metrics_runtime._stream_lmstudio_reply = observed_responses_stream
    setattr(speculative_tts_runtime, _INSTALL_SENTINEL, True)


__all__ = [
    "apply_live_voice_process_defaults",
    "install_live_voice_hardware_policy",
    "should_defer_speculative_tts",
    "stateful_live_responses_enabled",
]
