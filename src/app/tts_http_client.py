from __future__ import annotations

import base64
import io
import os
import uuid
import wave
from typing import Any

import requests

from app.voice_debug import text_fingerprint, voice_debug_log, voice_debug_log_path


def _normalize_base_url(value: str | None, default: str) -> str:
    raw = (value or default).strip().strip('"').strip("'")
    raw = raw.replace(" ", "")
    return raw.rstrip("/")


def _tts_base_url() -> str:
    return _normalize_base_url(
        os.environ.get("OMNIX_TTS_URL"),
        "http://127.0.0.1:5101",
    )


def _trace_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4()}"


def tts_health(timeout: float = 5.0) -> dict[str, Any]:
    try:
        response = requests.get(f"{_tts_base_url()}/health", timeout=timeout)
        response.raise_for_status()
        data = response.json()
        data["reachable"] = True
        return data
    except (requests.RequestException, ValueError) as exc:
        return {
            "ok": False,
            "reachable": False,
            "error": str(exc),
            "provider": "tts-http",
        }


def tts_speakers(timeout: float = 10.0) -> dict[str, Any]:
    trace_id = _trace_id("tts-speakers")
    endpoint = f"{_tts_base_url()}/api/tts/speakers"
    voice_debug_log(
        "backend",
        "tts_speakers_request",
        trace_id=trace_id,
        endpoint=endpoint,
        log_path=voice_debug_log_path("backend"),
    )
    try:
        response = requests.get(endpoint, timeout=timeout)
        voice_debug_log(
            "backend",
            "tts_speakers_response",
            trace_id=trace_id,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            response_bytes=len(response.content),
        )
        response.raise_for_status()
        data = response.json()
        speakers = data.get("speakers") if isinstance(data, dict) else None
        voice_debug_log(
            "backend",
            "tts_speakers_decoded",
            trace_id=trace_id,
            speaker_ids=[
                str(row.get("id") or row.get("name") or "")
                for row in speakers
                if isinstance(row, dict)
            ][:100] if isinstance(speakers, list) else [],
        )
        return data
    except (requests.RequestException, ValueError) as exc:
        voice_debug_log(
            "backend",
            "tts_speakers_failed",
            trace_id=trace_id,
            error=exc,
        )
        return {
            "success": False,
            "speakers": [],
            "provider": "tts-http",
            "error": str(exc),
            "reachable": False,
        }


def tts_generate_audio(
    *,
    text: str,
    speaker: str,
    language: str = "en",
    speed: float = 1.0,
    pitch: float = 0.0,
    emotion: str = "neutral",
    timeout: float = 120.0,
) -> dict[str, Any]:
    trace_id = _trace_id("tts-audio")
    endpoint = f"{_tts_base_url()}/api/tts/generate_audio"
    payload = {
        "text": text,
        "speaker": speaker,
        "language": language,
        "speed": speed,
        "pitch": pitch,
        "emotion": emotion,
        "trace_id": trace_id,
    }
    voice_debug_log(
        "backend",
        "tts_audio_forwarded",
        trace_id=trace_id,
        endpoint=endpoint,
        speaker=speaker,
        language=language,
        text_chars=len(text),
        text_fingerprint=text_fingerprint(text),
        log_path=voice_debug_log_path("backend"),
    )
    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
        voice_debug_log(
            "backend",
            "tts_audio_response",
            trace_id=trace_id,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            response_bytes=len(response.content),
        )
        response.raise_for_status()
        result = response.json()
        voice_debug_log(
            "backend",
            "tts_audio_decoded",
            trace_id=trace_id,
            success=bool(result.get("success")) if isinstance(result, dict) else None,
            is_fallback=bool(result.get("is_fallback")) if isinstance(result, dict) else None,
            provider=result.get("provider") if isinstance(result, dict) else None,
            error=result.get("error") if isinstance(result, dict) else None,
        )
        return result
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        voice_debug_log(
            "backend",
            "tts_audio_failed",
            trace_id=trace_id,
            speaker=speaker,
            error=exc,
        )
        raise


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
) -> dict[str, Any]:
    trace_id = _trace_id("tts-stream")
    endpoint = f"{_tts_base_url()}/api/tts/generate_stream_audio"
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
        "trace_id": trace_id,
    }
    voice_debug_log(
        "backend",
        "tts_stream_forwarded",
        trace_id=trace_id,
        endpoint=endpoint,
        speaker=speaker,
        language=language,
        text_chars=len(text),
        text_fingerprint=text_fingerprint(text),
        chunk_size=chunk_size,
        log_path=voice_debug_log_path("backend"),
    )
    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=timeout,
        )
        content_type = (response.headers.get("content-type") or "").lower()
        voice_debug_log(
            "backend",
            "tts_stream_response",
            trace_id=trace_id,
            status_code=response.status_code,
            content_type=content_type,
            response_bytes=len(response.content),
            response_trace_id=response.headers.get("x-omnix-voice-trace", ""),
        )
        response.raise_for_status()
        if content_type and not content_type.startswith("application/json"):
            audio_bytes = response.content
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            sample_rate = 24000
            try:
                with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
                    parsed_sample_rate = int(wav_file.getframerate())
                    if parsed_sample_rate <= 0:
                        raise wave.Error("Invalid stream sample rate")
                    sample_rate = parsed_sample_rate
            except (wave.Error, EOFError) as exc:
                voice_debug_log(
                    "backend",
                    "tts_stream_invalid_audio",
                    trace_id=trace_id,
                    error=exc,
                    response_bytes=len(audio_bytes),
                )
                raise RuntimeError(f"Invalid audio stream response: {exc}") from exc
            voice_debug_log(
                "backend",
                "tts_stream_audio_ready",
                trace_id=trace_id,
                sample_rate=sample_rate,
                response_bytes=len(audio_bytes),
            )
            return {
                "success": True,
                "sample_rate": sample_rate,
                "audio": audio_b64,
                "chunks": [audio_b64] if audio_b64 else [],
                "format": content_type,
                "trace_id": trace_id,
            }
        result = response.json()
        voice_debug_log(
            "backend",
            "tts_stream_json_response",
            trace_id=trace_id,
            success=bool(result.get("success")) if isinstance(result, dict) else None,
            is_fallback=bool(result.get("is_fallback")) if isinstance(result, dict) else None,
            provider=result.get("provider") if isinstance(result, dict) else None,
            error=result.get("error") if isinstance(result, dict) else None,
        )
        return result
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        voice_debug_log(
            "backend",
            "tts_stream_failed",
            trace_id=trace_id,
            speaker=speaker,
            error=exc,
        )
        raise


def tts_voice_clone(
    *,
    voice_id: str,
    gender: str = "neutral",
    language: str = "en",
    ref_text: str = "",
    audio_bytes: bytes | None = None,
    filename: str = "voice.wav",
    timeout: float = 120.0,
) -> dict[str, Any]:
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