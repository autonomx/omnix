"""Session-scoped persistent PCM websocket transport for live voice."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app import shared
from app.live_speech.performance_contract import apply_performance_plan_to_provider
from app.shared import remove_emojis

from .live_voice_speculative_tts import resolve_live_call_tts_provider
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
TTS_PCM_FRAME_SAMPLES = 2_400
FIRST_FRAME_HANDOFF_TIMEOUT_SECONDS = 0.050

# Explicit dependency seam retained for focused tests and alternate gateway
# composition. Runtime lane selection still happens below; this is not a
# process-wide provider monkey-patch.
get_tts_provider = shared.get_tts_provider


@dataclass(frozen=True)
class FrameMessage:
    message_type: str
    pcm_bytes: bytes | None
    sample_rate: int
    metadata: dict[str, Any]
    queued_at: float | None = None
    sent_ack: threading.Event | None = None


@dataclass
class ActiveOutput:
    output_id: str
    generation_epoch: int
    segment_id: str
    phrase_index: int | None
    stop_event: threading.Event
    sent_frames: int = 0


@dataclass
class ConnectionState:
    stop_event: threading.Event
    requests: asyncio.Queue[dict[str, Any] | None]
    active_frames: asyncio.Queue[FrameMessage] | None = None
    active_output: ActiveOutput | None = None
    cancelled_outputs: set[tuple[str, int]] = field(default_factory=set)


def _connection_details(websocket: WebSocket) -> dict[str, Any]:
    client = websocket.client
    return {
        "client_host": client.host if client else None,
        "client_port": client.port if client else None,
        "origin": websocket.headers.get("origin"),
        "user_agent": websocket.headers.get("user-agent"),
        "websocket_path": websocket.url.path,
        "persistent_connection": True,
        "websocket_scope": "live_session",
    }


def _phrase_index(payload: dict[str, Any]) -> int | None:
    value = payload.get("phrase_index")
    return value if isinstance(value, int) and value >= 0 else None


def _output_identity(payload: dict[str, Any]) -> tuple[str, int, str]:
    output_id = str(payload.get("output_id") or payload.get("request_id") or "legacy-output")[:160]
    try:
        generation_epoch = max(0, int(payload.get("generation_epoch") or 0))
    except (TypeError, ValueError):
        generation_epoch = 0
    segment_id = str(payload.get("segment_id") or f"{output_id}:segment")[:160]
    return output_id, generation_epoch, segment_id


def _ownership_fields(
    payload: dict[str, Any],
    output_id: str,
    generation_epoch: int,
    segment_id: str,
    output_order: Any = None,
) -> dict[str, Any]:
    """Expose ownership fields only to item-aware clients, preserving legacy controls."""
    if not str(payload.get("output_id") or "").strip():
        return {}
    return {
        "output_id": output_id,
        "generation_epoch": generation_epoch,
        "segment_id": segment_id,
        "output_order": output_order,
    }


def _stop_connection(state: ConnectionState, reason: str) -> None:
    if state.stop_event.is_set():
        return
    state.stop_event.set()
    if state.active_output is not None:
        state.active_output.stop_event.set()
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
    """Receive synthesis, cancellation, diagnostics, and close messages concurrently."""
    try:
        while not state.stop_event.is_set():
            raw_message = await websocket.receive_text()
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                await websocket.send_json({"type": "error", "message": f"Invalid JSON: {exc}"})
                continue
            if not isinstance(payload, dict):
                await websocket.send_json({"type": "error", "message": "TTS message must be an object."})
                continue
            message_type = payload.get("type")
            if message_type == "close":
                _stop_connection(state, str(payload.get("reason") or "client-close"))
                return
            if message_type == "diagnostic":
                stream_id = normalize_stream_id(payload.get("stream_id"))
                event = str(payload.get("event") or "diagnostic")[:120]
                details = payload.get("details")
                stream_log(
                    stream_id,
                    "client",
                    event,
                    persistent_connection=True,
                    **(details if isinstance(details, dict) else {}),
                )
                continue
            if message_type == "cancel":
                output_id, generation_epoch, segment_id = _output_identity(payload)
                key = (output_id, generation_epoch)
                state.cancelled_outputs.add(key)
                active = state.active_output
                generated_through_frame = -1
                if active and (active.output_id, active.generation_epoch) == key:
                    generated_through_frame = active.sent_frames - 1
                    active.stop_event.set()
                    if state.active_frames is not None:
                        state.active_frames.put_nowait(
                            FrameMessage(
                                "cancelled",
                                None,
                                DEFAULT_SAMPLE_RATE,
                                {
                                    "output_id": output_id,
                                    "generation_epoch": generation_epoch,
                                    "segment_id": active.segment_id,
                                    "reason": str(payload.get("reason") or "cancelled"),
                                },
                            )
                        )
                await websocket.send_json(
                    {
                        "type": "cancel_accepted",
                        "output_id": output_id,
                        "generation_epoch": generation_epoch,
                        "segment_id": segment_id,
                        "generated_through_frame": generated_through_frame,
                    }
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
    except Exception as exc:  # pragma: no cover
        _stop_connection(state, f"receiver-failed:{type(exc).__name__}")


async def _stream_phrase(
    websocket: WebSocket,
    payload: dict[str, Any],
    state: ConnectionState,
) -> None:
    """Generate and send one output item without closing the session websocket."""
    phrase_index = _phrase_index(payload)
    stream_id = normalize_stream_id(payload.get("diagnostics_stream_id"))
    output_id, generation_epoch, segment_id = _output_identity(payload)
    output_order = payload.get("output_order")
    ownership_fields = _ownership_fields(
        payload,
        output_id,
        generation_epoch,
        segment_id,
        output_order,
    )
    route_started_at = time.perf_counter()
    registered = False
    producer: threading.Thread | None = None
    phrase_stop = threading.Event()
    sent_frames = 0
    sent_samples = 0
    key = (output_id, generation_epoch)

    if key in state.cancelled_outputs:
        await websocket.send_json(
            {
                "type": "cancelled",
                "stream_id": stream_id,
                **ownership_fields,
                "generated_through_frame": -1,
            }
        )
        return

    active_output = ActiveOutput(
        output_id=output_id,
        generation_epoch=generation_epoch,
        segment_id=segment_id,
        phrase_index=phrase_index,
        stop_event=phrase_stop,
    )
    state.active_output = active_output

    try:
        try:
            request = TtsStreamRequest.model_validate(payload)
        except ValidationError as exc:
            stream_log(stream_id, "server", "request_invalid", error=repr(exc))
            await websocket.send_json(
                {
                    "type": "error",
                    "stream_id": stream_id,
                    **ownership_fields,
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
            phrase_index=phrase_index,
            request_id=request.request_id,
            output_id=output_id,
            generation_epoch=generation_epoch,
            segment_id=segment_id,
            output_order=output_order,
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
                    **ownership_fields,
                    "phrase_index": phrase_index,
                    "message": "text_required",
                }
            )
            return

        provider = resolve_live_call_tts_provider(get_tts_provider())
        if provider is None or not hasattr(provider, "generate_audio_stream"):
            message = "tts_provider_unavailable" if provider is None else "tts_provider_streaming_unavailable"
            stream_log(stream_id, "server", "request_rejected", reason=message)
            await websocket.send_json(
                {
                    "type": "error",
                    "stream_id": stream_id,
                    **ownership_fields,
                    "phrase_index": phrase_index,
                    "message": message,
                }
            )
            return

        performance_application = apply_performance_plan_to_provider(provider, request.delivery_plan)
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
            live_execution_lane=getattr(provider, "execution_lane", "shared"),
            provider_capabilities=capability_payload,
            performance_controls_applied=applied_controls,
            performance_controls_ignored=ignored_controls,
            request_to_provider_ms=round((provider_resolved_at - route_started_at) * 1000, 3),
            output_id=output_id,
            generation_epoch=generation_epoch,
        )
        loop = asyncio.get_running_loop()
        frames: asyncio.Queue[FrameMessage] = asyncio.Queue()
        state.active_frames = frames

        def stopped() -> bool:
            return state.stop_event.is_set() or phrase_stop.is_set() or key in state.cancelled_outputs

        def emit(message: FrameMessage) -> None:
            if not stopped() or message.message_type in {"cancelled", "client_disconnect"}:
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
                output_id=output_id,
                generation_epoch=generation_epoch,
                request_to_producer_ms=round((producer_started_at - route_started_at) * 1000, 3),
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
                        pcm_bytes = _audio_chunk_to_pcm16_bytes(audio_chunk)
                        resolved_rate = int(sample_rate or DEFAULT_SAMPLE_RATE)
                        sample_count = len(pcm_bytes) // 2
                        raw_chunk_count += 1
                        produced_samples += sample_count
                        last_raw_chunk_at = raw_chunk_ready_at
                        if raw_chunk_count == 1:
                            stream_log(
                                stream_id,
                                "provider",
                                "first_raw_chunk_ready",
                                provider_to_first_raw_ms=round(
                                    (raw_chunk_ready_at - provider_resolved_at) * 1000,
                                    3,
                                ),
                                route_to_first_raw_ms=round(
                                    (raw_chunk_ready_at - route_started_at) * 1000,
                                    3,
                                ),
                                raw_chunk_samples=sample_count,
                                sample_rate=resolved_rate,
                                output_id=output_id,
                                generation_epoch=generation_epoch,
                            )
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
                        "output_id": output_id,
                        "generation_epoch": generation_epoch,
                        "segment_id": segment_id,
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
                    if first_frame_ack is not None:
                        wait_started_at = time.perf_counter()
                        first_frame_ack.wait(timeout=FIRST_FRAME_HANDOFF_TIMEOUT_SECONDS)
                        stream_log(
                            stream_id,
                            "provider",
                            "first_frame_handoff_completed",
                            acknowledged=first_frame_ack.is_set(),
                            wait_ms=round((time.perf_counter() - wait_started_at) * 1000, 3),
                            output_id=output_id,
                            generation_epoch=generation_epoch,
                        )
                        if stopped():
                            return
                if stopped():
                    return
                emit(FrameMessage("done", None, DEFAULT_SAMPLE_RATE, {}))
            except Exception as exc:  # pragma: no cover
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
                    elapsed_ms=round((time.perf_counter() - producer_started_at) * 1000, 3),
                    raw_chunk_count=raw_chunk_count,
                    queued_frame_count=queued_frame_count,
                    produced_samples=produced_samples,
                    last_raw_chunk_age_ms=round((time.perf_counter() - last_raw_chunk_at) * 1000, 3),
                    stop_requested=stopped(),
                    output_id=output_id,
                    generation_epoch=generation_epoch,
                )

        producer = threading.Thread(
            target=produce,
            name=f"omnix-tts-live-{stream_id[:19]}",
            daemon=True,
        )
        producer.start()

        started = False
        current_sample_rate = DEFAULT_SAMPLE_RATE
        while True:
            message = await frames.get()
            message_type = message.message_type
            pcm_bytes = message.pcm_bytes
            sample_rate = message.sample_rate
            metadata = message.metadata
            if message_type == "client_disconnect":
                return
            if message_type == "cancelled":
                await websocket.send_json(
                    {
                        "type": "cancelled",
                        "stream_id": stream_id,
                        **ownership_fields,
                        "generated_through_frame": sent_frames - 1,
                        "reason": metadata.get("reason") or "cancelled",
                    }
                )
                return
            if message_type == "chunk" and pcm_bytes is not None:
                try:
                    if stopped():
                        continue
                    if not started or sample_rate != current_sample_rate:
                        first_start_control = not started
                        current_sample_rate = sample_rate
                        await websocket.send_json(
                            {
                                "type": "start" if first_start_control else "format",
                                "stream_id": stream_id,
                                **ownership_fields,
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
                        if first_start_control:
                            stream_log(
                                stream_id,
                                "server",
                                "first_start_control_sent",
                                route_to_start_control_ms=round(
                                    (time.perf_counter() - route_started_at) * 1000,
                                    3,
                                ),
                                output_id=output_id,
                                generation_epoch=generation_epoch,
                            )
                        started = True
                    first_pcm_frame = sent_frames == 0
                    await websocket.send_bytes(pcm_bytes)
                    if first_pcm_frame:
                        now = time.perf_counter()
                        stream_log(
                            stream_id,
                            "server",
                            "first_pcm_frame_sent",
                            frame_queue_wait_ms=(
                                round((now - message.queued_at) * 1000, 3)
                                if message.queued_at is not None
                                else None
                            ),
                            route_to_first_frame_ms=round((now - route_started_at) * 1000, 3),
                            frame_samples=len(pcm_bytes) // 2,
                            sample_rate=sample_rate,
                            output_id=output_id,
                            generation_epoch=generation_epoch,
                        )
                finally:
                    if message.sent_ack is not None:
                        message.sent_ack.set()
                frame_samples = len(pcm_bytes) // 2
                sent_frames += 1
                active_output.sent_frames = sent_frames
                sent_samples += frame_samples
                continue
            if message_type == "done":
                await websocket.send_json(
                    {
                        "type": "done",
                        "stream_id": stream_id,
                        **ownership_fields,
                        "phrase_index": phrase_index,
                        "last_frame_index": sent_frames - 1,
                        "partial": False,
                    }
                )
                stream_log(
                    stream_id,
                    "server",
                    "done_control_sent",
                    route_to_done_control_ms=round(
                        (time.perf_counter() - route_started_at) * 1000,
                        3,
                    ),
                    sent_frames=sent_frames,
                    sent_samples=sent_samples,
                    last_frame_index=sent_frames - 1,
                    output_id=output_id,
                    generation_epoch=generation_epoch,
                )
                return
            await websocket.send_json(
                {
                    "type": "error",
                    "stream_id": stream_id,
                    **ownership_fields,
                    "phrase_index": phrase_index,
                    "message": metadata.get("message") or "TTS stream failed.",
                }
            )
            return
    finally:
        phrase_stop.set()
        if state.active_frames is not None:
            state.active_frames = None
        if state.active_output is active_output:
            state.active_output = None
        producer_alive_before_join = bool(producer and producer.is_alive())
        if producer is not None and producer_alive_before_join:
            await asyncio.to_thread(producer.join, 0.25)
        producer_alive_after_join = bool(producer and producer.is_alive())
        stream_log(
            stream_id,
            "server",
            "phrase_route_cleanup",
            phrase_index=phrase_index,
            output_id=output_id,
            generation_epoch=generation_epoch,
            route_elapsed_ms=round((time.perf_counter() - route_started_at) * 1000, 3),
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
                output_id=output_id,
                generation_epoch=generation_epoch,
            )


def register_tts_live_call_websocket(gateway: FastAPI) -> None:
    """Register one reusable websocket per Live session."""
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
                output_id, generation_epoch, segment_id = _output_identity(payload)
                if (output_id, generation_epoch) in state.cancelled_outputs:
                    ownership_fields = _ownership_fields(
                        payload,
                        output_id,
                        generation_epoch,
                        segment_id,
                        payload.get("output_order"),
                    )
                    await websocket.send_json(
                        {
                            "type": "cancelled",
                            **ownership_fields,
                            "generated_through_frame": -1,
                        }
                    )
                    continue
                await _stream_phrase(websocket, payload, state)
        finally:
            _stop_connection(state, "route-cleanup")
            receiver.cancel()
            with suppress(asyncio.CancelledError):
                await receiver
            with suppress(Exception):
                await websocket.close()


def install_tts_live_call_websocket_hook() -> None:
    """Install the persistent live-session websocket hook for the local gateway."""
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
