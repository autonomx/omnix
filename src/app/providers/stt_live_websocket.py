"""Persistent low-latency WebSocket route for live Parakeet transcription."""
from __future__ import annotations

import asyncio
import base64
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIWebSocketRoute

from app.providers.stt_live_runtime_support import (
    env_float,
    env_int,
    metric,
    transcribe_path,
    warmed,
)
from app.providers.stt_streaming_audio import (
    DEFAULT_SAMPLE_RATE,
    pcm16_duration_ms,
    trim_pcm16_edge_silence,
    write_pcm16_wav,
)


def _remove_existing_route(app: Any) -> None:
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if not (isinstance(route, APIWebSocketRoute) and route.path == "/ws/transcribe")
    ]


async def _transcribe_raw_pcm(
    legacy: Any,
    combined_audio: bytes,
    session_dir: Path,
) -> tuple[str, dict[str, float | int | bool]]:
    prepare_started_at = time.perf_counter()
    trimmed_audio, trim = trim_pcm16_edge_silence(
        combined_audio,
        silence_threshold_dbfs=env_float("PARAKEET_LIVE_TRIM_DBFS", -40.0),
        edge_padding_ms=env_int("PARAKEET_LIVE_EDGE_PADDING_MS", 100),
    )
    audio_path = write_pcm16_wav(session_dir / "audio.wav", trimmed_audio)
    prepare_ms = (time.perf_counter() - prepare_started_at) * 1000.0
    text, inference_ms = await asyncio.to_thread(transcribe_path, legacy.model, audio_path)
    return text, {
        "prepare_ms": round(prepare_ms, 3),
        "inference_ms": round(inference_ms, 3),
        "original_audio_ms": round(pcm16_duration_ms(combined_audio), 3),
        "transcribed_audio_ms": round(pcm16_duration_ms(trimmed_audio), 3),
        "removed_audio_ms": round(trim.removed_samples / DEFAULT_SAMPLE_RATE * 1000.0, 3),
        "speech_detected": trim.speech_detected,
        "original_bytes": len(combined_audio),
        "transcribed_bytes": len(trimmed_audio),
    }


async def _transcribe_compatible_audio(
    legacy: Any,
    combined_audio: bytes,
    session_dir: Path,
) -> tuple[str, dict[str, float | int | bool]]:
    prepare_started_at = time.perf_counter()
    if len(combined_audio) > 44 and combined_audio[:4] == b"RIFF":
        audio_path = session_dir / "audio.wav"
        audio_path.write_bytes(combined_audio)
    else:
        input_path = session_dir / "audio.webm"
        input_path.write_bytes(combined_audio)
        audio = legacy.AudioSegment.from_file(input_path)
        audio = audio.set_frame_rate(DEFAULT_SAMPLE_RATE).set_channels(1)
        audio_path = session_dir / "audio.wav"
        audio.export(audio_path, format="wav")
    prepare_ms = (time.perf_counter() - prepare_started_at) * 1000.0
    text, inference_ms = await asyncio.to_thread(transcribe_path, legacy.model, audio_path)
    return text, {
        "prepare_ms": round(prepare_ms, 3),
        "inference_ms": round(inference_ms, 3),
        "original_audio_ms": 0.0,
        "transcribed_audio_ms": 0.0,
        "removed_audio_ms": 0.0,
        "speech_detected": True,
        "original_bytes": len(combined_audio),
        "transcribed_bytes": audio_path.stat().st_size,
    }


def install_live_stt_websocket(legacy: Any) -> None:
    app = legacy.app
    _remove_existing_route(app)

    @app.websocket("/ws/transcribe")
    async def websocket_transcribe(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"type": "ready"})
        audio_chunks: list[bytes] = []
        try:
            while True:
                data = await websocket.receive_json()
                message_type = data.get("type", "")
                if message_type == "audio":
                    encoded_audio = data.get("data", "")
                    if encoded_audio:
                        audio_chunks.append(base64.b64decode(encoded_audio))
                    continue
                if message_type != "final":
                    continue

                final_started_at = time.perf_counter()
                if not audio_chunks:
                    await websocket.send_json({"type": "done", "text": ""})
                    continue
                if legacy.model is None:
                    await websocket.send_json({"type": "error", "error": "ASR model not loaded"})
                    audio_chunks.clear()
                    continue

                combined_audio = b"".join(audio_chunks)
                audio_chunks.clear()
                session_dir = Path(tempfile.gettempdir()) / f"ws_transcription_{uuid.uuid4()}"
                session_dir.mkdir(parents=True, exist_ok=True)
                try:
                    is_wav = len(combined_audio) > 44 and combined_audio[:4] == b"RIFF"
                    is_webm = len(combined_audio) > 4 and combined_audio[:4] in {
                        b"\x1a\x45\xdf\xa3",
                        b"ftyp",
                    }
                    raw_pcm = not is_wav and not is_webm
                    if raw_pcm:
                        text, metrics = await _transcribe_raw_pcm(legacy, combined_audio, session_dir)
                    else:
                        text, metrics = await _transcribe_compatible_audio(legacy, combined_audio, session_dir)
                    send_started_at = time.perf_counter()
                    await websocket.send_json({"type": "done", "text": text})
                    metric(
                        "stt_websocket_final_completed",
                        total_ms=round((time.perf_counter() - final_started_at) * 1000.0, 3),
                        send_ms=round((time.perf_counter() - send_started_at) * 1000.0, 3),
                        warmed=warmed(),
                        device=str(legacy.device),
                        raw_pcm=raw_pcm,
                        transcript_chars=len(text),
                        **metrics,
                    )
                except Exception as exc:
                    metric(
                        "stt_websocket_final_failed",
                        total_ms=round((time.perf_counter() - final_started_at) * 1000.0, 3),
                        error_type=type(exc).__name__,
                    )
                    await websocket.send_json({"type": "error", "error": str(exc)})
                finally:
                    legacy.cleanup_session_dir(session_dir)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            metric("stt_websocket_failed", error_type=type(exc).__name__)
            try:
                await websocket.send_json({"type": "error", "error": str(exc)})
            except Exception:
                pass
