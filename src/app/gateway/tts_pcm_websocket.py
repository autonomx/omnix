"""Raw PCM websocket transport for browser TTS streaming."""
from __future__ import annotations

import asyncio
import json
import threading
from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.shared import get_tts_provider, remove_emojis

from .tts_streaming import (
    DEFAULT_SAMPLE_RATE,
    TtsStreamRequest,
    _audio_chunk_to_pcm16_bytes,
    _stream_pcm16_blocks,
)

_ROUTE_SENTINEL = "_omnix_tts_pcm_ws_registered"
_HOOK_SENTINEL = "_omnix_tts_pcm_ws_hook_installed"
TTS_PCM_WEBSOCKET_PATH = "/api/tts/stream/websocket"
TTS_PCM_FRAME_SAMPLES = 2_400  # 100 ms at 24 kHz, matching the network streamer cadence.


FrameMessage = tuple[str, bytes | None, int, str | None]


def register_tts_pcm_websocket(gateway: FastAPI) -> None:
    """Register the raw PCM websocket route once."""
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.websocket(TTS_PCM_WEBSOCKET_PATH)
    async def tts_pcm_websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        stop_event = threading.Event()
        producer: threading.Thread | None = None

        try:
            raw_message = await websocket.receive_text()
            try:
                payload = json.loads(raw_message)
                request = TtsStreamRequest.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                await websocket.send_json({"type": "error", "message": f"Invalid TTS request: {exc}"})
                return

            text = remove_emojis(request.text or "").strip()
            if not text:
                await websocket.send_json({"type": "error", "message": "text_required"})
                return

            provider = get_tts_provider()
            if provider is None:
                await websocket.send_json({"type": "error", "message": "tts_provider_unavailable"})
                return
            if not hasattr(provider, "generate_audio_stream"):
                await websocket.send_json({"type": "error", "message": "tts_provider_streaming_unavailable"})
                return

            loop = asyncio.get_running_loop()
            frames: asyncio.Queue[FrameMessage] = asyncio.Queue()

            def emit(message: FrameMessage) -> None:
                if not stop_event.is_set():
                    loop.call_soon_threadsafe(frames.put_nowait, message)

            def produce() -> None:
                chunk_count = 0
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

                    raw_chunks = (
                        (_audio_chunk_to_pcm16_bytes(audio_chunk), int(sample_rate or DEFAULT_SAMPLE_RATE), timing)
                        for audio_chunk, sample_rate, timing in provider.generate_audio_stream(
                            text=text,
                            speaker=request.speaker,
                            language=request.language or "en",
                            **stream_kwargs,
                        )
                    )
                    for pcm_bytes, sample_rate, _timing in _stream_pcm16_blocks(
                        raw_chunks,
                        block_samples=TTS_PCM_FRAME_SAMPLES,
                    ):
                        if stop_event.is_set():
                            return
                        emit(("chunk", pcm_bytes, sample_rate, None))
                        chunk_count += 1
                    emit(("done", None, DEFAULT_SAMPLE_RATE, None))
                except Exception as exc:  # pragma: no cover - provider failures are surfaced to the client.
                    if chunk_count > 0:
                        emit(("partial_done", None, DEFAULT_SAMPLE_RATE, str(exc) or "TTS stream ended early."))
                    else:
                        emit(("error", None, DEFAULT_SAMPLE_RATE, str(exc) or "TTS stream failed."))

            producer = threading.Thread(target=produce, name="omnix-tts-pcm-websocket", daemon=True)
            producer.start()

            started = False
            current_sample_rate = DEFAULT_SAMPLE_RATE
            while True:
                message_type, pcm_bytes, sample_rate, message = await frames.get()
                if message_type == "chunk" and pcm_bytes is not None:
                    if not started or sample_rate != current_sample_rate:
                        current_sample_rate = sample_rate
                        await websocket.send_json(
                            {
                                "type": "start" if not started else "format",
                                "sample_rate": current_sample_rate,
                                "sample_format": "pcm_s16le",
                                "channels": 1,
                                "frame_samples": TTS_PCM_FRAME_SAMPLES,
                            }
                        )
                        started = True
                    await websocket.send_bytes(pcm_bytes)
                    continue
                if message_type == "done":
                    await websocket.send_json({"type": "done"})
                    return
                if message_type == "partial_done":
                    await websocket.send_json({"type": "done", "partial": True, "message": message})
                    return
                await websocket.send_json({"type": "error", "message": message or "TTS stream failed."})
                return
        except WebSocketDisconnect:
            return
        finally:
            stop_event.set()
            if producer is not None and producer.is_alive():
                producer.join(timeout=0.05)


def install_tts_pcm_websocket_hook() -> None:
    """Install the raw PCM websocket route hook for the local gateway."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_tts_pcm_websocket(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
