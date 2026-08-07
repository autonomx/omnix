"""Dedicated low-latency model and accepted-first TTS execution lane."""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from app import shared
from app.providers.audio_registry import get_audio_registry

from .tts_stream_diagnostics import stream_log


class TtsLanePriority(IntEnum):
    ACCEPTED = 0
    CONTINUATION = 1
    SPECULATIVE = 2


@dataclass(frozen=True)
class LiveVoiceExecutionLaneConfig:
    mode: str
    provider_id: str | None
    model_id: str | None
    dedicated_tts: bool
    tts_provider_name: str | None

    @property
    def dedicated_chat_enabled(self) -> bool:
        return self.mode == "dedicated" and bool(self.provider_id or self.model_id)


@dataclass
class _TtsTicket:
    priority: TtsLanePriority
    sequence: int
    promotion_event: threading.Event | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    started: bool = False


class PriorityTtsScheduler:
    """Serialize non-concurrent TTS providers with accepted turns first.

    A newly accepted request cancels an active unaccepted speculative stream.
    A speculative first clause that becomes authoritative can be promoted in
    place and is then protected from later accepted-turn preemption.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._waiting: list[_TtsTicket] = []
        self._active: _TtsTicket | None = None
        self._sequence = 0

    def stream(
        self,
        provider: Any,
        *,
        text: str,
        speaker: str | None,
        language: str,
        kwargs: dict[str, Any],
        priority: TtsLanePriority,
        should_stop: Callable[[], bool] | None = None,
        promotion_event: threading.Event | None = None,
    ) -> Iterator[tuple[Any, int, Any]]:
        ticket = self._acquire(priority, promotion_event)
        stream: Any = None
        try:
            if self._stopped(ticket, should_stop):
                return
            stream = provider.generate_audio_stream(
                text=text,
                speaker=speaker,
                language=language,
                **kwargs,
            )
            for chunk in stream:
                if self._stopped(ticket, should_stop):
                    return
                yield chunk
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
            self._release(ticket)

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            return {
                "active_priority": (
                    int(self._effective_priority(self._active))
                    if self._active is not None
                    else None
                ),
                "active_cancelled": bool(
                    self._active and self._active.cancel_event.is_set()
                ),
                "waiting": [
                    int(self._effective_priority(ticket))
                    for ticket in self._waiting
                ],
            }

    def clear(self) -> None:
        with self._condition:
            if self._active is not None:
                self._active.cancel_event.set()
            for ticket in self._waiting:
                ticket.cancel_event.set()
            self._waiting.clear()
            self._condition.notify_all()

    def notify_priority_change(self) -> None:
        with self._condition:
            self._condition.notify_all()

    def _acquire(
        self,
        priority: TtsLanePriority,
        promotion_event: threading.Event | None,
    ) -> _TtsTicket:
        with self._condition:
            self._sequence += 1
            ticket = _TtsTicket(
                priority=priority,
                sequence=self._sequence,
                promotion_event=promotion_event,
            )
            self._waiting.append(ticket)
            if (
                priority == TtsLanePriority.ACCEPTED
                and self._active is not None
                and self._effective_priority(self._active)
                == TtsLanePriority.SPECULATIVE
            ):
                self._active.cancel_event.set()
                stream_log(
                    "gateway-live-voice-lane",
                    "scheduler",
                    "speculative_tts_preempt_requested",
                    active_sequence=self._active.sequence,
                    accepted_sequence=ticket.sequence,
                )
            while True:
                if ticket.cancel_event.is_set():
                    self._waiting = [item for item in self._waiting if item is not ticket]
                    raise RuntimeError("tts_lane_ticket_cancelled")
                next_ticket = min(
                    self._waiting,
                    key=lambda item: (
                        int(self._effective_priority(item)),
                        item.sequence,
                    ),
                )
                if self._active is None and next_ticket is ticket:
                    self._waiting.remove(ticket)
                    self._active = ticket
                    ticket.started = True
                    return ticket
                self._condition.wait(timeout=0.025)

    def _release(self, ticket: _TtsTicket) -> None:
        with self._condition:
            if self._active is ticket:
                self._active = None
            self._waiting = [item for item in self._waiting if item is not ticket]
            self._condition.notify_all()

    @staticmethod
    def _effective_priority(ticket: _TtsTicket) -> TtsLanePriority:
        if ticket.promotion_event is not None and ticket.promotion_event.is_set():
            return TtsLanePriority.ACCEPTED
        return ticket.priority

    @staticmethod
    def _stopped(
        ticket: _TtsTicket,
        should_stop: Callable[[], bool] | None,
    ) -> bool:
        return ticket.cancel_event.is_set() or bool(should_stop and should_stop())


_TTS_SCHEDULER = PriorityTtsScheduler()
_DEDICATED_TTS_LOCK = threading.RLock()
_DEDICATED_TTS_PROVIDER: Any = None
_DEDICATED_TTS_KEY: str | None = None
_DEDICATED_TTS_PROVIDER_NAME: str | None = None


def _normalized(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _boolean_setting(name: str, fallback: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def live_voice_execution_lane_config() -> LiveVoiceExecutionLaneConfig:
    mode = (os.environ.get("OMNIX_LIVE_VOICE_EXECUTION_MODE") or "session").strip().lower()
    if mode not in {"session", "dedicated"}:
        mode = "session"
    return LiveVoiceExecutionLaneConfig(
        mode=mode,
        provider_id=_normalized(os.environ.get("OMNIX_LIVE_VOICE_PROVIDER_ID")),
        model_id=_normalized(os.environ.get("OMNIX_LIVE_VOICE_MODEL_ID")),
        dedicated_tts=_boolean_setting("OMNIX_LIVE_TTS_DEDICATED", False),
        tts_provider_name=_normalized(
            os.environ.get("OMNIX_LIVE_TTS_PROVIDER_NAME")
        ),
    )


def resolve_live_voice_chat_route(
    provider_id: str | None,
    model_id: str | None,
) -> tuple[str | None, str | None, str]:
    config = live_voice_execution_lane_config()
    if not config.dedicated_chat_enabled:
        return provider_id, model_id, "session"
    return (
        config.provider_id or provider_id,
        config.model_id or model_id,
        "dedicated",
    )


def live_voice_tts_scheduler() -> PriorityTtsScheduler:
    return _TTS_SCHEDULER


def resolve_live_voice_tts_provider(default_provider: Any) -> tuple[Any, str]:
    """Return an optional separately instantiated provider for the live lane."""
    config = live_voice_execution_lane_config()
    provider_name = config.tts_provider_name
    if not config.dedicated_tts or not provider_name:
        return default_provider, "shared"

    # Dedicated live TTS is an explicit process-level configuration. Once that
    # provider is started, return it directly on the phrase hot path instead of
    # reloading application settings for every clause. A process restart/reset
    # remains the boundary for changing the dedicated provider configuration.
    with _DEDICATED_TTS_LOCK:
        if (
            _DEDICATED_TTS_PROVIDER is not None
            and _DEDICATED_TTS_PROVIDER_NAME == provider_name
        ):
            return _DEDICATED_TTS_PROVIDER, "dedicated"

    settings = shared.load_settings()
    provider_settings = dict(settings.get(provider_name, {}) or {})
    cache_key = json.dumps(
        {"provider": provider_name, "settings": provider_settings},
        sort_keys=True,
        default=str,
    )
    global _DEDICATED_TTS_KEY, _DEDICATED_TTS_PROVIDER, _DEDICATED_TTS_PROVIDER_NAME
    with _DEDICATED_TTS_LOCK:
        if (
            _DEDICATED_TTS_PROVIDER is not None
            and _DEDICATED_TTS_KEY == cache_key
        ):
            _DEDICATED_TTS_PROVIDER_NAME = provider_name
            return _DEDICATED_TTS_PROVIDER, "dedicated"

        previous = _DEDICATED_TTS_PROVIDER
        if previous is not None:
            stop = getattr(previous, "stop", None)
            if callable(stop):
                stop()
        registry = get_audio_registry()
        if provider_name == "faster-qwen3-tts":
            provider_config = provider_settings
        else:
            provider_config = {
                "base_url": provider_settings.get("base_url"),
                "timeout": provider_settings.get("timeout", 300),
                "max_retries": provider_settings.get("max_retries", 3),
                "extra_params": provider_settings.get("extra_params", {}),
            }
        provider = registry.create_tts_provider(
            provider_name,
            config=provider_config,
        )
        if provider is None:
            raise RuntimeError(f"live_tts_provider_unavailable:{provider_name}")
        start = getattr(provider, "start", None)
        if callable(start):
            result = start()
            if isinstance(result, dict) and result.get("running") is False:
                raise RuntimeError(
                    f"live_tts_provider_start_failed:{provider_name}"
                )
        _DEDICATED_TTS_PROVIDER = provider
        _DEDICATED_TTS_KEY = cache_key
        _DEDICATED_TTS_PROVIDER_NAME = provider_name
        return provider, "dedicated"


def reset_live_voice_execution_lane_for_tests() -> None:
    global _DEDICATED_TTS_KEY, _DEDICATED_TTS_PROVIDER, _DEDICATED_TTS_PROVIDER_NAME
    _TTS_SCHEDULER.clear()
    with _DEDICATED_TTS_LOCK:
        provider = _DEDICATED_TTS_PROVIDER
        _DEDICATED_TTS_PROVIDER = None
        _DEDICATED_TTS_KEY = None
        _DEDICATED_TTS_PROVIDER_NAME = None
    stop = getattr(provider, "stop", None)
    if callable(stop):
        stop()


__all__ = [
    "LiveVoiceExecutionLaneConfig",
    "PriorityTtsScheduler",
    "TtsLanePriority",
    "live_voice_execution_lane_config",
    "live_voice_tts_scheduler",
    "reset_live_voice_execution_lane_for_tests",
    "resolve_live_voice_chat_route",
    "resolve_live_voice_tts_provider",
]
