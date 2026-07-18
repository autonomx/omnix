"""Incremental PCM streaming route installed into the dedicated TTS service.

The route is registered lazily when ``app.providers`` is imported by
``src/tts_server.py`` during provider startup. Keeping the model and waveform
decoder in that process prevents their Python/C-extension work from starving
the browser-facing gateway event loop.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from collections.abc import Iterator
from typing import Any

from fastapi.responses import StreamingResponse

_ROUTE_SENTINEL = "_omnix_pcm_stream_route_registered"
PCM_STREAM_PATH = "/api/tts/generate_pcm_stream"
PCM_STREAM_MEDIA_TYPE = "application/x-ndjson"


def _pcm16_bytes(audio_chunk: Any) -> bytes:
    if audio_chunk is None:
        return b""
    if isinstance(audio_chunk, bytes):
        return audio_chunk
    if isinstance(audio_chunk, (bytearray, memoryview)):
        return bytes(audio_chunk)

    import numpy as np

    values = np.asarray(audio_chunk, dtype=np.float32)
    if values.size == 0:
        return b""
    if values.ndim > 1:
        values = values[..., 0]
    values = np.ascontiguousarray(values.reshape(-1), dtype=np.float32)
    np.nan_to_num(values, copy=False, nan=0.0, posinf=1.0, neginf=-1.0)
    np.clip(values, -1.0, 1.0, out=values)
    return (values * 32767.0).astype("<i2", copy=False).tobytes()


def _line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n").encode(
        "utf-8"
    )


def iter_pcm_stream_lines(provider: Any, request: Any) -> Iterator[bytes]:
    """Yield one NDJSON record per provider waveform chunk."""
    started_at = time.perf_counter()
    chunk_count = 0
    sample_count = 0
    try:
        stream = provider.generate_audio_stream(
            text=request.text,
            speaker=request.speaker,
            language=request.language,
            chunk_size=request.chunk_size,
            temperature=request.temperature,
            top_k=request.top_k,
            top_p=request.top_p,
            repetition_penalty=request.repetition_penalty,
            append_silence=request.append_silence,
            max_new_tokens=request.max_new_tokens,
            non_streaming_mode=False,
            parity_mode=getattr(request, "parity_mode", False),
        )
        for audio_chunk, sample_rate, timing in stream:
            pcm = _pcm16_bytes(audio_chunk)
            if not pcm:
                continue
            resolved_rate = int(sample_rate or 24_000)
            samples = len(pcm) // 2
            sample_count += samples
            worker_elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
            yield _line(
                {
                    "type": "chunk",
                    "chunk_index": chunk_count,
                    "sample_rate": resolved_rate,
                    "samples": samples,
                    "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                    "provider_timing": timing if isinstance(timing, dict) else {},
                    "worker_elapsed_ms": worker_elapsed_ms,
                    "worker_process_id": os.getpid(),
                }
            )
            chunk_count += 1
        yield _line(
            {
                "type": "done",
                "chunk_count": chunk_count,
                "samples": sample_count,
                "worker_elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "worker_process_id": os.getpid(),
            }
        )
    except GeneratorExit:
        raise
    except Exception as exc:
        yield _line(
            {
                "type": "error",
                "error_type": type(exc).__name__,
                "message": str(exc) or "tts_worker_stream_failed",
                "chunk_count": chunk_count,
                "worker_elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "worker_process_id": os.getpid(),
            }
        )


def _tts_server_module() -> Any | None:
    direct = sys.modules.get("tts_server")
    if direct is not None and hasattr(direct, "app"):
        return direct
    main = sys.modules.get("__main__")
    main_file = str(getattr(main, "__file__", "") or "").replace("\\", "/")
    if main is not None and main_file.endswith("/tts_server.py") and hasattr(main, "app"):
        return main
    return None


def install_tts_service_streaming_routes() -> bool:
    """Attach the PCM route when running inside the dedicated TTS service."""
    module = _tts_server_module()
    if module is None:
        return False
    app = module.app
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return True
    setattr(app.state, _ROUTE_SENTINEL, True)

    async def generate_pcm_stream(request: module.TtsGenerateStreamRequest) -> StreamingResponse:
        provider = module._require_provider()
        return StreamingResponse(
            iter_pcm_stream_lines(provider, request),
            media_type=PCM_STREAM_MEDIA_TYPE,
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    app.post(PCM_STREAM_PATH, include_in_schema=False)(generate_pcm_stream)
    print(f"[TTS SERVER] registered incremental PCM stream route: {PCM_STREAM_PATH}")
    return True
