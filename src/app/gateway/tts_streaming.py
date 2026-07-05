"""Voice Studio compatible TTS streaming routes for the browser gateway."""
from __future__ import annotations

import base64
import json
import time
import wave
from functools import wraps
from io import BytesIO
from typing import Any, Callable, Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.assist_core.hermes_api import router as hermes_router
from app.shared import get_tts_provider, remove_emojis

_ROUTE_SENTINEL = "_omnix_tts_sse_registered"
_HOOK_SENTINEL = "_omnix_tts_sse_hook_installed"
_HERMES_ROUTE_SENTINEL = "_omnix_hermes_routes_registered"
DEFAULT_SAMPLE_RATE = 24_000
STREAM_START_BUFFER_SECONDS = 0.10
STREAM_START_BUFFER_MAX_CHUNKS = 1
STREAM_OUTPUT_BLOCK_SAMPLES = 2048
STREAM_INITIAL_SILENCE_THRESHOLD = 0.01
STREAM_INITIAL_PREROLL_MS = 40.0
CHAT_STREAM_MIN_NEW_TOKENS = 192
CHAT_STREAM_MAX_NEW_TOKENS = 1_024
CHAT_STREAM_TOKEN_OVERHEAD = 48


def estimate_chat_stream_max_new_tokens(text: str) -> int:
    """Bound chat speech length while leaving generous room to finish the text."""
    normalized = remove_emojis(text or "").strip()
    estimated = ((len(normalized) * 5) + 3) // 4 + CHAT_STREAM_TOKEN_OVERHEAD
    return max(CHAT_STREAM_MIN_NEW_TOKENS, min(CHAT_STREAM_MAX_NEW_TOKENS, estimated))


class TtsStreamRequest(BaseModel):
    """Browser-facing TTS streaming request payload."""

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
    request_id: str | None = None
    diagnostics_stream_id: str | None = None

    @model_validator(mode="after")
    def apply_chat_stream_runtime_policy(self) -> "TtsStreamRequest":
        """Use CUDA graphs and a text-relative completion bound for chat playback."""
        stream_id = (self.diagnostics_stream_id or "").strip()
        if not stream_id.startswith("chat-"):
            return self
        self.parity_mode = False
        if self.max_new_tokens is None:
            self.max_new_tokens = estimate_chat_stream_max_new_tokens(self.text)
        return self


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
    request_id = (request.request_id or "tts:unknown").strip() or "tts:unknown"
    started_at = time.perf_counter()
    mode = "single-buffered" if request.non_streaming_mode is True else "chunked"
    print(
        "[TTS SSE] request start "
        f"id={request_id} mode={mode} chars={len(text)} speaker={request.speaker or 'default'} "
        f"chunk_size={request.chunk_size} parity={request.parity_mode} non_streaming={request.non_streaming_mode}"
    )
    yield _sse_comment("tts-stream-open")
    if request.non_streaming_mode is True:
        yield from _tts_sse_single_audio(provider, request, text)
        return

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
        provider_chunk_count = 0
        raw_chunks = (
            (_audio_chunk_to_pcm16_bytes(audio_chunk), int(sample_rate or DEFAULT_SAMPLE_RATE), timing)
            for audio_chunk, sample_rate, timing in provider.generate_audio_stream(
                text=text,
                speaker=request.speaker,
                language=request.language or "en",
                **stream_kwargs,
            )
        )
        for chunk_index, (pcm_bytes, effective_sample_rate, timing) in enumerate(_stream_pcm16_blocks(raw_chunks)):
            provider_chunk_count += 1
            duration_seconds = _pcm16_duration_seconds(pcm_bytes, effective_sample_rate)
            if chunk_index == 0:
                print(
                    "[TTS SSE] first audio chunk ready "
                    f"id={request_id} elapsed_ms={(time.perf_counter() - started_at) * 1000:.1f} "
                    f"sample_rate={effective_sample_rate} bytes={len(pcm_bytes)} duration_ms={duration_seconds * 1000:.1f}"
                )
            event = _sse_data(
                {
                    "type": "chunk",
                    "chunk_index": chunk_index,
                    "audio_b64": base64.b64encode(pcm_bytes).decode("utf-8"),
                    "sample_rate": effective_sample_rate,
                    "timing": {
                        **(timing if isinstance(timing, dict) else {}),
                        "sse_chunk_duration_ms": round(duration_seconds * 1000, 1),
                    },
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
        print(
            "[TTS SSE] stream complete "
            f"id={request_id} chunks={provider_chunk_count} elapsed_ms={(time.perf_counter() - started_at) * 1000:.1f}"
        )
        yield _sse_data({"type": "done"})
    except Exception as exc:  # pragma: no cover - provider failures are surfaced to the browser.
        if stream_started:
            print(
                "[TTS SSE] stream partial-done "
                f"id={request_id} chunks={provider_chunk_count} elapsed_ms={(time.perf_counter() - started_at) * 1000:.1f} error={exc}"
            )
            yield _sse_data({"type": "done", "partial": True, "message": str(exc) or "TTS stream ended early."})
            return
        print(
            "[TTS SSE] stream error before audio "
            f"id={request_id} elapsed_ms={(time.perf_counter() - started_at) * 1000:.1f} error={exc}"
        )
        yield _sse_data({"type": "error", "message": str(exc) or "TTS stream failed."})


def _tts_sse_single_audio(provider: Any, request: TtsStreamRequest, text: str) -> Iterator[str]:
    request_id = (request.request_id or "tts:unknown").strip() or "tts:unknown"
    started_at = time.perf_counter()
    if hasattr(provider, "generate_audio_stream"):
        print(f"[TTS SSE] single-audio streaming synthesis start id={request_id} chars={len(text)} speaker={request.speaker or 'default'}")
        try:
            pcm_parts: list[bytes] = []
            sample_rate = DEFAULT_SAMPLE_RATE
            for audio_chunk, sr, _timing in provider.generate_audio_stream(
                text=text,
                speaker=request.speaker,
                language=request.language or "en",
                chunk_size=request.chunk_size,
                temperature=request.temperature,
                top_k=request.top_k,
                top_p=request.top_p,
                repetition_penalty=request.repetition_penalty,
                append_silence=request.append_silence,
                max_new_tokens=request.max_new_tokens,
                non_streaming_mode=False,
                parity_mode=True,
            ):
                pcm_bytes = _audio_chunk_to_pcm16_bytes(audio_chunk)
                if not pcm_bytes:
                    continue
                pcm_parts.append(pcm_bytes)
                sample_rate = int(sr or sample_rate or DEFAULT_SAMPLE_RATE)
        except Exception as exc:
            print(
                "[TTS SSE] single-audio streaming synthesis error "
                f"id={request_id} elapsed_ms={(time.perf_counter() - started_at) * 1000:.1f} error={exc}"
            )
            yield _sse_data({"type": "error", "message": str(exc) or "TTS stream failed."})
            return

        pcm_bytes = _even_pcm16_bytes(b"".join(pcm_parts))
        if not pcm_bytes:
            yield _sse_data({"type": "error", "message": "TTS generation returned no audio."})
            return

        duration_seconds = _pcm16_duration_seconds(pcm_bytes, sample_rate)
        print(
            "[TTS SSE] single-audio streaming synthesis ready "
            f"id={request_id} elapsed_ms={(time.perf_counter() - started_at) * 1000:.1f} "
            f"sample_rate={sample_rate} bytes={len(pcm_bytes)} duration_ms={duration_seconds * 1000:.1f}"
        )
        yield _sse_data(
            {
                "type": "chunk",
                "chunk_index": 0,
                "audio_b64": base64.b64encode(pcm_bytes).decode("utf-8"),
                "sample_rate": sample_rate,
                "timing": {
                    "mode": "single_audio_stream_buffered",
                    "sse_chunk_duration_ms": round(duration_seconds * 1000, 1),
                },
            }
        )
        yield _sse_data({"type": "done"})
        return

    if not hasattr(provider, "generate_audio"):
        yield _sse_data({"type": "error", "message": "TTS provider batch generation is unavailable."})
        return

    print(f"[TTS SSE] single-audio batch synthesis start id={request_id} chars={len(text)} speaker={request.speaker or 'default'}")
    result = provider.generate_audio(
        text=text,
        speaker=request.speaker,
        language=request.language or "en",
        temperature=request.temperature,
        top_k=request.top_k,
        top_p=request.top_p,
        repetition_penalty=request.repetition_penalty,
        append_silence=request.append_silence,
        max_new_tokens=request.max_new_tokens,
        # Keep the transport as one smooth SSE audio payload, but avoid the
        # provider's non-streaming prompt layout, which can hit causal-mask
        # shape mismatches for short streamed sentence batches.
        non_streaming_mode=False,
        parity_mode=True,
    )
    if not isinstance(result, dict) or not result.get("success") or result.get("fallback") or result.get("is_fallback"):
        fallback = result if isinstance(result, dict) else {}
        message = str(fallback.get("error") or fallback.get("fallback_reason") or "TTS generation failed.")
        print(
            "[TTS SSE] single-audio batch synthesis error "
            f"id={request_id} elapsed_ms={(time.perf_counter() - started_at) * 1000:.1f} error={message}"
        )
        yield _sse_data({"type": "error", "message": message})
        return

    encoded = result.get("audio_base64") or result.get("audio")
    if not isinstance(encoded, str) or not encoded.strip():
        yield _sse_data({"type": "error", "message": "TTS generation returned no audio."})
        return

    try:
        audio_bytes = base64.b64decode(encoded)
        pcm_bytes, sample_rate = _wav_or_pcm16_bytes(audio_bytes, int(result.get("sample_rate") or DEFAULT_SAMPLE_RATE))
    except Exception as exc:
        print(
            "[TTS SSE] single-audio batch decode error "
            f"id={request_id} elapsed_ms={(time.perf_counter() - started_at) * 1000:.1f} error={exc}"
        )
        yield _sse_data({"type": "error", "message": str(exc) or "TTS audio could not be decoded."})
        return

    duration_seconds = _pcm16_duration_seconds(pcm_bytes, sample_rate)
    print(
        "[TTS SSE] single-audio batch synthesis ready "
        f"id={request_id} elapsed_ms={(time.perf_counter() - started_at) * 1000:.1f} "
        f"sample_rate={sample_rate} bytes={len(pcm_bytes)} duration_ms={duration_seconds * 1000:.1f}"
    )
    yield _sse_data(
        {
            "type": "chunk",
            "chunk_index": 0,
            "audio_b64": base64.b64encode(pcm_bytes).decode("utf-8"),
            "sample_rate": sample_rate,
            "timing": {"mode": "single_audio", "sse_chunk_duration_ms": round(duration_seconds * 1000, 1)},
        }
    )
    yield _sse_data({"type": "done"})


def _pcm16_duration_seconds(pcm_bytes: bytes, sample_rate: int) -> float:
    """Return mono PCM16 duration, guarding invalid provider sample rates."""
    if sample_rate <= 0:
        return 0.0
    return len(pcm_bytes) / 2 / sample_rate


def _stream_pcm16_blocks(
    chunks: Iterator[tuple[bytes, int, Any]],
    *,
    block_samples: int = STREAM_OUTPUT_BLOCK_SAMPLES,
    silence_threshold: float = STREAM_INITIAL_SILENCE_THRESHOLD,
    preroll_ms: float = STREAM_INITIAL_PREROLL_MS,
) -> Iterator[tuple[bytes, int, Any]]:
    """Repack provider chunks into steady PCM16 blocks without altering joins."""
    block_bytes = max(1, int(block_samples)) * 2
    leftover = b""
    leftover_rate = DEFAULT_SAMPLE_RATE
    leftover_timing: Any = {}
    found_speech = False

    for pcm_bytes, sample_rate, timing in chunks:
        sample_rate = int(sample_rate or DEFAULT_SAMPLE_RATE)
        pcm_bytes = _even_pcm16_bytes(pcm_bytes)
        if not pcm_bytes:
            continue

        if leftover and sample_rate != leftover_rate:
            yield _pad_pcm16_block(leftover, block_bytes), leftover_rate, leftover_timing
            leftover = b""

        if not found_speech:
            start_byte = _initial_speech_start_byte(pcm_bytes, sample_rate, silence_threshold, preroll_ms)
            if start_byte is None:
                continue
            pcm_bytes = pcm_bytes[start_byte:]
            found_speech = True

        audio = leftover + pcm_bytes
        full_bytes = (len(audio) // block_bytes) * block_bytes
        for offset in range(0, full_bytes, block_bytes):
            yield audio[offset : offset + block_bytes], sample_rate, timing

        leftover = audio[full_bytes:]
        leftover_rate = sample_rate
        leftover_timing = timing

    if leftover:
        yield _pad_pcm16_block(leftover, block_bytes), leftover_rate, leftover_timing


def _even_pcm16_bytes(pcm_bytes: bytes) -> bytes:
    return pcm_bytes if len(pcm_bytes) % 2 == 0 else pcm_bytes[:-1]


def _initial_speech_start_byte(
    pcm_bytes: bytes,
    sample_rate: int,
    silence_threshold: float,
    preroll_ms: float,
) -> int | None:
    threshold = int(32768 * max(0.0, silence_threshold))
    preroll_samples = max(0, int(sample_rate * max(0.0, preroll_ms) / 1000.0))
    for index in range(0, len(pcm_bytes), 2):
        sample = int.from_bytes(pcm_bytes[index : index + 2], "little", signed=True)
        if abs(sample) > threshold:
            start_sample = max(0, index // 2 - preroll_samples)
            return start_sample * 2
    return None


def _pad_pcm16_block(pcm_bytes: bytes, block_bytes: int) -> bytes:
    if len(pcm_bytes) >= block_bytes:
        return pcm_bytes
    return pcm_bytes + (b"\x00" * (block_bytes - len(pcm_bytes)))


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


def _wav_or_pcm16_bytes(audio_bytes: bytes, fallback_sample_rate: int) -> tuple[bytes, int]:
    if audio_bytes[:4] != b"RIFF":
        return audio_bytes, fallback_sample_rate
    with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
        if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise ValueError("TTS WAV output must be mono PCM16 for SSE playback.")
        return wav_file.readframes(wav_file.getnframes()), wav_file.getframerate()


def _sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, sort_keys=True)}\n\n"


def _sse_comment(comment: str) -> str:
    return f": {comment}\n\n"
