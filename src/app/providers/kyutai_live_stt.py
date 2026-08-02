"""Kyutai moshi-server adapter for persistent low-latency STT sessions."""
from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from array import array
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, AsyncIterator, Mapping

import msgpack
import websockets

from app.providers.live_stt_contracts import (
    CAP_AUTHORITATIVE_FINAL,
    CAP_CONTINUOUS_WORDS,
    CAP_DELAYED_FLUSH,
    CAP_SEMANTIC_ENDPOINTING,
    CAP_WORD_TIMESTAMPS,
    LiveSttCircuitBreaker,
    LiveSttEvent,
    LiveSttFlushResult,
    LiveSttNegotiation,
)

KYUTAI_SAMPLE_RATE = 24_000
KYUTAI_FRAME_SAMPLES = 1_920
KYUTAI_FRAME_SECONDS = KYUTAI_FRAME_SAMPLES / KYUTAI_SAMPLE_RATE
KYUTAI_MODEL_DELAY_SECONDS = 0.5
KYUTAI_STARTUP_SUPPRESSION_STEPS = 12
KYUTAI_STT_PATH = "/api/asr-streaming"
SUPPORTED_LANGUAGES = frozenset({"en", "en-us", "en-ca", "en-gb", "fr", "fr-ca", "fr-fr"})


class KyutaiLiveSttError(RuntimeError):
    pass


@dataclass
class _AsymmetricEma:
    attack_seconds: float = 0.01
    release_seconds: float = 0.01
    value: float = 1.0

    def update(self, *, dt: float, new_value: float) -> float:
        time_constant = self.attack_seconds if new_value > self.value else self.release_seconds
        alpha = 1.0 - math.exp(-dt / time_constant * math.log(2.0))
        self.value = (1.0 - alpha) * self.value + alpha * new_value
        return self.value


def _normalize_language(language: str | None) -> str:
    return (language or "en").strip().lower().replace("_", "-")


def _join_url(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith(path) else f"{normalized}{path}"


async def _connect_websocket(
    url: str,
    *,
    headers: dict[str, str],
    timeout_seconds: float,
) -> Any:
    try:
        connection = websockets.connect(url, additional_headers=headers, max_size=None)
        return await asyncio.wait_for(connection, timeout=timeout_seconds)
    except TypeError as exc:
        if "additional_headers" not in str(exc):
            raise
        connection = websockets.connect(url, extra_headers=headers, max_size=None)
        return await asyncio.wait_for(connection, timeout=timeout_seconds)


def pcm16le_to_float32(pcm16le: bytes) -> list[float]:
    if len(pcm16le) % 2:
        raise ValueError("PCM16 payload must contain whole samples")
    samples = array("h")
    samples.frombytes(pcm16le)
    if sys.byteorder != "little":
        samples.byteswap()
    return [max(-1.0, min(1.0, int(sample) / 32768.0)) for sample in samples]


class KyutaiLiveSttSession:
    negotiation = LiveSttNegotiation(
        provider="kyutai",
        protocol="segmented-v1",
        sample_rate=KYUTAI_SAMPLE_RATE,
        frame_samples=KYUTAI_FRAME_SAMPLES,
        capabilities=frozenset(
            {
                CAP_CONTINUOUS_WORDS,
                CAP_WORD_TIMESTAMPS,
                CAP_SEMANTIC_ENDPOINTING,
                CAP_DELAYED_FLUSH,
                CAP_AUTHORITATIVE_FINAL,
            }
        ),
    )

    def __init__(
        self,
        websocket: Any,
        *,
        delay_seconds: float = KYUTAI_MODEL_DELAY_SECONDS,
        flush_timeout_seconds: float = 3.0,
    ) -> None:
        self._websocket = websocket
        self._delay_seconds = delay_seconds
        self._flush_timeout_seconds = flush_timeout_seconds
        self._events: asyncio.Queue[LiveSttEvent | None] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._pcm_buffer = bytearray()
        self._transcript_parts: list[str] = []
        self._current_model_time = -delay_seconds
        self._steps_seen = 0
        self._pause_ema = _AsymmetricEma()
        self._step_condition = asyncio.Condition()
        self._send_lock = asyncio.Lock()
        self._flush_lock = asyncio.Lock()
        self._cancelled_attempts: set[str] = set()
        self._closed = False

    @classmethod
    async def connect(
        cls,
        base_url: str,
        *,
        api_key: str = "public_token",
        connect_timeout_seconds: float = 5.0,
        delay_seconds: float = KYUTAI_MODEL_DELAY_SECONDS,
        flush_timeout_seconds: float = 3.0,
    ) -> "KyutaiLiveSttSession":
        url = _join_url(base_url, KYUTAI_STT_PATH)
        headers = {"kyutai-api-key": api_key}
        try:
            websocket = await _connect_websocket(
                url,
                headers=headers,
                timeout_seconds=connect_timeout_seconds,
            )
            ready_raw = await asyncio.wait_for(websocket.recv(), timeout=connect_timeout_seconds)
            ready = msgpack.unpackb(ready_raw, raw=False)
            if ready.get("type") == "Error":
                await websocket.close()
                raise KyutaiLiveSttError(str(ready.get("message", "Kyutai service rejected the session")))
            if ready.get("type") != "Ready":
                await websocket.close()
                raise KyutaiLiveSttError(f"Expected Kyutai Ready, received {ready.get('type')!r}")
        except Exception as exc:
            if isinstance(exc, KyutaiLiveSttError):
                raise
            raise KyutaiLiveSttError(f"Could not connect to Kyutai STT at {url}: {exc}") from exc

        session = cls(
            websocket,
            delay_seconds=delay_seconds,
            flush_timeout_seconds=flush_timeout_seconds,
        )
        session._reader_task = asyncio.create_task(session._read_messages())
        return session

    @property
    def transcript(self) -> str:
        return "".join(self._transcript_parts).strip()

    @property
    def endpoint_probability(self) -> float:
        return self._pause_ema.value

    async def send_audio(self, pcm16le: bytes) -> None:
        if self._closed:
            raise KyutaiLiveSttError("Kyutai STT session is closed")
        if len(pcm16le) % 2:
            raise ValueError("PCM16 payload must contain whole samples")
        self._pcm_buffer.extend(pcm16le)
        frame_bytes = KYUTAI_FRAME_SAMPLES * 2
        while len(self._pcm_buffer) >= frame_bytes:
            frame = bytes(self._pcm_buffer[:frame_bytes])
            del self._pcm_buffer[:frame_bytes]
            await self._send_pcm16_frame(frame)

    async def flush(self, attempt_id: str) -> LiveSttFlushResult:
        async with self._flush_lock:
            started = time.perf_counter()
            self._cancelled_attempts.discard(attempt_id)
            await self._events.put(LiveSttEvent(type="flush_started", attempt_id=attempt_id))

            if self._pcm_buffer:
                frame_bytes = KYUTAI_FRAME_SAMPLES * 2
                padded = bytes(self._pcm_buffer) + bytes(frame_bytes - len(self._pcm_buffer))
                self._pcm_buffer.clear()
                await self._send_pcm16_frame(padded)

            target_model_time = self._current_model_time + self._delay_seconds
            zero_frame = bytes(KYUTAI_FRAME_SAMPLES * 2)
            frame_count = math.ceil(self._delay_seconds / KYUTAI_FRAME_SECONDS) + 1
            for _ in range(frame_count):
                await self._send_pcm16_frame(zero_frame)

            async def wait_for_model() -> None:
                async with self._step_condition:
                    await self._step_condition.wait_for(
                        lambda: self._current_model_time > target_model_time or self._closed
                    )

            await asyncio.wait_for(wait_for_model(), timeout=self._flush_timeout_seconds)
            if self._closed:
                raise KyutaiLiveSttError("Kyutai STT session closed while flushing")
            if attempt_id in self._cancelled_attempts:
                raise asyncio.CancelledError(f"Kyutai flush {attempt_id} was cancelled")

            wall_ms = (time.perf_counter() - started) * 1000.0
            model_ms = self._delay_seconds * 1000.0
            result = LiveSttFlushResult(
                attempt_id=attempt_id,
                transcript=self.transcript,
                wall_ms=wall_ms,
                model_ms=model_ms,
                realtime_factor=(model_ms / wall_ms) if wall_ms > 0 else 0.0,
            )
            await self._events.put(
                LiveSttEvent(
                    type="flush_completed",
                    text=result.transcript,
                    attempt_id=attempt_id,
                    fields={
                        "wall_ms": result.wall_ms,
                        "model_ms": result.model_ms,
                        "realtime_factor": result.realtime_factor,
                    },
                )
            )
            return result

    async def cancel_flush(self, attempt_id: str) -> None:
        self._cancelled_attempts.add(attempt_id)
        await self._events.put(LiveSttEvent(type="flush_cancelled", attempt_id=attempt_id))

    async def events(self) -> AsyncIterator[LiveSttEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def close(self) -> None:
        already_closed = self._closed
        self._closed = True
        with suppress(Exception):
            await self._websocket.close()
        if self._reader_task and self._reader_task is not asyncio.current_task():
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
        async with self._step_condition:
            self._step_condition.notify_all()
        if not already_closed:
            await self._events.put(None)

    async def _send_pcm16_frame(self, pcm16le: bytes) -> None:
        floats = pcm16le_to_float32(pcm16le)
        payload = msgpack.packb(
            {"type": "Audio", "pcm": floats},
            use_bin_type=True,
            use_single_float=True,
        )
        async with self._send_lock:
            await self._websocket.send(payload)

    async def _read_messages(self) -> None:
        try:
            async for raw in self._websocket:
                message = msgpack.unpackb(raw, raw=False)
                message_type = str(message.get("type", ""))
                if message_type == "Word":
                    text = str(message.get("text", ""))
                    self._transcript_parts.append(text)
                    start_ms = float(message.get("start_time", 0.0)) * 1000.0
                    await self._events.put(
                        LiveSttEvent(type="word", text=text, start_ms=start_ms)
                    )
                    await self._events.put(
                        LiveSttEvent(type="partial", text=self.transcript)
                    )
                elif message_type == "EndWord":
                    await self._events.put(
                        LiveSttEvent(
                            type="word_end",
                            end_ms=float(message.get("stop_time", 0.0)) * 1000.0,
                        )
                    )
                elif message_type == "Step":
                    self._current_model_time += KYUTAI_FRAME_SECONDS
                    self._steps_seen += 1
                    probabilities = message.get("prs") or []
                    if self._steps_seen > KYUTAI_STARTUP_SUPPRESSION_STEPS and len(probabilities) > 2:
                        probability = self._pause_ema.update(
                            dt=KYUTAI_FRAME_SECONDS,
                            new_value=max(0.0, float(probabilities[2])),
                        )
                        await self._events.put(
                            LiveSttEvent(
                                type="endpoint_score",
                                probability=probability,
                                model_time_ms=self._current_model_time * 1000.0,
                                fields={"signal": "semantic_pause"},
                            )
                        )
                    async with self._step_condition:
                        self._step_condition.notify_all()
                elif message_type == "Marker":
                    await self._events.put(
                        LiveSttEvent(type="marker", fields={"id": message.get("id")})
                    )
                elif message_type == "Error":
                    raise KyutaiLiveSttError(str(message.get("message", "Kyutai STT error")))
                elif message_type != "Ready":
                    await self._events.put(
                        LiveSttEvent(type="unknown", fields={"message_type": message_type})
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closed:
                await self._events.put(
                    LiveSttEvent(type="error", text=str(exc), fields={"retryable": True})
                )
        finally:
            if not self._closed:
                self._closed = True
                async with self._step_condition:
                    self._step_condition.notify_all()
                await self._events.put(None)


class KyutaiLiveSttProvider:
    provider_name = "kyutai"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        breaker: LiveSttCircuitBreaker | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("KYUTAI_STT_URL", "ws://127.0.0.1:8090")
        self.api_key = api_key or os.environ.get("KYUTAI_STT_API_KEY", "public_token")
        self.breaker = breaker or LiveSttCircuitBreaker(
            failure_threshold=int(os.environ.get("KYUTAI_STT_BREAKER_FAILURES", "3")),
            window_attempts=int(os.environ.get("KYUTAI_STT_BREAKER_WINDOW", "5")),
            cooldown_seconds=float(os.environ.get("KYUTAI_STT_BREAKER_COOLDOWN_SECONDS", "60")),
        )
        self._last_ready_at: float | None = None
        self._last_error: str | None = None

    async def create_live_session(self, *, language: str | None = None) -> KyutaiLiveSttSession:
        normalized_language = _normalize_language(language)
        if normalized_language not in SUPPORTED_LANGUAGES:
            raise KyutaiLiveSttError(f"Kyutai live STT does not support language {normalized_language!r}")
        if not self.breaker.allow_new_session():
            snapshot = self.breaker.snapshot()
            raise KyutaiLiveSttError(
                f"Kyutai live STT circuit is open for {snapshot.retry_after_seconds:.1f}s"
            )
        try:
            session = await KyutaiLiveSttSession.connect(
                self.base_url,
                api_key=self.api_key,
                connect_timeout_seconds=float(os.environ.get("KYUTAI_STT_CONNECT_TIMEOUT_SECONDS", "5")),
                flush_timeout_seconds=float(os.environ.get("KYUTAI_STT_FLUSH_TIMEOUT_SECONDS", "3")),
            )
        except Exception as exc:
            self._last_error = str(exc)
            self.breaker.record_failure(transient=not isinstance(exc, ValueError))
            raise
        self._last_ready_at = time.time()
        self._last_error = None
        self.breaker.record_success()
        return session

    async def health(self) -> Mapping[str, Any]:
        snapshot = self.breaker.snapshot()
        return {
            "provider": self.provider_name,
            "base_url": self.base_url,
            "state": snapshot.state.value,
            "failures_in_window": snapshot.failures_in_window,
            "attempts_in_window": snapshot.attempts_in_window,
            "retry_after_seconds": snapshot.retry_after_seconds,
            "last_ready_at": self._last_ready_at,
            "last_error": self._last_error,
            "sample_rate": KYUTAI_SAMPLE_RATE,
            "frame_samples": KYUTAI_FRAME_SAMPLES,
            "supported_languages": sorted(SUPPORTED_LANGUAGES),
        }
