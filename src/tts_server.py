from __future__ import annotations

import base64
import asyncio
import io
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
import wave
from pathlib import Path
from typing import Annotated, Any, Dict, List

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.config.env import env_bool, env_int, env_str, environment
from app.config.runtime import DevicePermitSettings
from app.persistence.database import default_database
from app.persistence.device_permits import (
    DevicePermitError,
    DevicePermitUnavailable,
    configure_default_device_permit_service,
    device_permit_slot,
)
from app.runtime.model_executor import ModelExecutor
from app.runtime.paths import VOICE_CLONES_DIR
from app.runtime.net import bind_host
from app.security.model_service import ModelServiceMiddleware
from app.voice_debug import text_fingerprint, voice_debug_log, voice_debug_log_path

app = FastAPI(title="Omnix TTS Service", version="1.0")
app.add_middleware(ModelServiceMiddleware)


# One request synthesizes at most this much text (about 25 minutes of speech);
# longer work is split by the caller (audiobook render units, live phrases).
MAX_TTS_TEXT_CHARS = 20_000


class TtsGenerateRequest(BaseModel):
    text: str = Field(max_length=MAX_TTS_TEXT_CHARS)
    speaker: str = "default"
    language: str = "en"
    speed: float = 1.0
    pitch: float = 0.0
    emotion: str = "neutral"
    trace_id: str = ""


class TtsGenerateStreamRequest(BaseModel):
    text: str = Field(max_length=MAX_TTS_TEXT_CHARS)
    speaker: str = "default"
    language: str = "en"
    chunk_size: int = 6
    temperature: float = 0.6
    top_k: int = 20
    top_p: float = 0.85
    repetition_penalty: float = 1.0
    append_silence: bool = False
    max_new_tokens: int = 180
    trace_id: str = ""


_MAX_VOICE_CLONE_BYTES = 25 * 1024 * 1024


class TtsVoiceCloneRequest(BaseModel):
    voice_id: str
    gender: str = "neutral"
    language: str = "en"
    ref_text: str = ""


_TTS_PROVIDER: Any = None
_TTS_PROVIDER_ERROR: str = ""
_TTS_PROVIDER_NAME: str = "qwen3_tts"
_TTS_MODEL_OWNER_GUARD: Any = None


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


def _normalize_bind_host(host: str) -> str:
    return bind_host(str(host or "").strip() or None)


def _can_bind_port(host: str, port: int) -> bool:
    bind_host = _normalize_bind_host(host)
    family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, int(port)))
        except OSError:
            return False
    return True


def _wait_for_port_release(host: str, port: int, timeout_s: float = 8.0, interval_s: float = 0.25) -> bool:
    """Wait briefly for Windows to release a port after Stop-Process."""
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        if _can_bind_port(host, port):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(max(0.05, float(interval_s)))


def _windows_port_owner_pids(port: int) -> List[int]:
    if os.name != "nt":
        return []
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-NetTCPConnection -LocalPort "
        + str(int(port))
        + " -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except Exception:
        return []
    pids: List[int] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if pid > 0 and pid != os.getpid():
            pids.append(pid)
    return sorted(set(pids))


def _kill_windows_port_owners(port: int) -> List[int]:
    killed: List[int] = []
    for pid in _windows_port_owner_pids(port):
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            killed.append(pid)
        except Exception:
            continue
    return killed


def _preflight_tts_port(host: str, port: int) -> bool:
    if _can_bind_port(host, port):
        return True

    should_kill = env_bool("OMNIX_LAUNCHER_KILL_PORT", False)
    if should_kill and os.name == "nt":
        killed = _kill_windows_port_owners(port)
        if killed:
            print(f"[TTS SERVER] stopped stale process(es) on port {port}: {', '.join(map(str, killed))}")
        wait_timeout_s = float(env_str("OMNIX_LAUNCHER_PORT_RELEASE_TIMEOUT", "8") or 8)
        if _wait_for_port_release(host, port, timeout_s=wait_timeout_s):
            return True
        remaining = _windows_port_owner_pids(port)
        if remaining:
            print(f"[TTS SERVER] port {port} still owned after cleanup: {', '.join(map(str, remaining))}")
        elif killed:
            print(f"[TTS SERVER] port {port} did not become bindable within {wait_timeout_s:.1f}s after cleanup")

    print("\n" + "=" * 50)
    print("Omnix TTS Server could not start")
    print("=" * 50)
    print(f"Port already in use: {host}:{port}")
    print("Another TTS/server process is already bound to this port.")
    print("")
    print("Find the process using PowerShell:")
    print(f"  Get-NetTCPConnection -LocalPort {port} | Select-Object LocalAddress,LocalPort,State,OwningProcess")
    print("")
    print("Then stop it, or kill the owning process:")
    print("  Stop-Process -Id <OwningProcess> -Force")
    print("")
    print("Or allow Omnix to clean stale port owners before launch:")
    print("  $env:OMNIX_LAUNCHER_KILL_PORT = '1'")
    print("=" * 50)
    return False


def _load_qwen3_provider() -> Any:
    """Load the dedicated TTS provider while keeping failures local."""
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider
    from app.settings.access import load_settings

    settings = load_settings() or {}
    provider_settings = dict(settings.get("faster-qwen3-tts") or {})
    return FasterQwen3TTSProvider(config=provider_settings)


def initialize_tts_provider() -> Dict[str, Any]:
    global _TTS_PROVIDER, _TTS_PROVIDER_ERROR
    try:
        provider = _load_qwen3_provider()
        startup_result: Dict[str, Any] = {}
        if hasattr(provider, "start"):
            startup_result = provider.start() or {}
            if not startup_result.get("running", False):
                raise RuntimeError(startup_result.get("error") or startup_result.get("message") or "provider_start_failed")

        _TTS_PROVIDER = provider
        _TTS_PROVIDER_ERROR = ""
        details: Dict[str, Any] = {}
        try:
            details["provider_class"] = type(_TTS_PROVIDER).__name__
            details["provider_name"] = getattr(_TTS_PROVIDER, "provider_name", _TTS_PROVIDER_NAME)
            details["configured_model"] = getattr(_TTS_PROVIDER, "_model_config", {}).get("model_name", "")
            details["configured_device"] = getattr(_TTS_PROVIDER, "device", "")
            if hasattr(_TTS_PROVIDER, "get_runtime_status"):
                details["runtime_status"] = _TTS_PROVIDER.get_runtime_status()
            if startup_result:
                details["startup"] = startup_result
        except Exception:
            pass
        return _provider_payload_ok(details)
    except Exception as exc:
        _TTS_PROVIDER = None
        _TTS_PROVIDER_ERROR = f"{type(exc).__name__}: {exc}"
        return _provider_payload_fail(
            _TTS_PROVIDER_ERROR,
            {"traceback": traceback.format_exc(limit=8)},
        )


def _claim_tts_model_owner() -> None:
    global _TTS_MODEL_OWNER_GUARD
    permit_config = DevicePermitSettings.from_environment(environment())
    service = configure_default_device_permit_service(
        default_database(),
        device_id=permit_config.device_id,
        capacities={
            model_class: (capacity, reserved)
            for model_class, capacity, reserved in permit_config.capacities
        },
        lease_seconds=permit_config.lease_seconds,
        tts_model_owner=permit_config.tts_model_owner,
    )
    if _TTS_MODEL_OWNER_GUARD is None:
        _TTS_MODEL_OWNER_GUARD = service.hold_model_owner(
            "tts",
            holder_id=f"tts-server:{os.getpid()}",
            process_role="tts-server",
        )


def _handle_tts_model_owner_loss(provider: Any, guard: Any) -> None:
    global _TTS_PROVIDER, _TTS_PROVIDER_ERROR, _TTS_MODEL_OWNER_GUARD
    stop = getattr(provider, "stop", None)
    if callable(stop):
        stop()
    if _TTS_PROVIDER is provider:
        _TTS_PROVIDER = None
        _TTS_PROVIDER_ERROR = "local TTS model-owner lease was lost"
    if _TTS_MODEL_OWNER_GUARD is guard:
        _TTS_MODEL_OWNER_GUARD = None


def get_tts_service_status() -> Dict[str, Any]:
    if _TTS_PROVIDER is not None:
        details: Dict[str, Any] = {}
        try:
            details["provider_class"] = type(_TTS_PROVIDER).__name__
            details["provider_name"] = getattr(_TTS_PROVIDER, "provider_name", _TTS_PROVIDER_NAME)
            details["configured_model"] = getattr(_TTS_PROVIDER, "_model_config", {}).get("model_name", "")
            details["configured_device"] = getattr(_TTS_PROVIDER, "device", "")
            if hasattr(_TTS_PROVIDER, "get_runtime_status"):
                details["runtime_status"] = _TTS_PROVIDER.get_runtime_status()
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


def _request_trace_id(value: str, prefix: str) -> str:
    candidate = str(value or "").strip()
    return candidate[:180] if candidate else f"{prefix}:{uuid.uuid4()}"


def _voice_reference_snapshot(speaker: str) -> dict[str, Any]:
    clone_dir = Path(VOICE_CLONES_DIR).resolve()
    requested = clone_dir / f"{speaker}.wav" if speaker else None
    default_ref = clone_dir / "default_ref.wav"
    wav_files = sorted(
        (path for path in clone_dir.glob("*.wav") if path.is_file()),
        key=lambda path: path.name.casefold(),
    ) if clone_dir.is_dir() else []

    resolved: Path | None = None
    strategy = "none"
    if requested is not None and requested.is_file():
        resolved = requested
        strategy = "exact_speaker"
    elif default_ref.is_file():
        resolved = default_ref
        strategy = "default_ref_fallback"
    elif wav_files:
        resolved = wav_files[0]
        strategy = "first_wav_fallback"

    return {
        "cwd": str(Path.cwd()),
        "voice_clones_dir": str(clone_dir),
        "voice_clones_dir_exists": clone_dir.is_dir(),
        "requested_speaker": speaker,
        "requested_path": str(requested) if requested is not None else "",
        "requested_path_exists": bool(requested and requested.is_file()),
        "resolution_strategy": strategy,
        "resolved_reference_path": str(resolved) if resolved is not None else "",
        "resolved_reference_name": resolved.name if resolved is not None else "",
        "resolved_reference_bytes": resolved.stat().st_size if resolved is not None else 0,
        "available_wav_files": [path.name for path in wav_files[:100]],
        "available_wav_count": len(wav_files),
    }


def _trace_response(response: Response, trace_id: str) -> Response:
    response.headers["X-Omnix-Voice-Trace"] = trace_id
    return response


_SYNTHESIS: ModelExecutor | None = None


def _synthesis() -> ModelExecutor:
    """Model calls run on their own pool (WP-7.1); device permits still gate the GPU."""
    global _SYNTHESIS
    if _SYNTHESIS is None:
        _SYNTHESIS = ModelExecutor(
            "tts-synthesis",
            env_int("OMNIX_TTS_SYNTHESIS_WORKERS", 8, minimum=1, maximum=64),
        )
    return _SYNTHESIS


async def _enter_device_permit(permit: Any) -> None:
    """Acquire without leaking a late grant if the request is cancelled."""
    acquire_task = asyncio.create_task(asyncio.to_thread(permit.__enter__))
    try:
        await asyncio.shield(acquire_task)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(acquire_task)
        except Exception as exc:
            # No permit was granted, so there is nothing to release.
            voice_debug_log(
                "tts",
                "tts_device_permit_cancelled_acquire_failed",
                error_type=type(exc).__name__,
            )
        else:
            await asyncio.shield(asyncio.to_thread(permit.__exit__, None, None, None))
        raise


@app.on_event("startup")
async def on_startup() -> None:
    global _TTS_PROVIDER, _TTS_PROVIDER_ERROR, _TTS_MODEL_OWNER_GUARD
    try:
        _claim_tts_model_owner()
        status = initialize_tts_provider()
        if status.get("ok") and _TTS_MODEL_OWNER_GUARD is not None:
            provider = _TTS_PROVIDER
            guard = _TTS_MODEL_OWNER_GUARD
            if not guard.set_on_lost(
                lambda: _handle_tts_model_owner_loss(provider, guard)
            ):
                status = get_tts_service_status()
        if not status.get("ok"):
            guard, _TTS_MODEL_OWNER_GUARD = _TTS_MODEL_OWNER_GUARD, None
            if guard is not None:
                guard.close()
    except Exception as exc:
        _TTS_PROVIDER = None
        _TTS_PROVIDER_ERROR = f"{type(exc).__name__}: {exc}"
        guard, _TTS_MODEL_OWNER_GUARD = _TTS_MODEL_OWNER_GUARD, None
        if guard is not None:
            guard.close()
        status = _provider_payload_fail(_TTS_PROVIDER_ERROR)
    voice_debug_log(
        "tts",
        "tts_service_started",
        trace_id="tts-service-startup",
        provider=_TTS_PROVIDER_NAME,
        provider_ready=bool(status.get("ok")),
        provider_error=status.get("error", ""),
        log_path=voice_debug_log_path("tts"),
        **_voice_reference_snapshot("default"),
    )
    if status.get("ok"):
        print(f"[TTS SERVER] READY provider={_TTS_PROVIDER_NAME}")
    else:
        print(f"[TTS SERVER] NOT READY provider={_TTS_PROVIDER_NAME} error={status.get('error')}")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global _TTS_PROVIDER, _TTS_MODEL_OWNER_GUARD, _SYNTHESIS
    synthesis, _SYNTHESIS = _SYNTHESIS, None
    if synthesis is not None:
        synthesis.shutdown()
    provider, _TTS_PROVIDER = _TTS_PROVIDER, None
    stop = getattr(provider, "stop", None)
    if callable(stop):
        stop()
    guard, _TTS_MODEL_OWNER_GUARD = _TTS_MODEL_OWNER_GUARD, None
    if guard is not None:
        guard.close()


@app.get("/health")
def health() -> Dict[str, Any]:
    status = get_tts_service_status()
    return {
        "ok": status["ok"],
        "provider": status["provider"],
        "error": "" if status["ok"] else "model_unavailable",
        "status": "ready" if status["ok"] else "not_ready",
        "details": {key: status["details"][key] for key in
                    ("provider_class", "provider_name", "configured_model", "configured_device")
                    if key in status["details"]},
    }


@app.get("/api/tts/speakers")
async def speakers() -> Dict[str, Any]:
    return await _synthesis().run(_speakers)


def _speakers() -> dict[str, Any]:
    trace_id = _request_trace_id("", "tts-speakers")
    try:
        provider = _require_provider()
        if hasattr(provider, "get_speakers"):
            result = provider.get_speakers()
            voice_debug_log(
                "tts",
                "tts_speakers_listed",
                trace_id=trace_id,
                speaker_ids=[
                    str(row.get("id") or row.get("name") or "")
                    for row in (result or [])
                    if isinstance(row, dict)
                ][:100],
                **_voice_reference_snapshot("default"),
            )
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
        voice_debug_log(
            "tts",
            "tts_speakers_failed",
            trace_id=trace_id,
            error=exc,
        )
        raise HTTPException(status_code=503, detail="model_unavailable") from exc


@app.post("/api/tts/generate_audio")
async def generate_audio(
    request: TtsGenerateRequest,
    accept: Annotated[str | None, Header()] = None,
):
    """Synthesise one utterance. ``Accept: audio/wav`` returns the WAV bytes
    (WP-7.3); otherwise the JSON result carries them base64-encoded."""
    wants_wav = "audio/wav" in (accept or "").lower()
    return await _synthesis().run(_generate_audio, request, wants_wav)


def _wav_result_response(result: dict[str, Any], trace_id: str) -> Response:
    encoded = result.get("audio_base64") or result.get("audio") or ""
    headers = {"X-Omnix-Voice-Trace": trace_id}
    for header, key in (("X-Omnix-Sample-Rate", "sample_rate"), ("X-Omnix-Duration", "duration")):
        if result.get(key) is not None:
            headers[header] = str(result[key])
    return Response(content=base64.b64decode(encoded), media_type="audio/wav", headers=headers)


def _generate_audio(request: TtsGenerateRequest, wants_wav: bool = False):
    trace_id = _request_trace_id(request.trace_id, "tts-audio")
    started_at = time.perf_counter()
    snapshot = _voice_reference_snapshot(request.speaker)
    voice_debug_log(
        "tts",
        "tts_audio_request_received",
        trace_id=trace_id,
        speaker=request.speaker,
        language=request.language,
        text_chars=len(request.text),
        text_fingerprint=text_fingerprint(request.text),
        **snapshot,
    )
    try:
        provider = _require_provider()

        if hasattr(provider, "generate_audio"):
            result = provider.generate_audio(
                text=request.text,
                speaker=request.speaker,
                language=request.language,
                voice_trace_id=trace_id,
            )
        elif hasattr(provider, "generate_tts"):
            result = provider.generate_tts(
                text=request.text,
                speaker=request.speaker,
                language=request.language,
            )
        else:
            voice_debug_log(
                "tts",
                "tts_audio_provider_missing",
                trace_id=trace_id,
                provider_class=type(provider).__name__,
            )
            return JSONResponse(
                {"success": False, "error": "provider_missing_generate_audio", "trace_id": trace_id},
                status_code=500,
            )

        voice_debug_log(
            "tts",
            "tts_audio_completed",
            trace_id=trace_id,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
            success=bool(result.get("success")) if isinstance(result, dict) else None,
            is_fallback=bool(result.get("is_fallback")) if isinstance(result, dict) else None,
            error=result.get("error") if isinstance(result, dict) else None,
            resolution_strategy=snapshot["resolution_strategy"],
            resolved_reference_path=snapshot["resolved_reference_path"],
        )

        if isinstance(result, dict) and result.get("is_fallback"):
            return JSONResponse(
                {
                    "success": False,
                    "provider": _TTS_PROVIDER_NAME,
                    "error": "tts_model_unavailable",
                    "details": result,
                    "trace_id": trace_id,
                },
                status_code=503,
                headers={"X-Omnix-Voice-Trace": trace_id},
            )

        if isinstance(result, dict) and not result.get("success", False):
            result = {**result, "trace_id": trace_id}
            return JSONResponse(
                result,
                status_code=503,
                headers={"X-Omnix-Voice-Trace": trace_id},
            )

        if isinstance(result, dict) and wants_wav:
            return _wav_result_response(result, trace_id)
        if isinstance(result, dict):
            result = {**result, "trace_id": trace_id}
        return result
    except Exception as exc:
        voice_debug_log(
            "tts",
            "tts_audio_failed",
            trace_id=trace_id,
            speaker=request.speaker,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
            error=exc,
            **snapshot,
        )
        return JSONResponse(
            {
                "success": False,
                "provider": _TTS_PROVIDER_NAME,
                "error": "model_service_error",
                "trace_id": trace_id,
            },
            status_code=500,
            headers={"X-Omnix-Voice-Trace": trace_id},
        )


@app.post("/api/tts/generate_stream_audio")
async def generate_stream_audio(request: TtsGenerateStreamRequest):
    return await _synthesis().run(_generate_stream_audio, request)


def _generate_stream_audio(request: TtsGenerateStreamRequest):
    trace_id = _request_trace_id(request.trace_id, "tts-stream")
    started_at = time.perf_counter()
    snapshot = _voice_reference_snapshot(request.speaker)
    voice_debug_log(
        "tts",
        "tts_stream_request_received",
        trace_id=trace_id,
        speaker=request.speaker,
        language=request.language,
        text_chars=len(request.text),
        text_fingerprint=text_fingerprint(request.text),
        chunk_size=request.chunk_size,
        **snapshot,
    )
    provider = None
    try:
        provider = _require_provider()
        if not hasattr(provider, "generate_audio_stream"):
            voice_debug_log(
                "tts",
                "tts_stream_provider_missing",
                trace_id=trace_id,
                provider_class=type(provider).__name__,
            )
            return JSONResponse(
                {"success": False, "error": "provider_missing_generate_audio_stream", "trace_id": trace_id},
                status_code=500,
                headers={"X-Omnix-Voice-Trace": trace_id},
            )

        pcm_chunks: List[bytes] = []
        sample_rate = 24000
        print(
            f"[TTS SERVER] generate_stream_audio speaker={request.speaker!r} "
            f"language={request.language!r} text_len={len(request.text)} trace_id={trace_id}"
        )

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
            voice_trace_id=trace_id,
        ):
            if audio_chunk is None:
                continue
            sample_rate = sr or sample_rate
            pcm = (audio_chunk * 32767).astype("int16").tobytes()
            pcm_chunks.append(pcm)

        response = _pcm16_chunks_to_wav_response(pcm_chunks, sample_rate)
        voice_debug_log(
            "tts",
            "tts_stream_completed",
            trace_id=trace_id,
            speaker=request.speaker,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
            chunk_count=len(pcm_chunks),
            pcm_bytes=sum(len(chunk) for chunk in pcm_chunks),
            sample_rate=sample_rate,
            resolution_strategy=snapshot["resolution_strategy"],
            resolved_reference_path=snapshot["resolved_reference_path"],
        )
        return _trace_response(response, trace_id)
    except Exception as exc:
        print(f"[TTS SERVER] generate_stream_audio error: {exc}")
        print(traceback.format_exc())
        voice_debug_log(
            "tts",
            "tts_stream_failed",
            trace_id=trace_id,
            speaker=request.speaker,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 3),
            provider_class=type(provider).__name__ if provider is not None else "",
            error=exc,
            traceback=traceback.format_exc(limit=12),
            **snapshot,
        )
        return JSONResponse(
            {
                "success": False,
                "provider": _TTS_PROVIDER_NAME,
                "error": "model_service_error",
                "trace_id": trace_id,
            },
            status_code=500,
            headers={"X-Omnix-Voice-Trace": trace_id},
        )


@app.post("/api/tts/live-call/stream")
async def generate_live_call_stream(request: TtsGenerateStreamRequest):
    """Stream little-endian PCM16 while holding admission through disconnect."""
    trace_id = _request_trace_id(request.trace_id, "tts-live-stream")
    provider = _require_provider()
    if not hasattr(provider, "generate_audio_stream"):
        return JSONResponse(
            {"success": False, "error": "provider_missing_generate_audio_stream", "trace_id": trace_id},
            status_code=503,
            headers={"X-Omnix-Voice-Trace": trace_id},
        )

    permit = device_permit_slot("tts", priority="realtime", timeout_seconds=1.0)
    try:
        await _enter_device_permit(permit)
    except DevicePermitUnavailable:
        return JSONResponse(
            {"success": False, "error": "tts_capacity_saturated", "trace_id": trace_id},
            status_code=429,
            headers={"Retry-After": "1", "X-Omnix-Voice-Trace": trace_id},
        )
    except DevicePermitError:
        return JSONResponse(
            {"success": False, "error": "tts_admission_unavailable", "trace_id": trace_id},
            status_code=503,
            headers={"X-Omnix-Voice-Trace": trace_id},
        )

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
            voice_trace_id=trace_id,
            _device_permit_held=True,
        )
    except Exception:
        await asyncio.to_thread(permit.__exit__, None, None, None)
        return JSONResponse(
            {"success": False, "error": "tts_provider_unavailable", "trace_id": trace_id},
            status_code=503,
            headers={"X-Omnix-Voice-Trace": trace_id},
        )

    release_lock = threading.Lock()
    permit_released = False

    def release_device_permit() -> None:
        nonlocal permit_released
        with release_lock:
            if permit_released:
                return
            permit_released = True
        permit.__exit__(None, None, None)

    finalization_lock = threading.Lock()
    stream_finalized = False

    def finalize_stream() -> None:
        nonlocal stream_finalized
        with finalization_lock:
            if stream_finalized:
                return
            stream_finalized = True
        try:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        finally:
            release_device_permit()

    def pcm_chunks():
        try:
            for audio_chunk, _sample_rate, _timing in stream:
                if audio_chunk is None:
                    continue
                import numpy as np

                pcm = np.asarray(audio_chunk, dtype=np.float32).reshape(-1)
                yield (np.clip(pcm, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        finally:
            finalize_stream()

    return StreamingResponse(
        pcm_chunks(),
        media_type="application/x-omnix-pcm16",
        headers={
            "X-Omnix-Audio-Format": "pcm_s16le",
            "X-Omnix-Sample-Rate": str(getattr(provider, "sample_rate", 24_000)),
            "X-Omnix-Channels": "1",
            "X-Omnix-Voice-Trace": trace_id,
        },
        background=BackgroundTask(finalize_stream),
    )


@app.post("/api/tts/voice_clone")
async def voice_clone(
    voice_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    gender: Annotated[str, Form()] = "neutral",
    language: Annotated[str, Form()] = "en",
    ref_text: Annotated[str, Form()] = "",
):
    """Multipart upload: the reference audio plus its fields (WP-7.3).

    The gateway client always sent multipart; the endpoint used to expect a
    JSON body without the audio, so cloning over HTTP could not succeed.
    """
    audio = await file.read(_MAX_VOICE_CLONE_BYTES + 1)
    if len(audio) > _MAX_VOICE_CLONE_BYTES:
        raise HTTPException(status_code=413, detail="reference_audio_too_large")
    if not audio:
        raise HTTPException(status_code=422, detail="reference_audio_required")
    request = TtsVoiceCloneRequest(voice_id=voice_id, gender=gender, language=language, ref_text=ref_text)
    return await _synthesis().run(_voice_clone, request, audio)


def _voice_clone(request: TtsVoiceCloneRequest, audio_data: bytes):
    trace_id = _request_trace_id("", "tts-clone")
    voice_debug_log(
        "tts",
        "tts_voice_clone_requested",
        trace_id=trace_id,
        voice_id=request.voice_id,
        language=request.language,
        ref_text_chars=len(request.ref_text),
        ref_text_fingerprint=text_fingerprint(request.ref_text),
        voice_clones_dir=str(Path(VOICE_CLONES_DIR).resolve()),
    )
    try:
        provider = _require_provider()
        if not hasattr(provider, "voice_clone"):
            return JSONResponse(
                {"success": False, "error": "provider_missing_voice_clone", "trace_id": trace_id},
                status_code=500,
            )

        result = provider.voice_clone(
            voice_id=request.voice_id,
            audio_data=audio_data,
            ref_text=request.ref_text or None,
        )
        voice_debug_log(
            "tts",
            "tts_voice_clone_completed",
            trace_id=trace_id,
            voice_id=request.voice_id,
            success=bool(result.get("success")) if isinstance(result, dict) else None,
            error=result.get("error") if isinstance(result, dict) else None,
            **_voice_reference_snapshot(request.voice_id),
        )
        if isinstance(result, dict) and not result.get("success", False):
            return JSONResponse(
                {"success": False, "error": str(result.get("error") or "voice_clone_failed"), "trace_id": trace_id},
                status_code=503,
            )
        return result
    except Exception as exc:
        voice_debug_log(
            "tts",
            "tts_voice_clone_failed",
            trace_id=trace_id,
            voice_id=request.voice_id,
            error=exc,
        )
        return JSONResponse(
            {
                "success": False,
                "provider": _TTS_PROVIDER_NAME,
                "error": "model_service_error",
                "trace_id": trace_id,
            },
            status_code=500,
        )


if __name__ == "__main__":
    import uvicorn

    from app.observability.logging import configure_logging

    configure_logging()
    host = bind_host()
    port = env_int("OMNIX_TTS_PORT", 5101, minimum=1, maximum=65535)
    if not _preflight_tts_port(host, port):
        sys.exit(1)
    uvicorn.run(app, host=host, port=port)
