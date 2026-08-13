"""Provider-neutral contracts for persistent low-latency speech recognition."""
from __future__ import annotations

import time
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

LIVE_STT_CONFIG_VERSION = "live-stt-v1"
PCM16LE_ENCODING = "pcm16le"

CAP_SEGMENTED_AUDIO = "segmented_audio"
CAP_AUTHORITATIVE_FINAL = "authoritative_final"
CAP_RESULT_REPLAY = "result_replay"
CAP_CLIENT_AUDIO_REPLAY = "client_audio_replay"
CAP_CONTINUOUS_WORDS = "continuous_words"
CAP_WORD_TIMESTAMPS = "word_timestamps"
CAP_SEMANTIC_ENDPOINTING = "semantic_endpointing"
CAP_DELAYED_FLUSH = "delayed_flush"
CAP_PARTIAL_TRANSCRIPTS = "partial_transcripts"
CAP_AUTHORITATIVE_EOU = "authoritative_eou"
CAP_AUTHORITATIVE_PREVIEW = "authoritative_preview"


@dataclass(frozen=True)
class LiveSttNegotiation:
    """Audio and capability contract frozen for one capture epoch."""

    provider: str
    protocol: str
    sample_rate: int
    frame_samples: int
    capabilities: frozenset[str]
    encoding: str = PCM16LE_ENCODING
    config_version: str = LIVE_STT_CONFIG_VERSION

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must not be empty")
        if not self.protocol.strip():
            raise ValueError("protocol must not be empty")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.frame_samples <= 0:
            raise ValueError("frame_samples must be positive")
        if self.encoding != PCM16LE_ENCODING:
            raise ValueError(f"unsupported live STT encoding: {self.encoding}")

    def ready_payload(self, *, connection_id: str, **extra: Any) -> dict[str, Any]:
        return {
            "type": "ready",
            "protocol": self.protocol,
            "provider": self.provider,
            "connectionId": connection_id,
            "sampleRate": self.sample_rate,
            "frameSamples": self.frame_samples,
            "encoding": self.encoding,
            "capabilities": sorted(self.capabilities),
            "configVersion": self.config_version,
            **extra,
        }


@dataclass(frozen=True)
class LiveSttEvent:
    """Normalized event emitted by a persistent STT session."""

    type: str
    text: str = ""
    probability: float | None = None
    model_time_ms: float | None = None
    start_ms: float | None = None
    end_ms: float | None = None
    attempt_id: str | None = None
    fields: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LiveSttFlushResult:
    attempt_id: str
    transcript: str
    wall_ms: float
    model_ms: float
    realtime_factor: float


@runtime_checkable
class LiveSttSession(Protocol):
    negotiation: LiveSttNegotiation

    async def send_audio(self, pcm16le: bytes) -> None: ...

    async def flush(self, attempt_id: str) -> LiveSttFlushResult: ...

    async def cancel_flush(self, attempt_id: str) -> None: ...

    def events(self) -> AsyncIterator[LiveSttEvent]: ...

    async def close(self) -> None: ...


@runtime_checkable
class LiveSttProvider(Protocol):
    provider_name: str

    async def create_live_session(self, *, language: str | None = None) -> LiveSttSession: ...

    async def health(self) -> Mapping[str, Any]: ...


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitSnapshot:
    state: CircuitState
    failures_in_window: int
    attempts_in_window: int
    retry_after_seconds: float


class LiveSttCircuitBreaker:
    """Small new-session circuit breaker; active utterances never switch providers."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        window_attempts: int = 5,
        cooldown_seconds: float = 60.0,
        max_cooldown_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if window_attempts < failure_threshold:
            raise ValueError("window_attempts must be >= failure_threshold")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive")
        self.failure_threshold = failure_threshold
        self.window_attempts = window_attempts
        self.cooldown_seconds = cooldown_seconds
        self.max_cooldown_seconds = max(cooldown_seconds, max_cooldown_seconds)
        self._clock = clock
        self._outcomes: deque[bool] = deque(maxlen=window_attempts)
        self._state = CircuitState.CLOSED
        self._opened_until = 0.0
        self._current_cooldown = cooldown_seconds
        self._half_open_probe_in_flight = False

    @property
    def state(self) -> CircuitState:
        self._refresh()
        return self._state

    def allow_new_session(self) -> bool:
        self._refresh()
        if self._state is CircuitState.CLOSED:
            return True
        if self._state is CircuitState.OPEN:
            return False
        if self._half_open_probe_in_flight:
            return False
        self._half_open_probe_in_flight = True
        return True

    def record_success(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._outcomes.clear()
        self._outcomes.append(True)
        self._state = CircuitState.CLOSED
        self._half_open_probe_in_flight = False
        self._current_cooldown = self.cooldown_seconds

    def record_failure(self, *, transient: bool = True) -> None:
        self._outcomes.append(False)
        self._half_open_probe_in_flight = False
        failures = sum(1 for succeeded in self._outcomes if not succeeded)
        if not transient or self._state is CircuitState.HALF_OPEN or failures >= self.failure_threshold:
            self._open()

    def snapshot(self) -> CircuitSnapshot:
        self._refresh()
        return CircuitSnapshot(
            state=self._state,
            failures_in_window=sum(1 for succeeded in self._outcomes if not succeeded),
            attempts_in_window=len(self._outcomes),
            retry_after_seconds=max(0.0, self._opened_until - self._clock())
            if self._state is CircuitState.OPEN
            else 0.0,
        )

    def _refresh(self) -> None:
        if self._state is CircuitState.OPEN and self._clock() >= self._opened_until:
            self._state = CircuitState.HALF_OPEN
            self._half_open_probe_in_flight = False

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_until = self._clock() + self._current_cooldown
        self._current_cooldown = min(self.max_cooldown_seconds, self._current_cooldown * 2.0)
