from __future__ import annotations

import base64
import io
import os
import traceback
import wave
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel


app = FastAPI(title="Omnix TTS Service", version="1.0")


class TtsGenerateRequest(BaseModel):
    text: str
    speaker: str = "default"
    language: str = "en"
    speed: float = 1.0
    pitch: float = 0.0
    emotion: str = "neutral"


class TtsGenerateStreamRequest(BaseModel):
    text: str
    speaker: str = "default"
    language: str = "en"
    chunk_size: int = 6
    temperature: float = 0.6
    top_k: int = 20
    top_p: float = 0.85
    repetition_penalty: float = 1.0
    append_silence: bool = False
    max_new_tokens: int = 180


class TtsVoiceCloneRequest(BaseModel):
    voice_id: str
    gender: str = "neutral"
    language: str = "en"
    ref_text: str = ""


_TTS_PROVIDER: Any = None
_TTS_PROVIDER_ERROR: str = ""
_TTS_PROVIDER_NAME: str = "qwen3_tts"


def _provider_payload_ok(details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "ok": True,
        "provider": _TTS_PROVIDER_NAME,
        "error": "",
        "details": dict(details or {}),
    }


def _provider_payload_fail(error: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "ok": False,
        "provider": _TTS_PROVIDER_NAME,
        "error": str(error),
        "details": dict(details or {}),
    }


def _load_qwen3_provider() -> Any:
    """
    Load the dedicated TTS provider.
    This function is intentionally isolated so failures stay local to the TTS service.
    """
    from app.shared import load_settings
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    settings = load_settings() or {}
    provider_settings = dict(settings.get("faster-qwen3-tts") or {})

    provider = FasterQwen3TTSProvider(config=provider_settings)
    return provider


def initialize_tts_provider() -> Dict[str, Any]:
    global _TTS_PROVIDER, _TTS_PROVIDER_ERROR
    try:
        _TTS_PROVIDER = _load_qwen3_provider()
        _TTS_PROVIDER_ERROR = ""
        details: Dict[str, Any] = {}
        try:
            details["provider_class"] = type(_TTS_PROVIDER).__name__
            details["provider_name"] = getattr(_TTS_PROVIDER, "provider_name", _TTS_PROVIDER_NAME)
            details["configured_model"] = getattr(_TTS_PROVIDER, "_model_config", {}).get("model_name", "")
            details["configured_device"] = getattr(_TTS_PROVIDER, "device", "")
        except Exception:
            pass
        return _provider_payload_ok(details)
    except Exception as exc:
        _TTS_PROVIDER = None
        _TTS_PROVIDER_ERROR = f"{type(exc).__name__}: {exc}"
        return _provider_payload_fail(
            _TTS_PROVIDER_ERROR,
            {
                "traceback": traceback.format_exc(limit=8),
            },
        )


def get_tts_service_status() -> Dict[str, Any]:
    if _TTS_PROVIDER is not None:
        details: Dict[str, Any] = {}
        try:
            details["provider_class"] = type(_TTS_PROVIDER).__name__
            details["provider_name"] = getattr(_TTS_PROVIDER, "provider_name", _TTS_PROVIDER_NAME)
            details["configured_model"] = getattr(_TTS_PROVIDER, "_model_config", {}).get("model_name", "")
            details["configured_device"] = getattr(_TTS_PROVIDER, "device", "")
        except Exception:
            pass
        return _provider_payload_ok(details)
    return _provider_payload_fail(_TTS_PROVIDER_ERROR or "provider_not_initialized")


def _require_provider() -> Any:
    if _TTS_PROVIDER is None:
        raise RuntimeError(_TTS_PROVIDER_ERROR or "provider_not_initialized")
    return _TTS_PROVIDER


def _wav_response_from_base64(audio_base64: str, media_type: str = "audio/wav") -> Response:
    return Response(content=base64.b64decode(audio_base64), media_type=media_type)


def _pcm16_chunks_to_wav_response(chunks: List[bytes], sample_rate: int) -> Response:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(chunks))
    return Response(content=buffer.getvalue(), media_type="audio/wav")


def _stream_fallback_response(provider: Any, request: TtsGenerateStreamRequest) -> Optional[Response]:
    if not hasattr(provider, "generate_audio"):
        return None

    fallback_result = provider.generate_audio(
        text=request.text,
        speaker=request.speaker,
        language=request.language,
        temperature=request.temperature,
        top_k=request.top_k,
        top_p=request.top_p,
        repetition_penalty=request.repetition_penalty,
        append_silence=request.append_silence,
        max_new_tokens=request.max_new_tokens,
    )
    audio_base64 = fallback_result.get("audio_base64")
    if not isinstance(audio_base64, str) or not audio_base64:
        audio_value = fallback_result.get("audio")
        audio_base64 = audio_value if isinstance(audio_value, str) else ""
    if not fallback_result.get("success") or not audio_base64:
        return None
    media_type = fallback_result.get("format")
    if not isinstance(media_type, str) or not media_type:
        media_type = "audio/wav"
    return _wav_response_from_base64(
        audio_base64,
        media_type=media_type,
    )


@app.on_event("startup")
async def on_startup() -> None:
    status = initialize_tts_provider()
    if status.get("ok"):
        print(f"[TTS SERVER] READY provider={_TTS_PROVIDER_NAME}")
    else:
        print(f"[TTS SERVER] NOT READY provider={_TTS_PROVIDER_NAME} error={status.get('error')}")


@app.get("/health")
async def health() -> Dict[str, Any]:
    status = get_tts_service_status()
    return {
        "ok": status["ok"],
        "provider": status["provider"],
        "error": status["error"],
        "status": "ready" if status["ok"] else "not_ready",
        "details": status["details"],
    }


@app.get("/api/tts/speakers")
async def speakers() -> Dict[str, Any]:
    try:
        provider = _require_provider()
        if hasattr(provider, "get_speakers"):
            result = provider.get_speakers()
            return {
                "success": True,
                "provider": _TTS_PROVIDER_NAME,
                "speakers": result or [],
            }
        return {
            "success": True,
            "provider": _TTS_PROVIDER_NAME,
            "speakers": ["default"],
        }
    except Exception as exc:
        return {
            "success": False,
            "provider": _TTS_PROVIDER_NAME,
            "speakers": [],
            "error": str(exc),
        }


@app.post("/api/tts/generate_audio")
async def generate_audio(request: TtsGenerateRequest):
    try:
        provider = _require_provider()

        if hasattr(provider, "generate_audio"):
            result = provider.generate_audio(
                text=request.text,
                speaker=request.speaker,
                language=request.language,
            )
        elif hasattr(provider, "generate_tts"):
            result = provider.generate_tts(
                text=request.text,
                speaker=request.speaker,
                language=request.language,
            )
        else:
            return JSONResponse(
                {"success": False, "error": "provider_missing_generate_audio"},
                status_code=500,
            )

        return result
    except Exception as exc:
        return JSONResponse(
            {
                "success": False,
                "provider": _TTS_PROVIDER_NAME,
                "error": str(exc),
            },
            status_code=500,
        )


@app.post("/api/tts/generate_stream_audio")
async def generate_stream_audio(request: TtsGenerateStreamRequest):
    provider = None
    try:
        provider = _require_provider()
        if not hasattr(provider, "generate_audio_stream"):
            return JSONResponse(
                {"success": False, "error": "provider_missing_generate_audio_stream"},
                status_code=500,
            )

        chunks: List[bytes] = []
        sample_rate = 24000

        print(f"[TTS SERVER] generate_stream_audio speaker={request.speaker!r} language={request.language!r} text_len={len(request.text)}")

        for audio_chunk, sr, timing in provider.generate_audio_stream(
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
        ):
            if audio_chunk is None:
                continue
            sample_rate = sr or sample_rate
            pcm = (audio_chunk * 32767).astype("int16").tobytes()
            chunks.append(pcm)

        return _pcm16_chunks_to_wav_response(chunks, sample_rate)
    except Exception as exc:
        import traceback
        print(f"[TTS SERVER] generate_stream_audio error: {exc}")
        print(traceback.format_exc())
        fallback_response = _stream_fallback_response(provider, request) if provider is not None else None
        if fallback_response is not None:
            return fallback_response
        return JSONResponse(
            {
                "success": False,
                "provider": _TTS_PROVIDER_NAME,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=12),
            },
            status_code=500,
        )


@app.post("/api/tts/voice_clone")
async def voice_clone(request: TtsVoiceCloneRequest):
    try:
        provider = _require_provider()
        if not hasattr(provider, "voice_clone"):
            return JSONResponse(
                {"success": False, "error": "provider_missing_voice_clone"},
                status_code=500,
            )

        result = provider.voice_clone(
            voice_id=request.voice_id,
            gender=request.gender,
            language=request.language,
            ref_text=request.ref_text,
        )
        return result
    except Exception as exc:
        return JSONResponse(
            {
                "success": False,
                "provider": _TTS_PROVIDER_NAME,
                "error": str(exc),
            },
            status_code=500,
        )


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("OMNIX_TTS_HOST", "127.0.0.1")
    port = int(os.environ.get("OMNIX_TTS_PORT", "5101"))
    uvicorn.run(app, host=host, port=port)
