"""Voice Studio compatible TTS streaming routes for the browser gateway."""
from __future__ import annotations

import base64
import json
from functools import wraps
from typing import Any, Callable, Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.assist_core.hermes_api import router as hermes_router
from app.shared import get_tts_provider, remove_emojis

_ROUTE_SENTINEL = "_omnix_tts_sse_registered"
_HOOK_SENTINEL = "_omnix_tts_sse_hook_installed"
_HERMES_ROUTE_SENTINEL = "_omnix_hermes_routes_registered"
DEFAULT_SAMPLE_RATE = 24_000
STREAM_START_BUFFER_SECONDS = 0.75
STREAM_START_BUFFER_MAX_CHUNKS = 4


class TtsStreamRequest(BaseModel):
    """Browser-facing TTS SSE request payload."""

    text: str = ""
    speaker: str | None = None
    language: str | None = "en"
    chunk_size: int = Field(default=12, ge=1, le=256)
    temperature: float = Field(default=0.9, ge=0.0, le=2.0)
    top_k: int = Field(default=50, ge=0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    repetition_penalty: float = Field(default=1.05, ge=0.0)
    append_silence: bool = True
    max_new_tokens: int | None = Field(default=None, ge=1)
    non_streaming_mode: bool | None = None
    parity_mode: bool | None = None


def register_hermes_routes(gateway: FastAPI) -> None:
    """Register Hermes gateway routes once."""
    if getattr(gateway.state, _HERMES_ROUTE_SENTINEL, False):
        return
    gateway.include_router(hermes_router)
    setattr(gateway.state, _HERMES_ROUTE_SENTINEL, True)


def register_tts_stream_routes(gateway: FastAPI) -> None:
    """Register Voice Studio compatible SSE TTS routes."""
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)

    @gateway.post("/api/tts/stream/server-sent-events", include_in_schema=False)
    async def tts_stream_server_sent_events(request: TtsStreamRequest) -> StreamingResponse:
        text = remove_emojis(request.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text_required")

        provider = get_tts_provider()
        if provider is None:
            raise HTTPException(status_code=503, detail="tts_provider_unavailable")
        if not hasattr(provider, "generate_audio_stream"):
            raise HTTPException(status_code=501, detail="tts_provider_streaming_unavailable")

        return StreamingResponse(
            _tts_sse_stream(provider, request, text),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


def install_tts_stream_hook() -> None:
    """Install the TTS SSE route hook for the local gateway app."""
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return

    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (args and args[0] == "Omnix Web Gateway"):
            register_hermes_routes(self)
            register_tts_stream_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)


def _tts_sse_stream(provider: Any, request: TtsStreamRequest, text: str) -> Iterator[str]:
    yield _sse_comment("tts-stream-open")
    stream_kwargs: dict[str, Any] = {
        "chunk_size": request.chunk_size,
        "temperature": request.temperature,
        "top_k": request.top_k,
        "top_p": request.top_p,
        "repetition_penalty": request.repetition_penalty,
        "append_silence": request.append_silence,
        # This route exists specifically for incremental playback. Some clients
        # previously sent True here, which made the provider wait for the entire
        # waveform and silently turned the stream into a high-latency batch job.
        "non_streaming_mode": False,
    }
    if request.max_new_tokens is not None:
        stream_kwargs["max_new_tokens"] = request.max_new_tokens
    if request.parity_mode is not None:
        stream_kwargs["parity_mode"] = request.parity_mode

    startup_events: list[str] = []
    startup_buffer_seconds = 0.0
    stream_started = False

    try:
        for chunk_index, (audio_chunk, sample_rate, timing) in enumerate(
            provider.generate_audio_stream(
                text=text,
                speaker=request.speaker,
                language=request.language or "en",
                **stream_kwargs,
            )
        ):
            pcm_bytes = _audio_chunk_to_pcm16_bytes(audio_chunk)
            if not pcm_bytes:
                continue
            effective_sample_rate = int(sample_rate or DEFAULT_SAMPLE_RATE)
            event = _sse_data(
                {
                    "type": "chunk",
                    "chunk_index": chunk_index,
                    "audio_b64": base64.b64encode(pcm_bytes).decode("utf-8"),
                    "sample_rate": effective_sample_rate,
                    "timing": timing if isinstance(timing, dict) else {},
                }
            )

            if not stream_started:
                startup_events.append(event)
                startup_buffer_seconds += _pcm16_duration_seconds(pcm_bytes, effective_sample_rate)
                if (
                    startup_buffer_seconds < STREAM_START_BUFFER_SECONDS
                    and len(startup_events) < STREAM_START_BUFFER_MAX_CHUNKS
                ):
                    continue
                yield from startup_events
                startup_events.clear()
                stream_started = True
                continue

            yield event

        # Short responses may finish before reaching the target buffer. They
        # still need to be flushed instead of waiting for a nonexistent chunk.
        if startup_events:
            yield from startup_events
        yield _sse_data({"type": "done"})
    except Exception as exc:  # pragma: no cover - provider failures are surfaced to the browser.
        yield _sse_data({"type": "error", "message": str(exc) or "TTS stream failed."})


def _pcm16_duration_seconds(pcm_bytes: bytes, sample_rate: int) -> float:
    """Return mono PCM16 duration, guarding invalid provider sample rates."""
    if sample_rate <= 0:
        return 0.0
    return len(pcm_bytes) / 2 / sample_rate


def _audio_chunk_to_pcm16_bytes(audio_chunk: Any) -> bytes:
    """Convert float-like mono chunks to little-endian PCM16 without importing numpy."""
    if audio_chunk is None:
        return b""
    if isinstance(audio_chunk, bytes):
        return audio_chunk
    if isinstance(audio_chunk, bytearray):
        return bytes(audio_chunk)

    values = audio_chunk.tolist() if hasattr(audio_chunk, "tolist") else audio_chunk
    if not isinstance(values, (list, tuple)):
        values = [values]

    pcm = bytearray()
    for value in values:
        if isinstance(value, (list, tuple)):
            value = value[0] if value else 0.0
        try:
            sample = float(value)
        except (TypeError, ValueError):
            continue
        sample = max(-1.0, min(1.0, sample))
        pcm.extend(int(sample * 32767).to_bytes(2, byteorder="little", signed=True))
    return bytes(pcm)


def _sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, sort_keys=True)}\n\n"


def _sse_comment(comment: str) -> str:
    return f": {comment}\n\n"
