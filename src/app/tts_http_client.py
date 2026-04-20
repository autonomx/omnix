from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional

import requests


def _tts_base_url() -> str:
    return os.environ.get("OMNIX_TTS_URL", "http://127.0.0.1:5101").strip().rstrip("/")


def tts_health(timeout: float = 5.0) -> Dict[str, Any]:
    try:
        response = requests.get(f"{_tts_base_url()}/health", timeout=timeout)
        response.raise_for_status()
        data = response.json()
        data["reachable"] = True
        return data
    except Exception as exc:
        return {
            "ok": False,
            "reachable": False,
            "error": str(exc),
            "provider": "tts-http",
        }


def tts_speakers(timeout: float = 10.0) -> Dict[str, Any]:
    response = requests.get(f"{_tts_base_url()}/api/tts/speakers", timeout=timeout)
    response.raise_for_status()
    return response.json()


def tts_generate_stream_audio(
    *,
    text: str,
    speaker: str,
    language: str = "English",
    chunk_size: int = 6,
    temperature: float = 0.6,
    top_k: int = 20,
    top_p: float = 0.85,
    repetition_penalty: float = 1.0,
    append_silence: bool = False,
    max_new_tokens: int = 180,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    payload = {
        "text": text,
        "speaker": speaker,
        "language": language,
        "chunk_size": chunk_size,
        "temperature": temperature,
        "top_k": top_k,
        "top_p": top_p,
        "repetition_penalty": repetition_penalty,
        "append_silence": append_silence,
        "max_new_tokens": max_new_tokens,
    }
    response = requests.post(
        f"{_tts_base_url()}/api/tts/generate_stream_audio",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def tts_generate_audio(
    *,
    text: str,
    speaker: str,
    language: str = "en",
    speed: float = 1.0,
    pitch: float = 0.0,
    emotion: str = "neutral",
    timeout: float = 120.0,
) -> Dict[str, Any]:
    payload = {
        "text": text,
        "speaker": speaker,
        "language": language,
        "speed": speed,
        "pitch": pitch,
        "emotion": emotion,
    }
    response = requests.post(
        f"{_tts_base_url()}/api/tts/generate_audio",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def tts_voice_clone(
    *,
    voice_id: str,
    gender: str = "neutral",
    language: str = "en",
    ref_text: str = "",
    audio_bytes: Optional[bytes] = None,
    filename: str = "voice.wav",
    timeout: float = 120.0,
) -> Dict[str, Any]:
    data = {
        "voice_id": voice_id,
        "gender": gender,
        "language": language,
        "ref_text": ref_text,
    }
    files = None
    if audio_bytes:
        files = {
            "file": (filename, audio_bytes, "audio/wav"),
        }
    response = requests.post(
        f"{_tts_base_url()}/api/tts/voice_clone",
        data=data,
        files=files,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def decode_float32_audio_base64(audio_base64: str) -> bytes:
    return base64.b64decode(audio_base64)