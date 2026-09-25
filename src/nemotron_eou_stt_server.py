"""Omnix STT service: Nemotron streaming transcript + Parakeet Realtime EOU."""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import subprocess
import time
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.providers.nemotron_eou_live_websocket import (
    PROVIDER_NAME,
    install_nemotron_eou_websocket,
)
from app.providers.nemotron_eou_quality import quality_model_manager as model_manager
from app.providers.nemotron_eou_streaming import SAMPLE_RATE

app = FastAPI(
    title="Omnix Nemotron + Parakeet EOU STT",
    description="Nemotron owns transcripts; Parakeet Realtime EOU owns turn-end detection.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_nemotron_eou_websocket(app, manager=model_manager)


@app.on_event("startup")
async def warm_hybrid_stt() -> None:
    await asyncio.to_thread(model_manager.warm_streaming_runtime)


@app.get("/health")
async def health() -> dict[str, object]:
    details = model_manager.health_details()
    return {
        "ok": model_manager.loaded,
        "status": "ready" if model_manager.loaded else "loading",
        "provider": PROVIDER_NAME,
        "details": details,
    }


@app.get("/authorityz")
async def authorityz(language: str = "en", mode: str = "auto") -> dict[str, object]:
    normalized_language = language.strip().lower()
    english = normalized_language in {"en", "en-us", "en_us", "english"}
    ready = model_manager.loaded
    reasons: list[str] = []
    if not english:
        reasons.append("parakeet_eou_english_only")
    if not ready:
        reasons.append("hybrid_models_not_ready")
    return {
        "ok": ready,
        "eligible": ready and english,
        "mode": mode,
        "provider": PROVIDER_NAME,
        "reasons": reasons,
    }


def _wav_pcm16_mono_16k(payload: bytes) -> tuple[bytes, float] | None:
    try:
        with wave.open(io.BytesIO(payload), "rb") as wav_file:
            if (
                wav_file.getnchannels() != 1
                or wav_file.getsampwidth() != 2
                or wav_file.getframerate() != SAMPLE_RATE
            ):
                return None
            frames = wav_file.readframes(wav_file.getnframes())
            return frames, len(frames) / 2 / SAMPLE_RATE
    except (EOFError, wave.Error):
        return None


def _decode_audio(payload: bytes, filename: str) -> tuple[bytes, float]:
    direct = _wav_pcm16_mono_16k(payload)
    if direct is not None:
        return direct
    ffmpeg = _ffmpeg_binary()
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "cache:pipe:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                "-f",
                "s16le",
                "pipe:1",
            ],
            input=payload,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"FFmpeg executable is unavailable: {ffmpeg}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("FFmpeg timed out while decoding the uploaded audio") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"FFmpeg could not decode {Path(filename or 'audio').name}"
            f"{': ' + detail if detail else ''}"
        )
    if not result.stdout:
        raise RuntimeError("FFmpeg decoded no audio samples")
    return result.stdout, len(result.stdout) / (2 * SAMPLE_RATE)


def _ffmpeg_binary() -> str:
    configured = os.environ.get("OMNIX_FFMPEG", "").strip()
    if configured and Path(configured).is_file():
        return configured
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    bundled = sorted(
        (
            Path(__file__).resolve().parents[1]
            / "venv"
            / "Lib"
            / "site-packages"
            / "imageio_ffmpeg"
            / "binaries"
        ).glob("ffmpeg*.exe")
    )
    if bundled:
        return str(bundled[-1])
    raise RuntimeError(
        "FFmpeg is required to decode uploaded audio; configure OMNIX_FFMPEG or add it to PATH"
    )


@app.post("/transcribe")
async def transcribe(
    file: UploadFile | None = File(default=None),  # noqa: B008 - FastAPI dependency default
    audio: UploadFile | None = File(default=None),  # noqa: B008 - FastAPI dependency default
    language: str | None = None,
) -> dict[str, object]:
    del language  # English-only runtime; kept for legacy client compatibility.
    upload = file or audio
    if upload is None:
        raise HTTPException(status_code=400, detail="audio_file_required")
    payload = await upload.read()
    if not payload:
        return {"success": False, "text": "", "segments": [], "duration": 0.0}
    try:
        pcm16, duration = await asyncio.to_thread(_decode_audio, payload, upload.filename or "audio.wav")
        started = time.perf_counter()
        text = await asyncio.to_thread(model_manager.transcribe_pcm16, pcm16)
        inference_ms = (time.perf_counter() - started) * 1000.0
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "success": bool(text),
        "text": text,
        "segments": [{"start": 0.0, "end": duration, "text": text}] if text else [],
        "duration": duration,
        "provider": PROVIDER_NAME,
        "inference_ms": round(inference_ms, 3),
    }


def main() -> None:
    port = int(os.environ.get("OMNIX_STT_PORT", "5201"))
    print(f"[STT] Starting {PROVIDER_NAME} on http://0.0.0.0:{port}")
    print("[STT] Nemotron is authoritative transcript; Parakeet Realtime EOU is endpoint-only")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
