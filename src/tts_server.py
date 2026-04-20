#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
import json
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))

import app.shared as shared

from app.providers.vendor.qwen3_tts.runtime_status import validate_qwen3_tts_runtime


HOST = "127.0.0.1"
PORT = 5101

app = FastAPI(title="Omnix TTS Service")


def _get_tts_provider():
    provider = shared.get_tts_provider()
    if not provider:
        raise RuntimeError("No TTS provider available")
    return provider


@app.get("/health")
async def health():
    try:
        result = validate_qwen3_tts_runtime()
        return {
            "ok": bool(result.get("ready")),
            "status": result.get("status", "unknown"),
            "provider": result.get("provider", "qwen3_tts"),
            "details": result.get("details", {}),
            "error": result.get("error", ""),
        }
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "status": "not_ready",
                "error": str(exc),
                "provider": "tts-http",
                "details": {},
            },
            status_code=500,
        )


@app.get("/api/tts/speakers")
async def get_tts_speakers():
    try:
        provider = _get_tts_provider()
        if hasattr(provider, "get_speakers"):
            speakers = provider.get_speakers()
        elif hasattr(provider, "get_voices"):
            speakers = provider.get_voices()
        else:
            speakers = [{"id": "default", "name": "Default"}]
        return {"success": True, "speakers": speakers, "provider": provider.provider_name}
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/api/tts/generate_stream_audio")
async def generate_stream_audio(request: Request):
    try:
        data = await request.json()
        provider = _get_tts_provider()
        if not hasattr(provider, "generate_audio_stream"):
            return JSONResponse({"success": False, "error": "Provider missing generate_audio_stream"}, status_code=500)

        chunks = []
        sample_rate = 24000
        for audio_chunk, sr, _timing in provider.generate_audio_stream(
            text=data.get("text", ""),
            speaker=data.get("speaker", "default"),
            language=data.get("language", "English"),
            chunk_size=int(data.get("chunk_size", 6)),
            non_streaming_mode=False,
            temperature=float(data.get("temperature", 0.6)),
            top_k=int(data.get("top_k", 20)),
            top_p=float(data.get("top_p", 0.85)),
            repetition_penalty=float(data.get("repetition_penalty", 1.0)),
            append_silence=bool(data.get("append_silence", False)),
            max_new_tokens=int(data.get("max_new_tokens", 180)),
        ):
            if audio_chunk is None or len(audio_chunk) == 0:
                continue
            chunk = np.asarray(audio_chunk, dtype=np.float32)
            if chunk.ndim > 1:
                chunk = chunk.mean(axis=1)
            chunks.append(chunk.astype(np.float32, copy=False))
            sample_rate = int(sr or sample_rate)

        if chunks:
            audio = np.concatenate(chunks).astype(np.float32, copy=False)
        else:
            audio = np.array([], dtype=np.float32)

        return {
            "success": True,
            "sample_rate": sample_rate,
            "audio_format": "float32le_base64",
            "audio": base64.b64encode(audio.tobytes()).decode("ascii"),
        }
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/api/tts/generate_audio")
async def generate_audio(request: Request):
    try:
        data = await request.json()
        provider = _get_tts_provider()

        kwargs = {
            "text": data.get("text", ""),
            "speaker": data.get("speaker", "default"),
            "language": data.get("language", "en"),
            "speed": data.get("speed", 1.0),
            "pitch": data.get("pitch", 0.0),
            "emotion": data.get("emotion", "neutral"),
        }

        if hasattr(provider, "generate_tts"):
            result = provider.generate_tts(**kwargs)
        elif hasattr(provider, "generate_audio"):
            result = provider.generate_audio(**kwargs)
        else:
            return JSONResponse({"success": False, "error": "Provider missing generate_audio/generate_tts"}, status_code=500)

        return result
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


@app.post("/api/tts/voice_clone")
async def voice_clone(request: Request):
    try:
        form = await request.form()
        voice_id = (form.get("voice_id") or form.get("name") or "").strip()
        gender = form.get("gender", "neutral")
        language = form.get("language", "en")
        ref_text = form.get("ref_text", "")
        audio_file = form.get("file")

        if not voice_id:
            return JSONResponse({"success": False, "error": "Voice name is required"}, status_code=400)

        clones_dir = Path(shared.VOICE_CLONES_DIR)
        clones_dir.mkdir(parents=True, exist_ok=True)

        audio_bytes = b""
        if audio_file and hasattr(audio_file, "read"):
            audio_bytes = await audio_file.read()
            if audio_bytes:
                wav_path = clones_dir / f"{voice_id}.wav"
                wav_path.write_bytes(audio_bytes)

        provider = _get_tts_provider()
        if audio_bytes and hasattr(provider, "voice_clone"):
            provider.voice_clone(voice_id, audio_bytes, ref_text)

        shared.custom_voices[voice_id] = {
            "speaker": "default",
            "language": language,
            "voice_clone_id": voice_id,
            "has_audio": bool(audio_bytes),
            "is_preloaded": True,
            "gender": gender,
        }

        with open(shared.VOICE_CLONES_FILE, "w", encoding="utf-8") as f:
            json.dump(shared.custom_voices, f, indent=2)

        return {"success": True, "voice_id": voice_id}
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")