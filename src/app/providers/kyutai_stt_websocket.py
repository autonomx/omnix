"""Omnix-facing WebSocket bridge for Kyutai streaming speech recognition."""
from __future__ import annotations

import asyncio
import base64
import binascii
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.routing import APIWebSocketRoute

from app.providers.kyutai_live_stt import (
    KYUTAI_SAMPLE_RATE,
    KyutaiLiveSttError,
    KyutaiLiveSttProvider,
    KyutaiLiveSttSession,
)

SESSION_TTL_SECONDS = 600.0
MAX_SESSION_STATES = 64
MAX_REPLAY_RESULTS = 64
MAX_OPEN_SEGMENTS = 16
MAX_SEGMENT_AUDIO_MS = 15_000
MAX_SEGMENT_BYTES = int(KYUTAI_SAMPLE_RATE * 2 * MAX_SEGMENT_AUDIO_MS / 1_000)
MAX_AUDIO_FRAME_MS = 2_000
MAX_AUDIO_FRAME_BYTES = int(KYUTAI_SAMPLE_RATE * 2 * MAX_AUDIO_FRAME_MS / 1_000)
MAX_QUEUED_ACTIONS = 512


@dataclass
class KyutaiSegment:
    segment_id: str
    sequence: int
    capture_start_sample: int
    primary_start_sample: int
    capture_epoch: str
    accepted_through_sample: int
    transcript_prefix: str | None = None
    finalize_request_id: str = ""
    end_sample: int = 0
    finalize_started_at: float = 0.0
    audio_bytes: int = 0
    finalized: bool = False


@dataclass(frozen=True)
class KyutaiAction:
    type: Literal["audio", "finalize"]
    segment_id: str
    payload: bytes = b""


@dataclass
class KyutaiBrowserSessionState:
    session_id: str
    results: dict[int, dict[str, Any]] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.monotonic)

    def remember_result(self, payload: dict[str, Any]) -> None:
        self.results[int(payload["sequence"])] = payload
        while len(self.results) > MAX_REPLAY_RESULTS:
            self.results.pop(min(self.results))
        self.last_seen = time.monotonic()


_BROWSER_SESSION_STATES: dict[str, KyutaiBrowserSessionState] = {}


def _remove_existing_route(app: FastAPI) -> None:
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if not (isinstance(route, APIWebSocketRoute) and route.path == "/ws/transcribe")
    ]


def _prune_sessions() -> None:
    now = time.monotonic()
    for session_id in [
        session_id
        for session_id, state in _BROWSER_SESSION_STATES.items()
        if now - state.last_seen > SESSION_TTL_SECONDS
    ]:
        _BROWSER_SESSION_STATES.pop(session_id, None)
    if len(_BROWSER_SESSION_STATES) <= MAX_SESSION_STATES:
        return
    oldest = sorted(_BROWSER_SESSION_STATES.values(), key=lambda state: state.last_seen)
    for state in oldest[: len(_BROWSER_SESSION_STATES) - MAX_SESSION_STATES]:
        _BROWSER_SESSION_STATES.pop(state.session_id, None)


def _browser_state(session_id: str) -> KyutaiBrowserSessionState:
    _prune_sessions()
    state = _BROWSER_SESSION_STATES.get(session_id)
    if state is None:
        state = KyutaiBrowserSessionState(session_id=session_id)
        _BROWSER_SESSION_STATES[session_id] = state
    state.last_seen = time.monotonic()
    return state


def _field(data: dict[str, Any], camel: str, snake: str, default: Any = None) -> Any:
    return data.get(camel, data.get(snake, default))


def _segment_text(session: KyutaiLiveSttSession, segment: KyutaiSegment) -> str:
    transcript = session.transcript
    prefix = segment.transcript_prefix or ""
    if prefix and transcript.startswith(prefix):
        return transcript[len(prefix) :].strip()
    return transcript.strip()


async def _safe_send(websocket: WebSocket, lock: asyncio.Lock, payload: dict[str, Any]) -> bool:
    try:
        async with lock:
            await websocket.send_json(payload)
        return True
    except Exception:  # noqa: BLE001 - client disconnects surface through framework-specific exceptions
        return False


def _decode_audio(encoded_audio: str) -> bytes:
    if len(encoded_audio) > ((MAX_AUDIO_FRAME_BYTES + 2) // 3) * 4 + 8:
        raise ValueError("audio_frame_limit")
    try:
        payload = base64.b64decode(encoded_audio, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio_frame_base64") from exc
    if len(payload) % 2:
        raise ValueError("audio_frame_partial_sample")
    if len(payload) > MAX_AUDIO_FRAME_BYTES:
        raise ValueError("audio_frame_limit")
    return payload


def install_kyutai_stt_websocket(
    app: FastAPI,
    *,
    provider: KyutaiLiveSttProvider | None = None,
) -> KyutaiLiveSttProvider:
    """Install an Omnix-compatible STT route backed by Kyutai moshi-server."""

    _remove_existing_route(app)
    live_provider = provider or KyutaiLiveSttProvider()

    @app.websocket("/ws/transcribe")
    async def websocket_transcribe(websocket: WebSocket) -> None:
        await websocket.accept()
        send_lock = asyncio.Lock()
        connection_id = uuid.uuid4().hex
        language = websocket.query_params.get("language") or os.environ.get("OMNIX_LIVE_STT_LANGUAGE", "en")
        try:
            session = await live_provider.create_live_session(language=language)
        except (KyutaiLiveSttError, ValueError, OSError) as exc:
            await _safe_send(
                websocket,
                send_lock,
                {
                    "type": "error",
                    "errorCode": "kyutai_session_unavailable",
                    "retryable": getattr(exc, "retryable", True),
                    "error": str(exc),
                },
            )
            await websocket.close(code=1013)
            return

        await _safe_send(
            websocket,
            send_lock,
            session.negotiation.ready_payload(
                connection_id=connection_id,
                maxSegmentAudioMs=MAX_SEGMENT_AUDIO_MS,
                language=language,
            ),
        )

        active_session_id = f"connection-{connection_id}"
        segments: dict[str, KyutaiSegment] = {}
        action_queue: asyncio.Queue[KyutaiAction | None] = asyncio.Queue(MAX_QUEUED_ACTIONS)
        current_segment_id: str | None = None
        closed = False
        endpoint_candidate_threshold = float(os.environ.get("KYUTAI_ENDPOINT_CANDIDATE_THRESHOLD", "0.75"))

        async def forward_events() -> None:
            nonlocal closed
            try:
                async for event in session.events():
                    segment = segments.get(current_segment_id or "")
                    if event.type == "partial" and segment is not None:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "partial",
                                "provider": "kyutai",
                                "segmentId": segment.segment_id,
                                "sequence": segment.sequence,
                                "text": _segment_text(session, segment),
                            },
                        )
                    elif event.type == "word" and segment is not None:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "word",
                                "provider": "kyutai",
                                "segmentId": segment.segment_id,
                                "sequence": segment.sequence,
                                "text": event.text,
                                "startMs": event.start_ms,
                                "endMs": event.end_ms,
                            },
                        )
                    elif event.type == "endpoint_score":
                        payload = {
                            "type": "endpoint_score",
                            "provider": "kyutai",
                            "probability": event.probability,
                            "modelTimeMs": event.model_time_ms,
                            "signal": "semantic_pause",
                        }
                        if segment is not None:
                            payload.update(
                                {
                                    "segmentId": segment.segment_id,
                                    "sequence": segment.sequence,
                                }
                            )
                        await _safe_send(websocket, send_lock, payload)
                        if (
                            segment is not None
                            and event.probability is not None
                            and event.probability >= endpoint_candidate_threshold
                            and _segment_text(session, segment)
                        ):
                            await _safe_send(
                                websocket,
                                send_lock,
                                {
                                    "type": "endpoint_candidate",
                                    "provider": "kyutai",
                                    "segmentId": segment.segment_id,
                                    "sequence": segment.sequence,
                                    "probability": event.probability,
                                    "modelTimeMs": event.model_time_ms,
                                },
                            )
                    elif event.type in {"flush_started", "flush_completed", "flush_cancelled"}:
                        payload = {
                            "type": event.type,
                            "provider": "kyutai",
                            "attemptId": event.attempt_id,
                        }
                        if event.fields:
                            payload.update(dict(event.fields))
                        await _safe_send(websocket, send_lock, payload)
                    elif event.type == "error":
                        retryable = bool((event.fields or {}).get("retryable", True))
                        live_provider.record_runtime_failure(event.text, retryable=retryable)
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "error",
                                "provider": "kyutai",
                                "errorCode": "kyutai_session_failed",
                                "retryable": retryable,
                                "error": event.text,
                            },
                        )
            finally:
                closed = True

        async def process_actions() -> None:
            nonlocal current_segment_id, closed
            while not closed:
                action = await action_queue.get()
                if action is None:
                    return
                segment = segments.get(action.segment_id)
                if segment is None:
                    continue
                if action.type == "audio":
                    if segment.transcript_prefix is None:
                        segment.transcript_prefix = session.transcript
                    current_segment_id = segment.segment_id
                    try:
                        await session.send_audio(action.payload)
                    except (KyutaiLiveSttError, OSError, ValueError) as exc:
                        live_provider.record_runtime_failure(
                            str(exc),
                            retryable=getattr(exc, "retryable", True),
                        )
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment.segment_id,
                                "sequence": segment.sequence,
                                "retryable": getattr(exc, "retryable", True),
                                "errorCode": "kyutai_audio_failed",
                                "error": str(exc),
                            },
                        )
                        segments.pop(segment.segment_id, None)
                    continue

                current_segment_id = segment.segment_id
                try:
                    flush = await session.flush(segment.finalize_request_id)
                except asyncio.CancelledError:
                    await _safe_send(
                        websocket,
                        send_lock,
                        {
                            "type": "segment_error",
                            "segmentId": segment.segment_id,
                            "sequence": segment.sequence,
                            "retryable": True,
                            "errorCode": "flush_cancelled",
                            "error": "flush_cancelled",
                        },
                    )
                    segments.pop(segment.segment_id, None)
                    current_segment_id = None
                    continue
                except (KyutaiLiveSttError, TimeoutError, OSError, ValueError) as exc:
                    retryable = getattr(exc, "retryable", True)
                    live_provider.record_runtime_failure(str(exc), retryable=retryable)
                    await _safe_send(
                        websocket,
                        send_lock,
                        {
                            "type": "segment_error",
                            "segmentId": segment.segment_id,
                            "sequence": segment.sequence,
                            "retryable": retryable,
                            "errorCode": "kyutai_flush_failed",
                            "error": str(exc),
                        },
                    )
                    segments.pop(segment.segment_id, None)
                    current_segment_id = None
                    continue

                state = _browser_state(active_session_id)
                payload = {
                    "type": "result_available",
                    "sessionId": state.session_id,
                    "captureEpoch": segment.capture_epoch,
                    "segmentId": segment.segment_id,
                    "sequence": segment.sequence,
                    "resultId": uuid.uuid4().hex,
                    "finalizeRequestId": segment.finalize_request_id,
                    "startSample": segment.primary_start_sample,
                    "endSample": segment.end_sample or segment.accepted_through_sample,
                    "text": _segment_text(session, segment),
                    "acceptedThroughSample": segment.accepted_through_sample,
                    "provider": "kyutai",
                    "providerMetrics": {
                        "flushWallMs": round(flush.wall_ms, 3),
                        "flushModelMs": round(flush.model_ms, 3),
                        "flushRealtimeFactor": round(flush.realtime_factor, 3),
                        "totalFinalizeMs": round(
                            (time.perf_counter() - segment.finalize_started_at) * 1000.0,
                            3,
                        ),
                    },
                }
                state.remember_result(payload)
                await _safe_send(websocket, send_lock, payload)
                segments.pop(segment.segment_id, None)
                current_segment_id = None

        event_task = asyncio.create_task(forward_events())
        action_task = asyncio.create_task(process_actions())

        try:
            while not closed:
                data = await websocket.receive_json()
                message_type = str(data.get("type", ""))
                if message_type == "hello":
                    requested_rate = int(_field(data, "sampleRate", "sample_rate", KYUTAI_SAMPLE_RATE))
                    if requested_rate != KYUTAI_SAMPLE_RATE:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "error",
                                "errorCode": "sample_rate_mismatch",
                                "retryable": False,
                                "error": f"Kyutai requires {KYUTAI_SAMPLE_RATE} Hz PCM",
                            },
                        )
                        await websocket.close(code=1003)
                        return
                    active_session_id = str(_field(data, "sessionId", "session_id", active_session_id))[:120]
                    state = _browser_state(active_session_id)
                    await _safe_send(
                        websocket,
                        send_lock,
                        {
                            "type": "session_ready",
                            "sessionId": active_session_id,
                            "provider": "kyutai",
                            "results": [state.results[key] for key in sorted(state.results)],
                        },
                    )
                    continue

                state = _browser_state(
                    str(_field(data, "sessionId", "session_id", active_session_id))[:120]
                )

                if message_type == "audio":
                    encoded_audio = str(data.get("data", ""))
                    if not encoded_audio:
                        continue
                    sample_rate = int(_field(data, "sampleRate", "sample_rate", KYUTAI_SAMPLE_RATE))
                    segment_id = str(_field(data, "segmentId", "segment_id", f"segment-{len(segments)}"))[:120]
                    sequence = int(data.get("sequence", 0))
                    if sample_rate != KYUTAI_SAMPLE_RATE:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "retryable": False,
                                "errorCode": "sample_rate_mismatch",
                                "error": f"Kyutai requires {KYUTAI_SAMPLE_RATE} Hz PCM",
                            },
                        )
                        continue
                    try:
                        payload = _decode_audio(encoded_audio)
                    except ValueError as exc:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "retryable": False,
                                "errorCode": str(exc),
                                "error": str(exc),
                            },
                        )
                        continue
                    capture_start = int(_field(data, "captureStartSample", "capture_start_sample", 0))
                    primary_start = int(_field(data, "primaryStartSample", "primary_start_sample", capture_start))
                    sample_start = int(_field(data, "sampleStart", "sample_start", capture_start))
                    capture_epoch = str(_field(data, "captureEpoch", "capture_epoch", ""))[:160]
                    if segment_id not in segments:
                        if len(segments) >= MAX_OPEN_SEGMENTS:
                            await _safe_send(
                                websocket,
                                send_lock,
                                {
                                    "type": "segment_error",
                                    "segmentId": segment_id,
                                    "sequence": sequence,
                                    "retryable": True,
                                    "errorCode": "open_segment_limit",
                                    "error": "open_segment_limit",
                                },
                            )
                            continue
                        segments[segment_id] = KyutaiSegment(
                            segment_id=segment_id,
                            sequence=sequence,
                            capture_start_sample=capture_start,
                            primary_start_sample=primary_start,
                            capture_epoch=capture_epoch,
                            accepted_through_sample=capture_start,
                        )
                    segment = segments[segment_id]
                    if (
                        segment.sequence != sequence
                        or segment.capture_epoch != capture_epoch
                        or segment.capture_start_sample != capture_start
                        or segment.primary_start_sample != primary_start
                    ):
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "retryable": False,
                                "errorCode": "segment_identity_mismatch",
                                "error": "segment_identity_mismatch",
                            },
                        )
                        segments.pop(segment_id, None)
                        continue
                    frame_end = sample_start + len(payload) // 2
                    if frame_end <= segment.accepted_through_sample:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "audio_buffered",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "acceptedThroughSample": segment.accepted_through_sample,
                            },
                        )
                        continue
                    duplicate_samples = max(0, segment.accepted_through_sample - sample_start)
                    if duplicate_samples:
                        payload = payload[duplicate_samples * 2 :]
                        sample_start += duplicate_samples
                    if sample_start != segment.accepted_through_sample:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "retryable": False,
                                "errorCode": "audio_frame_gap",
                                "error": "audio_frame_gap",
                            },
                        )
                        segments.pop(segment_id, None)
                        continue
                    if segment.audio_bytes + len(payload) > MAX_SEGMENT_BYTES:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "retryable": False,
                                "errorCode": "segment_audio_limit",
                                "error": "segment_audio_limit",
                            },
                        )
                        segments.pop(segment_id, None)
                        continue
                    try:
                        action_queue.put_nowait(KyutaiAction("audio", segment_id, payload))
                    except asyncio.QueueFull:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment_id,
                                "sequence": sequence,
                                "retryable": True,
                                "errorCode": "provider_action_queue_full",
                                "error": "provider_action_queue_full",
                            },
                        )
                        continue
                    segment.accepted_through_sample += len(payload) // 2
                    segment.audio_bytes += len(payload)
                    await _safe_send(
                        websocket,
                        send_lock,
                        {
                            "type": "audio_buffered",
                            "segmentId": segment_id,
                            "sequence": sequence,
                            "acceptedThroughSample": segment.accepted_through_sample,
                        },
                    )
                    continue

                if message_type in {"final", "finalize"}:
                    segment_id = str(_field(data, "segmentId", "segment_id", current_segment_id or ""))[:120]
                    sequence = int(data.get("sequence", 0))
                    segment = segments.get(segment_id)
                    if segment is None:
                        cached = state.results.get(sequence)
                        if cached is not None:
                            await _safe_send(websocket, send_lock, cached)
                        else:
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
                    finalize_request_id = str(
                        _field(data, "finalizeRequestId", "finalize_request_id", uuid.uuid4().hex)
                    )[:160]
                    if segment.finalized:
                        if finalize_request_id == segment.finalize_request_id:
                            await _safe_send(
                                websocket,
                                send_lock,
                                {
                                    "type": "finalize_queued",
                                    "segmentId": segment.segment_id,
                                    "sequence": segment.sequence,
                                    "queuedSegments": action_queue.qsize(),
                                },
                            )
                        continue
                    end_sample = int(_field(data, "endSample", "end_sample", segment.accepted_through_sample))
                    if end_sample > segment.accepted_through_sample or end_sample < segment.primary_start_sample:
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment.segment_id,
                                "sequence": segment.sequence,
                                "retryable": False,
                                "errorCode": "finalize_sample_range",
                                "error": "finalize_sample_range",
                            },
                        )
                        segments.pop(segment.segment_id, None)
                        continue
                    segment.finalize_request_id = finalize_request_id
                    segment.end_sample = end_sample
                    segment.finalize_started_at = time.perf_counter()
                    segment.finalized = True
                    try:
                        action_queue.put_nowait(KyutaiAction("finalize", segment.segment_id))
                    except asyncio.QueueFull:
                        segment.finalized = False
                        await _safe_send(
                            websocket,
                            send_lock,
                            {
                                "type": "segment_error",
                                "segmentId": segment.segment_id,
                                "sequence": segment.sequence,
                                "retryable": True,
                                "errorCode": "provider_action_queue_full",
                                "error": "provider_action_queue_full",
                            },
                        )
                        continue
                    await _safe_send(
                        websocket,
                        send_lock,
                        {
                            "type": "finalize_queued",
                            "segmentId": segment.segment_id,
                            "sequence": segment.sequence,
                            "queuedSegments": action_queue.qsize(),
                        },
                    )
                    continue

                if message_type == "cancel_flush":
                    attempt_id = str(_field(data, "attemptId", "attempt_id", ""))[:160]
                    if attempt_id:
                        await session.cancel_flush(attempt_id)
                    continue
        except WebSocketDisconnect:
            return
        except KyutaiLiveSttError as exc:
            live_provider.record_runtime_failure(str(exc), retryable=exc.retryable)
            await _safe_send(
                websocket,
                send_lock,
                {
                    "type": "error",
                    "errorCode": "kyutai_session_failed",
                    "retryable": exc.retryable,
                    "error": str(exc),
                },
            )
        finally:
            closed = True
            try:
                action_queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
            for task in (event_task, action_task):
                task.cancel()
            for task in (event_task, action_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await session.close()

    return live_provider
