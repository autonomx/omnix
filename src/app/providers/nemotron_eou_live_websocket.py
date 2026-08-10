"""Segmented WebSocket transport for Nemotron ASR + Parakeet Realtime EOU."""
from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.providers.live_stt_contracts import (
    CAP_AUTHORITATIVE_EOU,
    CAP_AUTHORITATIVE_FINAL,
    CAP_PARTIAL_TRANSCRIPTS,
    CAP_RESULT_REPLAY,
    CAP_SEGMENTED_AUDIO,
    LiveSttNegotiation,
)
from app.providers.nemotron_eou_streaming import SAMPLE_RATE, NemotronEouModelManager, model_manager

SEGMENTED_PROTOCOL = "segmented-v1"
PROVIDER_NAME = "nemotron_parakeet_eou"
FRAME_SAMPLES = 320
MAX_SEGMENT_AUDIO_MS = 15_000
MAX_SEGMENT_BYTES = int(SAMPLE_RATE * 2 * MAX_SEGMENT_AUDIO_MS / 1_000)
MAX_REPLAY_RESULTS = 64
SESSION_TTL_SECONDS = 600.0

HYBRID_NEGOTIATION = LiveSttNegotiation(
    provider=PROVIDER_NAME,
    protocol=SEGMENTED_PROTOCOL,
    sample_rate=SAMPLE_RATE,
    frame_samples=FRAME_SAMPLES,
    capabilities=frozenset(
        {
            CAP_SEGMENTED_AUDIO,
            CAP_AUTHORITATIVE_FINAL,
            CAP_RESULT_REPLAY,
            CAP_PARTIAL_TRANSCRIPTS,
            CAP_AUTHORITATIVE_EOU,
        }
    ),
)


def _metric(event: str, **fields: Any) -> None:
    print(
        "[STT_METRIC] "
        + json.dumps(
            {
                "event": event,
                "source": "nemotron-parakeet-eou-runtime",
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                **fields,
            },
            sort_keys=True,
            default=str,
        ),
        flush=True,
    )


def _field(data: dict[str, Any], camel: str, snake: str, default: Any = None) -> Any:
    return data.get(camel, data.get(snake, default))


def primary_pcm_slice(sample_start: int, primary_start_sample: int, payload: bytes) -> bytes:
    """Remove the browser's cross-segment overlap before model inference."""
    if len(payload) % 2:
        raise ValueError("audio_frame_partial_sample")
    skip_samples = max(0, primary_start_sample - sample_start)
    if skip_samples >= len(payload) // 2:
        return b""
    return payload[skip_samples * 2 :]


@dataclass
class HybridSegment:
    segment_id: str
    sequence: int
    capture_start_sample: int
    primary_start_sample: int
    capture_epoch: str = ""
    accepted_through_sample: int = 0
    primary_audio: bytearray = field(default_factory=bytearray)
    stream_pending: bytearray = field(default_factory=bytearray)
    stream_task: asyncio.Task[None] | None = None
    last_partial: str = ""
    eou_emitted: bool = False
    finalize_request_id: str = ""
    end_sample: int = 0
    finalized: bool = False

    def append(self, sample_start: int, payload: bytes) -> int:
        if len(payload) % 2:
            raise ValueError("audio_frame_partial_sample")
        if self.accepted_through_sample == 0:
            self.accepted_through_sample = self.capture_start_sample
        sample_count = len(payload) // 2
        frame_end = sample_start + sample_count
        if frame_end <= self.accepted_through_sample:
            return self.accepted_through_sample
        if sample_start < self.accepted_through_sample:
            duplicate_samples = self.accepted_through_sample - sample_start
            payload = payload[duplicate_samples * 2 :]
            sample_start = self.accepted_through_sample
        if sample_start != self.accepted_through_sample:
            raise ValueError("audio_frame_gap")
        if len(self.primary_audio) + len(payload) > MAX_SEGMENT_BYTES + (SAMPLE_RATE * 2):
            raise ValueError("segment_audio_limit")
        primary = primary_pcm_slice(sample_start, self.primary_start_sample, payload)
        if primary:
            if len(self.primary_audio) + len(primary) > MAX_SEGMENT_BYTES:
                raise ValueError("segment_audio_limit")
            self.primary_audio.extend(primary)
            self.stream_pending.extend(primary)
        self.accepted_through_sample = sample_start + len(payload) // 2
        return self.accepted_through_sample


@dataclass
class HybridSessionState:
    session_id: str
    segments: dict[str, HybridSegment] = field(default_factory=dict)
    results: dict[int, dict[str, Any]] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.monotonic)

    def remember_result(self, payload: dict[str, Any]) -> None:
        self.results[int(payload["sequence"])] = payload
        while len(self.results) > MAX_REPLAY_RESULTS:
            self.results.pop(min(self.results))
        self.last_seen = time.monotonic()


_SESSION_STATES: dict[str, HybridSessionState] = {}


def _session_state(session_id: str) -> HybridSessionState:
    now = time.monotonic()
    stale = [key for key, value in _SESSION_STATES.items() if now - value.last_seen > SESSION_TTL_SECONDS]
    for key in stale:
        _SESSION_STATES.pop(key, None)
    state = _SESSION_STATES.get(session_id)
    if state is None:
        state = HybridSessionState(session_id=session_id)
        _SESSION_STATES[session_id] = state
    state.last_seen = now
    return state


async def _safe_send(websocket: WebSocket, lock: asyncio.Lock, payload: dict[str, Any]) -> bool:
    try:
        async with lock:
            await websocket.send_json(payload)
        return True
    except Exception:
        return False


async def _drain_stream_audio(
    segment: HybridSegment,
    manager: NemotronEouModelManager,
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    *,
    flush: bool = False,
) -> None:
    chunk_bytes = manager.feed_chunk_samples * 2
    while len(segment.stream_pending) >= chunk_bytes or (flush and segment.stream_pending):
        take = chunk_bytes if len(segment.stream_pending) >= chunk_bytes else len(segment.stream_pending)
        payload = bytes(segment.stream_pending[:take])
        del segment.stream_pending[:take]
        update = await asyncio.to_thread(manager.feed, segment.segment_id, payload)
        model_time_ms = round(
            len(segment.primary_audio) / 2 / SAMPLE_RATE * 1000.0,
            3,
        )
        if update.transcript_changed and update.transcript != segment.last_partial:
            segment.last_partial = update.transcript
            await _safe_send(
                websocket,
                send_lock,
                {
                    "type": "partial",
                    "provider": PROVIDER_NAME,
                    "segmentId": segment.segment_id,
                    "sequence": segment.sequence,
                    "text": update.transcript,
                },
            )
            _metric(
                "stt_streaming_partial",
                segment_sequence=segment.sequence,
                transcript_chars=len(update.transcript),
                nemotron_ms=round(update.nemotron_ms, 3),
                eou_ms=round(update.eou_ms, 3),
                model_time_ms=model_time_ms,
            )
        if update.eou and not segment.eou_emitted:
            segment.eou_emitted = True
            endpoint = {
                "provider": PROVIDER_NAME,
                "segmentId": segment.segment_id,
                "sequence": segment.sequence,
                "probability": 1.0,
                "modelTimeMs": model_time_ms,
                "signal": "eou",
            }
            await _safe_send(websocket, send_lock, {"type": "endpoint_score", **endpoint})
            await _safe_send(websocket, send_lock, {"type": "endpoint_candidate", **endpoint})
            _metric(
                "stt_eou_emitted",
                segment_sequence=segment.sequence,
                transcript_chars=len(segment.last_partial),
                model_time_ms=model_time_ms,
                nemotron_ms=round(update.nemotron_ms, 3),
                eou_ms=round(update.eou_ms, 3),
            )


def _schedule_stream_drain(
    segment: HybridSegment,
    manager: NemotronEouModelManager,
    websocket: WebSocket,
    send_lock: asyncio.Lock,
) -> None:
    chunk_bytes = manager.feed_chunk_samples * 2
    if len(segment.stream_pending) < chunk_bytes:
        return
    if segment.stream_task is not None and not segment.stream_task.done():
        return

    async def run() -> None:
        try:
            await _drain_stream_audio(segment, manager, websocket, send_lock)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _metric(
                "stt_streaming_feed_failed",
                segment_sequence=segment.sequence,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            await _safe_send(
                websocket,
                send_lock,
                {
                    "type": "segment_error",
                    "segmentId": segment.segment_id,
                    "sequence": segment.sequence,
                    "retryable": False,
                    "errorCode": type(exc).__name__,
                    "error": str(exc),
                },
            )
        finally:
            segment.stream_task = None
            if len(segment.stream_pending) >= chunk_bytes and not segment.finalized:
                _schedule_stream_drain(segment, manager, websocket, send_lock)

    segment.stream_task = asyncio.create_task(run())


async def _flush_stream(
    segment: HybridSegment,
    manager: NemotronEouModelManager,
    websocket: WebSocket,
    send_lock: asyncio.Lock,
) -> None:
    existing = segment.stream_task
    if existing is not None:
        await existing
    if segment.stream_pending:
        await _drain_stream_audio(segment, manager, websocket, send_lock, flush=True)


def install_nemotron_eou_websocket(app: Any, manager: NemotronEouModelManager = model_manager) -> None:
    @app.websocket("/ws/transcribe")
    async def websocket_transcribe(websocket: WebSocket) -> None:
        await websocket.accept()
        send_lock = asyncio.Lock()
        connection_id = uuid.uuid4().hex
        active_session_id = f"connection-{connection_id}"
        await _safe_send(
            websocket,
            send_lock,
            HYBRID_NEGOTIATION.ready_payload(
                connection_id=connection_id,
                maxSegmentAudioMs=MAX_SEGMENT_AUDIO_MS,
                language="en-US",
            ),
        )
        try:
            while True:
                data = await websocket.receive_json()
                message_type = str(data.get("type", ""))
                if message_type == "hello":
                    active_session_id = str(_field(data, "sessionId", "session_id", active_session_id))[:120]
                    state = _session_state(active_session_id)
                    await _safe_send(
                        websocket,
                        send_lock,
                        {
                            "type": "session_ready",
                            "sessionId": state.session_id,
                            "provider": PROVIDER_NAME,
                            "results": [state.results[key] for key in sorted(state.results)],
                        },
                    )
                    continue
                state = _session_state(str(_field(data, "sessionId", "session_id", active_session_id))[:120])
                if message_type == "audio":
                    segment_id = str(_field(data, "segmentId", "segment_id", ""))[:120]
                    if not segment_id:
                        await _safe_send(websocket, send_lock, {"type": "error", "error": "segment_id_required"})
                        continue
                    sequence = int(data.get("sequence", 0))
                    sample_rate = int(_field(data, "sampleRate", "sample_rate", SAMPLE_RATE))
                    if sample_rate != SAMPLE_RATE:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "retryable": False,
                                "errorCode": "sample_rate_mismatch",
                                "error": f"Hybrid STT requires {SAMPLE_RATE} Hz PCM",
                            },
                        )
                        continue
                    capture_start = int(_field(data, "captureStartSample", "capture_start_sample", 0))
                    primary_start = int(_field(data, "primaryStartSample", "primary_start_sample", capture_start))
                    sample_start = int(_field(data, "sampleStart", "sample_start", capture_start))
                    segment = state.segments.get(segment_id)
                    if segment is None:
                        segment = HybridSegment(
                            segment_id=segment_id,
                            sequence=sequence,
                            capture_start_sample=capture_start,
                            primary_start_sample=primary_start,
                            capture_epoch=str(_field(data, "captureEpoch", "capture_epoch", ""))[:160],
                        )
                        state.segments[segment_id] = segment
                    try:
                        payload = base64.b64decode(str(data.get("data", "")), validate=True)
                        accepted = segment.append(sample_start, payload)
                    except Exception as exc:
                        manager.release(segment_id)
                        state.segments.pop(segment_id, None)
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "retryable": False,
                                "errorCode": type(exc).__name__,
                                "error": str(exc),
                            },
                        )
                        continue
                    await _safe_send(
                        websocket,
                        send_lock,
                        {
                            "type": "audio_buffered",
                            "segmentId": segment_id,
                            "sequence": sequence,
                            "acceptedThroughSample": accepted,
                        },
                    )
                    _schedule_stream_drain(segment, manager, websocket, send_lock)
                    continue
                if message_type in {"final", "finalize"}:
                    segment_id = str(_field(data, "segmentId", "segment_id", ""))[:120]
                    sequence = int(data.get("sequence", 0))
                    cached = state.results.get(sequence)
                    if cached is not None:
                        await _safe_send(websocket, send_lock, cached)
                        continue
                    segment = state.segments.get(segment_id)
                    if segment is None:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "retryable": True,
                                "errorCode": "segment_missing",
                                "error": "segment_missing",
                            },
                        )
                        continue
                    if segment.finalized:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {"type": "finalize_queued", "segmentId": segment_id, "sequence": sequence},
                        )
                        continue
                    segment.finalized = True
                    segment.capture_epoch = str(
                        _field(data, "captureEpoch", "capture_epoch", segment.capture_epoch)
                    )[:160]
                    segment.finalize_request_id = str(
                        _field(data, "finalizeRequestId", "finalize_request_id", "")
                    )[:160]
                    segment.end_sample = int(
                        _field(data, "endSample", "end_sample", segment.accepted_through_sample)
                    )
                    final_started = time.perf_counter()
                    await _safe_send(
                        websocket,
                        send_lock,
                        {"type": "finalize_queued", "segmentId": segment_id, "sequence": sequence, "queuedSegments": 0},
                    )
                    try:
                        await _flush_stream(segment, manager, websocket, send_lock)
                        text, provider_metrics = await asyncio.to_thread(
                            manager.finalize,
                            segment_id,
                            bytes(segment.primary_audio),
                        )
                        finalize_ms = (time.perf_counter() - final_started) * 1000.0
                        provider_metrics = {
                            **provider_metrics,
                            "finalize_ms": round(finalize_ms, 3),
                            "eou_triggered": 1.0 if segment.eou_emitted else 0.0,
                        }
                        result = {
                            "type": "result_available",
                            "provider": PROVIDER_NAME,
                            "sessionId": state.session_id,
                            "captureEpoch": segment.capture_epoch,
                            "segmentId": segment.segment_id,
                            "sequence": segment.sequence,
                            "resultId": uuid.uuid4().hex,
                            "finalizeRequestId": segment.finalize_request_id,
                            "startSample": segment.primary_start_sample,
                            "endSample": segment.end_sample or segment.accepted_through_sample,
                            "text": text,
                            "acceptedThroughSample": segment.accepted_through_sample,
                            "providerMetrics": provider_metrics,
                        }
                        state.remember_result(result)
                        await _safe_send(websocket, send_lock, result)
                        _metric(
                            "stt_hybrid_final_completed",
                            segment_sequence=segment.sequence,
                            transcript_chars=len(text),
                            finalize_ms=round(finalize_ms, 3),
                            eou_triggered=segment.eou_emitted,
                            streaming_final=provider_metrics.get("streaming_final", 0.0),
                            offline_fallback=provider_metrics.get("offline_fallback", 0.0),
                        )
                    except Exception as exc:
                        _metric(
                            "stt_hybrid_final_failed",
                            segment_sequence=segment.sequence,
                            error_type=type(exc).__name__,
                            error=str(exc),
                        )
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment.segment_id,
                                "sequence": segment.sequence,
                                "retryable": False,
                                "errorCode": type(exc).__name__,
                                "error": str(exc),
                            },
                        )
                    finally:
                        manager.release(segment_id)
                        state.segments.pop(segment_id, None)
                    continue
        except WebSocketDisconnect:
            return
        except Exception as exc:
            _metric("stt_hybrid_websocket_failed", error_type=type(exc).__name__, error=str(exc))
            await _safe_send(websocket, send_lock, {"type": "error", "error": str(exc)})
