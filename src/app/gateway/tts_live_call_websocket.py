"""Turn-scoped persistent PCM websocket transport for live voice."""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.live_speech.performance_contract import apply_performance_plan_to_provider
from app.shared import get_tts_provider, remove_emojis

from .tts_stream_diagnostics import (
    begin_stream,
    diagnostics_log_path,
    end_stream,
    normalize_stream_id,
    stream_log,
)
from .tts_streaming import (
    DEFAULT_SAMPLE_RATE,
    TtsStreamRequest,
    _audio_chunk_to_pcm16_bytes,
    _stream_pcm16_blocks,
)

_ROUTE_SENTINEL = "_omnix_tts_live_call_ws_registered"
_HOOK_SENTINEL = "_omnix_tts_live_call_ws_hook_installed"
TTS_LIVE_CALL_WEBSOCKET_PATH = "/api/tts/live-call/websocket"
TTS_PCM_FRAME_SAMPLES = 2_400  # 100 ms at 24 kHz.
FIRST_FRAME_HANDOFF_TIMEOUT_SECONDS = 0.050


@dataclass(frozen=True)
class FrameMessage:
    message_type: str
    pcm_bytes: bytes | None
    sample_rate: int
    metadata: dict[str, Any]
    queued_at: float | None = None
    sent_ack: threading.Event | None = None


@dataclass
class ConnectionState:
    stop_event: threading.Event
    requests: asyncio.Queue[dict[str, Any] | None]
    active_frames: asyncio.Queue[FrameMessage] | None = None


def _connection_details(websocket: WebSocket) -> dict[str, Any]:
    client = websocket.client
    return {
        "client_host": client.host if client else None,
        "client_port": client.port if client else None,
        "origin": websocket.headers.get("origin"),
        "user_agent": websocket.headers.get("user-agent"),
        "websocket_path": websocket.url.path,
        "persistent_connection": True,
    }


def _phrase_index(payload: dict[str, Any]) -> int | None:
    value = payload.get("phrase_index")
    return value if isinstance(value, int) and value >= 0 else None


def _stop_connection(state: ConnectionState, reason: str) -> None:
    if state.stop_event.is_set():
        return
    state.stop_event.set()
    if state.active_frames is not None:
        state.active_frames.put_nowait(
            FrameMessage(
                "client_disconnect",
                None,
                DEFAULT_SAMPLE_RATE,
                {"reason": reason},
            )
        )
    state.requests.put_nowait(None)


async def _receive_messages(websocket: WebSocket, state: ConnectionState) -> None:
    """Receive requests and cancellation while phrase audio is being produced."""
    try:
        while not state.stop_event.is_set():
            raw_message = await websocket.receive_text()
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                await websocket.send_json(
                    {"type": "error", "message": f"Invalid JSON: {exc}"}
                )
                continue
            if not isinstance(payload, dict):
                await websocket.send_json(
                    {"type": "error", "message": "TTS message must be an object."}
                )
                continue
            message_type = payload.get("type")
            if message_type == "close":
                _stop_connection(state, str(payload.get("reason") or "client-close"))
                return
            if message_type == "diagnostic":
                stream_id = normalize_stream_id(payload.get("stream_id"))
                event = str(payload.get("event") or "diagnostic")[:120]
                details = payload.get("details")
                normalized_details = details if isinstance(details, dict) else {}
                stream_log(
                    stream_id,
                    "client",
                    event,
                    persistent_connection=True,
                    **normalized_details,
                )
                continue
            if message_type == "synthesize":
                await state.requests.put(payload)
                continue
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "unsupported_message_type",
                    "received_type": message_type,
                }
            )
    except WebSocketDisconnect:
        _stop_connection(state, "websocket-disconnected")
    except Exception as exc:  # pragma: no cover - defensive receiver guard.
        _stop_connection(state, f"receiver-failed:{type(exc).__name__}")


async def _stream_phrase(
    websocket: WebSocket,
    payload: dict[str, Any],
    state: ConnectionState,
) -> None:
    """Generate and send one phrase without closing the turn websocket."""
    phrase_index = _phrase_index(payload)
    stream_id = normalize_stream_id(payload.get("diagnostics_stream_id"))
    route_started_at = time.perf_counter()
    registered = False
    producer: threading.Thread | None = None
    phrase_stop = threading.Event()
    sent_frames = 0
    sent_samples = 0

    try:
        try:
            request = TtsStreamRequest.model_validate(payload)
        except ValidationError as exc:
            stream_log(stream_id, "server", "request_invalid", error=repr(exc))
            await websocket.send_json(
                {
                    "type": "error",
                    "stream_id": stream_id,
                    "phrase_index": phrase_index,
                    "message": f"Invalid TTS request: {exc}",
                }
            )
            return

        begin_stream(stream_id, **_connection_details(websocket))
        registered = True
        raw_text = request.text or ""
        text = remove_emojis(raw_text).strip()
        stream_log(
            stream_id,
            "server",
            "request_received",
            text=raw_text,
            sanitized_text=text,
            text_length=len(raw_text),
            sanitized_text_length=len(text),
            text_sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            phrase_index=phrase_index,
            request_id=request.request_id,
            speaker=request.speaker,
            language=request.language,
            chunk_size=request.chunk_size,
            temperature=request.temperature,
            top_k=request.top_k,
            top_p=request.top_p,
            repetition_penalty=request.repetition_penalty,
            append_silence=request.append_silence,
            max_new_tokens=request.max_new_tokens,
            parity_mode=request.parity_mode,
            performance_schema_version=(
                request.delivery_plan.schema_version if request.delivery_plan else None
            ),
            log_path=diagnostics_log_path(),
            persistent_connection=True,
        )
        if not text:
            await websocket.send_json(
                {
                    "type": "error",
                    "stream_id": stream_id,
                    "phrase_index": phrase_index,
                    "message": "text_required",
                }
            )
            return

        provider = get_tts_provider()
        if provider is None or not hasattr(provider, "generate_audio_stream"):
            message = (
                "tts_provider_unavailable"
                if provider is None
                else "tts_provider_streaming_unavailable"
            )
            stream_log(stream_id, "server", "request_rejected", reason=message)
            await websocket.send_json(
                {
                    "type": "error",
                    "stream_id": stream_id,
                    "phrase_index": phrase_index,
                    "message": message,
                }
            )
            return

        performance_application = apply_performance_plan_to_provider(
            provider,
            request.delivery_plan,
        )
        capability_payload = performance_application.capabilities.model_dump(mode="json")
        applied_controls = list(performance_application.applied_controls)
        ignored_controls = list(performance_application.ignored_controls)
        provider_resolved_at = time.perf_counter()
        stream_log(
            stream_id,
            "server",
            "provider_resolved",
            provider_class=f"{type(provider).__module__}.{type(provider).__qualname__}",
            provider_name=getattr(provider, "provider_name", None),
            provider_object_id=id(provider),
            provider_capabilities=capability_payload,
            performance_controls_applied=applied_controls,
            performance_controls_ignored=ignored_controls,
            request_to_provider_ms=round(
                (provider_resolved_at - route_started_at) * 1000,
                3,
            ),
        )
        loop = asyncio.get_running_loop()
        frames: asyncio.Queue[FrameMessage] = asyncio.Queue()
        state.active_frames = frames

        def stopped() -> bool:
            return state.stop_event.is_set() or phrase_stop.is_set()

        def emit(message: FrameMessage) -> None:
            if not stopped():
                loop.call_soon_threadsafe(frames.put_nowait, message)

        def produce() -> None:
            producer_started_at = time.perf_counter()
            last_raw_chunk_at = producer_started_at
            raw_chunk_count = 0
            queued_frame_count = 0
            produced_samples = 0
            stream_log(
                stream_id,
                "provider",
                "producer_thread_started",
                phrase_index=phrase_index,
                request_to_producer_ms=round(
                    (producer_started_at - route_started_at) * 1000,
                    3,
                ),
            )
            try:
                stream_kwargs: dict[str, Any] = {
                    "chunk_size": request.chunk_size,
                    "temperature": request.temperature,
                    "top_k": request.top_k,
                    "top_p": request.top_p,
                    "repetition_penalty": request.repetition_penalty,
                    "append_silence": request.append_silence,
                    "non_streaming_mode": False,
                }
                if request.max_new_tokens is not None:
                    stream_kwargs["max_new_tokens"] = request.max_new_tokens
                if request.parity_mode is not None:
                    stream_kwargs["parity_mode"] = request.parity_mode
                stream_kwargs.update(performance_application.provider_kwargs)
                stream_log(
                    stream_id,
                    "provider",
                    "generation_started",
                    stream_kwargs=stream_kwargs,
                    performance_controls_applied=applied_controls,
                    performance_controls_ignored=ignored_controls,
                )

                def raw_chunks():
                    nonlocal last_raw_chunk_at, produced_samples, raw_chunk_count
                    provider_stream = provider.generate_audio_stream(
                        text=text,
                        speaker=request.speaker,
                        language=request.language or "en",
                        **stream_kwargs,
                    )
                    for audio_chunk, sample_rate, timing in provider_stream:
                        if stopped():
                            return
                        raw_chunk_ready_at = time.perf_counter()
                        if raw_chunk_count == 0:
                            stream_log(
                                stream_id,
                                "provider",
                                "first_raw_chunk_ready",
                                generation_elapsed_ms=round(
                                    (raw_chunk_ready_at - producer_started_at) * 1000,
                                    3,
                                ),
                                provider_timing=timing,
                            )
                        conversion_started_at = time.perf_counter()
                        pcm_bytes = _audio_chunk_to_pcm16_bytes(audio_chunk)
                        conversion_finished_at = time.perf_counter()
                        resolved_rate = int(sample_rate or DEFAULT_SAMPLE_RATE)
                        sample_count = len(pcm_bytes) // 2
                        raw_chunk_count += 1
                        produced_samples += sample_count
                        elapsed_ms = (raw_chunk_ready_at - producer_started_at) * 1000
                        audio_ms = produced_samples * 1000 / max(1, resolved_rate)
                        stream_log(
                            stream_id,
                            "provider",
                            "raw_chunk_received",
                            raw_chunk_index=raw_chunk_count - 1,
                            sample_rate=resolved_rate,
                            samples=sample_count,
                            bytes=len(pcm_bytes),
                            interval_ms=round(
                                (raw_chunk_ready_at - last_raw_chunk_at) * 1000,
                                3,
                            ),
                            generation_elapsed_ms=round(elapsed_ms, 3),
                            pcm_conversion_ms=round(
                                (conversion_finished_at - conversion_started_at) * 1000,
                                3,
                            ),
                            cumulative_audio_ms=round(audio_ms, 3),
                            generation_rtf=(
                                round(elapsed_ms / audio_ms, 5) if audio_ms else None
                            ),
                            provider_timing=timing,
                            stop_requested=stopped(),
                        )
                        last_raw_chunk_at = raw_chunk_ready_at
                        yield pcm_bytes, resolved_rate, timing

                for pcm_bytes, sample_rate, timing in _stream_pcm16_blocks(
                    raw_chunks(),
                    block_samples=TTS_PCM_FRAME_SAMPLES,
                ):
                    if stopped():
                        return
                    is_first_frame = queued_frame_count == 0
                    first_frame_ack = threading.Event() if is_first_frame else None
                    queued_at = time.perf_counter()
                    metadata = {
                        "frame_index": queued_frame_count,
                        "provider_timing": timing,
                        "producer_elapsed_ms": round(
                            (queued_at - producer_started_at) * 1000,
                            3,
                        ),
                    }
                    queued_frame_count += 1
                    emit(
                        FrameMessage(
                            "chunk",
                            pcm_bytes,
                            sample_rate,
                            metadata,
                            queued_at=queued_at,
                            sent_ack=first_frame_ack,
                        )
                    )
                    stream_log(
                        stream_id,
                        "provider",
                        "network_frame_queued",
                        frame_index=metadata["frame_index"],
                        sample_rate=sample_rate,
                        samples=len(pcm_bytes) // 2,
                        bytes=len(pcm_bytes),
                        first_frame_handoff_requested=is_first_frame,
                    )
                    if first_frame_ack is not None:
                        handoff_started_at = time.perf_counter()
                        acknowledged = first_frame_ack.wait(
                            timeout=FIRST_FRAME_HANDOFF_TIMEOUT_SECONDS
                        )
                        handoff_finished_at = time.perf_counter()
                        stream_log(
                            stream_id,
                            "provider",
                            "first_frame_handoff_completed",
                            acknowledged=acknowledged,
                            wait_ms=round(
                                (handoff_finished_at - handoff_started_at) * 1000,
                                3,
                            ),
                            timeout_ms=round(
                                FIRST_FRAME_HANDOFF_TIMEOUT_SECONDS * 1000,
                                3,
                            ),
                            stop_requested=stopped(),
                        )
                        if stopped():
                            return
                emit(FrameMessage("done", None, DEFAULT_SAMPLE_RATE, {}))
            except Exception as exc:  # pragma: no cover - surfaced to browser.
                stream_log(
                    stream_id,
                    "provider",
                    "generation_failed",
                    error=repr(exc),
                )
                emit(
                    FrameMessage(
                        "error",
                        None,
                        DEFAULT_SAMPLE_RATE,
                        {"message": str(exc) or "TTS stream failed."},
                    )
                )
            finally:
                stream_log(
                    stream_id,
                    "provider",
                    "producer_thread_finished",
                    elapsed_ms=round(
                        (time.perf_counter() - producer_started_at) * 1000,
                        3,
                    ),
                    raw_chunk_count=raw_chunk_count,
                    queued_frame_count=queued_frame_count,
                    produced_samples=produced_samples,
                    stop_requested=stopped(),
                )

        producer = threading.Thread(
            target=produce,
            name=f"omnix-tts-live-{stream_id[:19]}",
            daemon=True,
        )
        producer.start()
        stream_log(
            stream_id,
            "server",
            "producer_thread_launched",
            producer_thread_name=producer.name,
        )

        started = False
        current_sample_rate = DEFAULT_SAMPLE_RATE
        last_send_at = route_started_at
        while True:
            message = await frames.get()
            message_type = message.message_type
            pcm_bytes = message.pcm_bytes
            sample_rate = message.sample_rate
            metadata = message.metadata
            dequeued_at = time.perf_counter()
            frame_queue_wait_ms = (
                round((dequeued_at - message.queued_at) * 1000, 3)
                if message.queued_at is not None
                else None
            )
            if message_type == "client_disconnect":
                stream_log(
                    stream_id,
                    "server",
                    "client_disconnect_observed",
                    metadata=metadata,
                )
                return
            if message_type == "chunk" and pcm_bytes is not None:
                try:
                    if not started or sample_rate != current_sample_rate:
                        current_sample_rate = sample_rate
                        control_started_at = time.perf_counter()
                        await websocket.send_json(
                            {
                                "type": "start" if not started else "format",
                                "stream_id": stream_id,
                                "phrase_index": phrase_index,
                                "sample_rate": current_sample_rate,
                                "sample_format": "pcm_s16le",
                                "channels": 1,
                                "frame_samples": TTS_PCM_FRAME_SAMPLES,
                                "diagnostics_log": diagnostics_log_path(),
                                "provider_capabilities": capability_payload,
                                "performance_controls_applied": applied_controls,
                                "performance_controls_ignored": ignored_controls,
                            }
                        )
                        control_sent_at = time.perf_counter()
                        if not started:
                            stream_log(
                                stream_id,
                                "server",
                                "first_start_control_sent",
                                frame_queue_wait_ms=frame_queue_wait_ms,
                                send_duration_ms=round(
                                    (control_sent_at - control_started_at) * 1000,
                                    3,
                                ),
                            )
                        started = True
                    send_started_at = time.perf_counter()
                    await websocket.send_bytes(pcm_bytes)
                    sent_at = time.perf_counter()
                finally:
                    if message.sent_ack is not None:
                        message.sent_ack.set()
                frame_samples = len(pcm_bytes) // 2
                sent_frames += 1
                sent_samples += frame_samples
                stream_log(
                    stream_id,
                    "server",
                    "network_frame_sent",
                    frame_index=sent_frames - 1,
                    bytes=len(pcm_bytes),
                    samples=frame_samples,
                    sample_rate=current_sample_rate,
                    frame_queue_wait_ms=frame_queue_wait_ms,
                    send_duration_ms=round((sent_at - send_started_at) * 1000, 3),
                    interval_since_previous_send_ms=round(
                        (sent_at - last_send_at) * 1000,
                        3,
                    ),
                    cumulative_audio_ms=round(
                        sent_samples * 1000 / max(1, current_sample_rate),
                        3,
                    ),
                    pending_server_frames=frames.qsize(),
                    producer_metadata=metadata,
                )
                if sent_frames == 1:
                    stream_log(
                        stream_id,
                        "server",
                        "first_pcm_frame_sent",
                        request_to_first_frame_ms=round(
                            (sent_at - route_started_at) * 1000,
                            3,
                        ),
                        frame_queue_wait_ms=frame_queue_wait_ms,
                        send_duration_ms=round(
                            (sent_at - send_started_at) * 1000,
                            3,
                        ),
                    )
                last_send_at = sent_at
                continue
            if message_type == "done":
                await websocket.send_json(
                    {
                        "type": "done",
                        "stream_id": stream_id,
                        "phrase_index": phrase_index,
                        "partial": False,
                    }
                )
                stream_log(
                    stream_id,
                    "server",
                    "done_control_sent",
                    phrase_index=phrase_index,
                    sent_frames=sent_frames,
                    sent_samples=sent_samples,
                    sent_audio_ms=round(
                        sent_samples * 1000 / max(1, current_sample_rate),
                        3,
                    ),
                    persistent_connection=True,
                )
                return
            message_text = metadata.get("message") or "TTS stream failed."
            await websocket.send_json(
                {
                    "type": "error",
                    "stream_id": stream_id,
                    "phrase_index": phrase_index,
                    "message": message_text,
                }
            )
            return
    finally:
        phrase_stop.set()
        if state.active_frames is not None:
            state.active_frames = None
        producer_alive_before_join = bool(producer and producer.is_alive())
        if producer is not None and producer_alive_before_join:
            await asyncio.to_thread(producer.join, 0.25)
        producer_alive_after_join = bool(producer and producer.is_alive())
        stream_log(
            stream_id,
            "server",
            "phrase_route_cleanup",
            phrase_index=phrase_index,
            route_elapsed_ms=round(
                (time.perf_counter() - route_started_at) * 1000,
                3,
            ),
            sent_frames=sent_frames,
            sent_samples=sent_samples,
            producer_alive_before_join=producer_alive_before_join,
            producer_alive_after_join=producer_alive_after_join,
            persistent_connection=True,
        )
        if registered:
            end_stream(
                stream_id,
                producer_alive_after_join=producer_alive_after_join,
                sent_frames=sent_frames,
                sent_samples=sent_samples,
            )


def register_tts_live_call_websocket(gateway: FastAPI) -> None:
    """Register one reusable websocket per live-call turn."""
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.websocket(TTS_LIVE_CALL_WEBSOCKET_PATH)
    async def tts_live_call_websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        state = ConnectionState(
            stop_event=threading.Event(),
            requests=asyncio.Queue(),
        )
        receiver = asyncio.create_task(_receive_messages(websocket, state))
        try:
            while not state.stop_event.is_set():
                payload = await state.requests.get()
                if payload is None:
                    return
                await _stream_phrase(websocket, payload, state)
        finally:
            _stop_connection(state, "route-cleanup")
            receiver.cancel()
            with suppress(asyncio.CancelledError):
                await receiver
            with suppress(Exception):
                await websocket.close()


def install_tts_live_call_websocket_hook() -> None:
    """Install the persistent live-call websocket hook for the local gateway."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        is_gateway = kwargs.get("title") == "Omnix Web Gateway"
        if is_gateway or (args and args[0] == "Omnix Web Gateway"):
            register_tts_live_call_websocket(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
