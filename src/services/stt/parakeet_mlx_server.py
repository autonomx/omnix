"""The desktop app's speech service on macOS: Parakeet-MLX (desktop roadmap D-5, §4.7, DT-8.2).

    python -S -m app.desktop.service_boot stt-mlx      (the supervisor starts it so; it runs ``main``)

The same HTTP and websocket contract as the Windows service (``nemotron_eou_stt_server``), so the gateway and the
browser need no Mac-specific path:

- ``GET /health`` and ``GET /authorityz``;
- ``POST /transcribe``: one upload, transcribed whole;
- ``/ws/transcribe``: segmented live audio (PCM16 mono 16 kHz, JSON or binary frames), with partial transcripts,
  ``endpoint_candidate`` at the end of an utterance, and the authoritative ``result_available`` on finalize.

Parakeet-MLX transcribes but does not report the end of an utterance, so ``energy_endpointing`` detects it from the
audio. The model loads by repository id from the pinned, offline Hugging Face cache, like NeMo's on Windows.
"""
from __future__ import annotations

import asyncio
import io
import tempfile
import threading
import time
import uuid
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect

from app.config.env import env_int, env_str
from app.providers.live_stt_contracts import (
    CAP_AUTHORITATIVE_EOU, CAP_AUTHORITATIVE_FINAL, CAP_BINARY_AUDIO_FRAMES, CAP_PARTIAL_TRANSCRIPTS, CAP_RESULT_REPLAY,
    CAP_SEGMENTED_AUDIO, LiveSttNegotiation, audio_message_pcm, receive_client_message,
)
from app.runtime.net import allowed_origins, bind_host
from app.security.model_service import ModelServiceMiddleware
from services.stt.energy_endpointing import SAMPLE_RATE, EnergyEndpointer

PROVIDER_NAME = "parakeet-mlx"
# The segmented live protocol the Windows service and the gateway speak (nemotron_eou_live_websocket).
SEGMENTED_PROTOCOL = "segmented-v1"
MODEL_REPO = "mlx-community/parakeet-tdt-0.6b-v3"
FRAME_SAMPLES = 2560  # 160 ms, as the Windows service feeds Nemotron
# A partial transcript after this much new audio (Parakeet-TDT 0.6B on MLX runs far faster than real time).
PARTIAL_EVERY_SAMPLES = SAMPLE_RATE
MAX_SEGMENT_SECONDS = 120

NEGOTIATION = LiveSttNegotiation(
    provider=PROVIDER_NAME,
    protocol=SEGMENTED_PROTOCOL,
    sample_rate=SAMPLE_RATE,
    frame_samples=FRAME_SAMPLES,
    capabilities=frozenset({CAP_SEGMENTED_AUDIO, CAP_AUTHORITATIVE_FINAL, CAP_RESULT_REPLAY, CAP_PARTIAL_TRANSCRIPTS,
                            CAP_AUTHORITATIVE_EOU, CAP_BINARY_AUDIO_FRAMES}),
)


class Transcriber(Protocol):
    loaded: bool

    def load(self) -> None: ...

    def transcribe_pcm16(self, pcm16: bytes) -> str: ...


class MlxParakeet:
    """Parakeet-TDT on MLX, loaded on first use (Apple Silicon only)."""

    def __init__(self, repo: str = MODEL_REPO) -> None:
        self.repo = repo
        self.model: Any = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        with self._lock:
            if self.model is None:
                from parakeet_mlx import from_pretrained

                self.model = from_pretrained(self.repo)

    def transcribe_pcm16(self, pcm16: bytes) -> str:
        self.load()
        if not pcm16:
            return ""
        with tempfile.TemporaryDirectory(prefix="omnix-mlx-stt-") as folder:
            path = Path(folder) / "segment.wav"
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(SAMPLE_RATE)
                writer.writeframes(pcm16)
            with self._lock:
                result = self.model.transcribe(str(path))
        return str(getattr(result, "text", "") or "").strip()


@dataclass
class Segment:
    segment_id: str
    sequence: int
    audio: bytearray = field(default_factory=bytearray)
    endpointer: EnergyEndpointer = field(default_factory=EnergyEndpointer)
    since_partial: int = 0
    last_partial: str = ""
    finalized: bool = False


def _decode_upload(payload: bytes) -> bytes:
    """PCM16 mono 16 kHz from a WAV at that format, or through ffmpeg."""
    try:
        with wave.open(io.BytesIO(payload), "rb") as reader:
            if reader.getnchannels() == 1 and reader.getsampwidth() == 2 and reader.getframerate() == SAMPLE_RATE:
                return reader.readframes(reader.getnframes())
    except (EOFError, wave.Error):
        pass
    import shutil
    import subprocess

    ffmpeg = (env_str("OMNIX_FFMPEG", "") or "").strip() or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to decode uploaded audio; configure OMNIX_FFMPEG or add it to PATH")
    completed = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar",
                                str(SAMPLE_RATE), "-f", "s16le", "pipe:1"], input=payload, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError("the audio could not be decoded")
    return completed.stdout


def create_app(transcriber: Transcriber | None = None, *, preload: bool = True,
               clock: Callable[[], float] = time.perf_counter) -> FastAPI:
    model = transcriber or MlxParakeet()
    app = FastAPI(title="Omnix Parakeet-MLX STT", version="1.0.0",
                  description="Parakeet-TDT on MLX; the end of an utterance comes from audio energy.")
    app.add_middleware(CORSMiddleware, allow_origins=allowed_origins(), allow_credentials=True, allow_methods=["*"],
                       allow_headers=["*"])
    app.add_middleware(ModelServiceMiddleware)

    if preload:
        @app.on_event("startup")
        async def warm() -> None:
            await asyncio.to_thread(model.load)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"ok": model.loaded, "status": "ready" if model.loaded else "loading", "provider": PROVIDER_NAME,
                "details": {"model": MODEL_REPO, "endpointing": "energy"}}

    @app.get("/authorityz")
    def authorityz(language: str = "en", mode: str = "auto") -> dict[str, object]:
        ready = model.loaded
        return {"ok": ready, "eligible": ready, "mode": mode, "provider": PROVIDER_NAME,
                "reasons": [] if ready else ["parakeet_mlx_not_ready"]}

    @app.post("/transcribe")
    async def transcribe(file: UploadFile | None = File(default=None),  # noqa: B008 - FastAPI dependency default
                         audio: UploadFile | None = File(default=None),  # noqa: B008
                         language: str | None = None) -> dict[str, object]:
        del language  # Parakeet-TDT v3 detects the language itself.
        upload = file or audio
        if upload is None:
            raise HTTPException(status_code=400, detail="audio_file_required")
        payload = await upload.read()
        if not payload:
            return {"success": False, "text": "", "segments": [], "duration": 0.0}
        try:
            pcm = await asyncio.to_thread(_decode_upload, payload)
            started = clock()
            text = await asyncio.to_thread(model.transcribe_pcm16, pcm)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="model_service_error") from exc
        duration = len(pcm) / 2 / SAMPLE_RATE
        return {"success": bool(text), "text": text, "duration": duration, "provider": PROVIDER_NAME,
                "segments": [{"start": 0.0, "end": duration, "text": text}] if text else [],
                "inference_ms": round((clock() - started) * 1000.0, 3)}

    @app.websocket("/ws/transcribe")
    async def websocket_transcribe(websocket: WebSocket) -> None:
        await websocket.accept()
        connection_id = uuid.uuid4().hex
        session_id = f"connection-{connection_id}"
        segments: dict[str, Segment] = {}
        results: dict[int, dict[str, Any]] = {}
        await websocket.send_json(NEGOTIATION.ready_payload(connection_id=connection_id, language="auto"))
        try:
            while True:
                data = await receive_client_message(websocket)
                kind = str(data.get("type", ""))
                if kind == "hello":
                    session_id = str(data.get("sessionId") or data.get("session_id") or session_id)[:120]
                    await websocket.send_json({"type": "session_ready", "sessionId": session_id, "provider": PROVIDER_NAME})
                elif kind == "audio":
                    await _audio(websocket, data, segments, model)
                elif kind in {"final", "finalize"}:
                    await _finalize(websocket, data, segments, results, model, session_id, clock)
        except WebSocketDisconnect:
            return

    return app


async def _audio(websocket: WebSocket, data: dict[str, Any], segments: dict[str, Segment], model: Transcriber) -> None:
    segment_id = str(data.get("segmentId") or data.get("segment_id") or "")[:120]
    sequence = int(data.get("sequence", 0))
    if not segment_id:
        await websocket.send_json({"type": "error", "error": "segment_id_required"})
        return
    if int(data.get("sampleRate") or data.get("sample_rate") or SAMPLE_RATE) != SAMPLE_RATE:
        await websocket.send_json({"type": "segment_error", "segmentId": segment_id, "sequence": sequence,
                                   "retryable": False, "errorCode": "sample_rate_mismatch",
                                   "error": f"Parakeet-MLX STT requires {SAMPLE_RATE} Hz PCM"})
        return
    segment = segments.setdefault(segment_id, Segment(segment_id, sequence))
    try:
        pcm = audio_message_pcm(data, validate=True)
    except Exception:  # noqa: BLE001 - a malformed frame is a protocol error, not a crash
        await websocket.send_json({"type": "segment_error", "segmentId": segment_id, "sequence": sequence,
                                   "retryable": False, "errorCode": "model_service_error", "error": "model_service_error"})
        return
    if len(segment.audio) + len(pcm) > MAX_SEGMENT_SECONDS * SAMPLE_RATE * 2:
        pcm = pcm[: max(0, MAX_SEGMENT_SECONDS * SAMPLE_RATE * 2 - len(segment.audio))]
    segment.audio.extend(pcm)
    segment.since_partial += len(pcm) // 2
    await websocket.send_json({"type": "audio_buffered", "segmentId": segment_id, "sequence": sequence,
                               "acceptedThroughSample": len(segment.audio) // 2})
    ended = segment.endpointer.feed(pcm)
    if segment.since_partial >= PARTIAL_EVERY_SAMPLES or ended:
        segment.since_partial = 0
        text = await asyncio.to_thread(model.transcribe_pcm16, bytes(segment.audio))
        if text and text != segment.last_partial:
            segment.last_partial = text
            await websocket.send_json({"type": "partial", "provider": PROVIDER_NAME, "segmentId": segment_id,
                                       "sequence": segment.sequence, "text": text})
    if ended:
        endpoint = {"provider": PROVIDER_NAME, "segmentId": segment_id, "sequence": segment.sequence,
                    "probability": 1.0, "modelTimeMs": round(len(segment.audio) / 2 / SAMPLE_RATE * 1000.0, 3),
                    "signal": "energy"}
        await websocket.send_json({"type": "endpoint_score", **endpoint})
        await websocket.send_json({"type": "endpoint_candidate", **endpoint})


async def _finalize(websocket: WebSocket, data: dict[str, Any], segments: dict[str, Segment],
                    results: dict[int, dict[str, Any]], model: Transcriber, session_id: str,
                    clock: Callable[[], float]) -> None:
    segment_id = str(data.get("segmentId") or data.get("segment_id") or "")[:120]
    sequence = int(data.get("sequence", 0))
    cached = results.get(sequence)
    if cached is not None:
        await websocket.send_json(cached)
        return
    segment = segments.get(segment_id)
    if segment is None:
        await websocket.send_json({"type": "segment_error", "segmentId": segment_id, "sequence": sequence,
                                   "retryable": True, "errorCode": "segment_missing", "error": "segment_missing"})
        return
    if segment.finalized:
        await websocket.send_json({"type": "finalize_queued", "segmentId": segment_id, "sequence": sequence})
        return
    segment.finalized = True
    await websocket.send_json({"type": "finalize_queued", "segmentId": segment_id, "sequence": sequence,
                               "queuedSegments": 0})
    started = clock()
    text = await asyncio.to_thread(model.transcribe_pcm16, bytes(segment.audio))
    result = {
        "type": "result_available", "provider": PROVIDER_NAME, "sessionId": session_id,
        "captureEpoch": str(data.get("captureEpoch") or data.get("capture_epoch") or "")[:160],
        "segmentId": segment_id, "sequence": segment.sequence, "resultId": uuid.uuid4().hex,
        "finalizeRequestId": str(data.get("finalizeRequestId") or data.get("finalize_request_id") or "")[:160],
        "startSample": 0, "endSample": int(data.get("endSample") or data.get("end_sample") or len(segment.audio) // 2),
        "text": text, "acceptedThroughSample": len(segment.audio) // 2,
        "providerMetrics": {"finalize_ms": round((clock() - started) * 1000.0, 3), "endpointing": "energy"},
    }
    results[sequence] = result
    segments.pop(segment_id, None)
    await websocket.send_json(result)


def main() -> None:
    import uvicorn

    from app.observability.logging import configure_logging

    configure_logging()
    host = bind_host()
    port = env_int("OMNIX_STT_PORT", 5201, minimum=1, maximum=65535)
    print(f"[STT] Starting {PROVIDER_NAME} on http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
