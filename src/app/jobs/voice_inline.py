"""Inline Voice Studio job execution for local backend wiring."""
from __future__ import annotations

import base64
import json
import math
import mimetypes
import re
import wave
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from app.assets import AssetRecord, AssetType, default_asset_store
from app.runtime_paths import resources_data_root

from .models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobRecord, JobStage, ResourceClass

VOICE_STUDIO_JOB_TYPES = {
    "tts.synthesize",
    "tts.multi_speaker_synthesize",
    "voice-cloning.create-profile",
}


def install_voice_studio_job_execution(sqlite_job_store_cls: Any) -> None:
    """Patch ``SQLiteJobStore.create_job`` so Voice Studio jobs execute locally."""
    if getattr(sqlite_job_store_cls, "_omnix_voice_studio_jobs_installed", False):
        return

    original_create_job = sqlite_job_store_cls.create_job

    def create_job_with_voice_studio_execution(self: Any, request: CreateJobRequest) -> JobRecord:
        job = original_create_job(self, request)
        if job.type not in VOICE_STUDIO_JOB_TYPES:
            return job
        return execute_voice_studio_job(self, job)

    sqlite_job_store_cls.create_job = create_job_with_voice_studio_execution
    sqlite_job_store_cls._omnix_voice_studio_jobs_installed = True


def execute_voice_studio_job(job_store: Any, job: JobRecord) -> JobRecord:
    """Run a Voice Studio job synchronously and persist generated assets."""
    job_store.mark_running(job.id)
    try:
        if job.type == "voice-cloning.create-profile":
            result = _execute_clone_job(job)
        elif job.type in {"tts.synthesize", "tts.multi_speaker_synthesize"}:
            result = _execute_tts_job(job)
        else:  # pragma: no cover - guarded by caller.
            raise RuntimeError(f"Unsupported Voice Studio job type: {job.type}")
    except Exception as exc:
        failed = job_store.fail_job(
            job.id,
            FailJobRequest(
                code="voice_studio_job_failed",
                message=str(exc) or "Voice Studio job failed",
                retryable=True,
                details={"job_type": job.type, "module": job.module},
            ),
        )
        return failed or job

    completed = job_store.complete_job(
        job.id,
        CompleteJobRequest(
            output_refs=result["output_refs"],
            logs=[
                {
                    "level": "info",
                    "message": result["log_message"],
                    "content": result["content"],
                }
            ],
        ),
    )
    return completed or job


def _execute_clone_job(job: JobRecord) -> dict[str, Any]:
    payload = job.input_payload or {}
    profile_name = _require_text(payload.get("profile_name"), "Voice name is required")
    audio_bytes = _decode_audio_payload(payload.get("sample_audio_base64"))
    source_file_name = _text(payload.get("source_file_name")) or f"{profile_name}.wav"
    suffix = Path(source_file_name).suffix.lower() or ".wav"
    if suffix not in {".wav", ".mp3", ".mp4", ".m4a", ".webm", ".ogg", ".flac"}:
        suffix = ".wav"

    voice_id = _safe_segment(profile_name)
    clone_dir = _voice_clone_dir()
    clone_dir.mkdir(parents=True, exist_ok=True)
    clone_path = clone_dir / f"{voice_id}{suffix}"
    clone_path.write_bytes(audio_bytes)
    _upsert_legacy_voice_manifest(voice_id, profile_name, payload, clone_path)

    asset = _upsert_asset(
        AssetRecord(
            id=f"voice-cloning:{voice_id}",
            module="voice-cloning",
            type=AssetType.VOICE_PROFILE,
            mime_type=_mime_for_path(clone_path),
            storage_path=str(clone_path),
            metadata={
                "profile_name": profile_name,
                "voice_id": voice_id,
                "language": _text(payload.get("language")) or "English (US)",
                "quality": _text(payload.get("quality")) or "High (Recommended)",
                "notes": _text(payload.get("notes")),
                "source_kind": _text(payload.get("source_kind")) or "upload",
                "source_file_name": source_file_name,
                "provider_id": _text(payload.get("provider_id")),
                "has_audio": True,
            },
            source_job_id=job.id,
            created_at=_utcnow(),
            compat={"contract": "voice_studio_clone_v1", "storage_hint": "resources/voice_clones"},
        )
    )
    return {
        "content": f"Voice clone '{profile_name}' saved to {clone_path}",
        "log_message": "Voice clone profile stored locally",
        "output_refs": [_asset_output_ref(asset, title=profile_name)],
    }


def _execute_tts_job(job: JobRecord) -> dict[str, Any]:
    payload = job.input_payload or {}
    text = _require_text(payload.get("text"), "Text is required")
    assignments = payload.get("character_voice_assignments") if isinstance(payload.get("character_voice_assignments"), list) else []
    primary_voice = _text(payload.get("voice_id")) or _first_assignment_voice(assignments)
    speaker = _voice_stem(primary_voice) or _text(payload.get("speaker")) or "default"
    wav_bytes, audio_metadata = _generate_audio_bytes(text, speaker=speaker, payload=payload)

    title = _tts_title(payload, job)
    output_dir = resources_data_root() / "voice_studio"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_safe_segment(title)}-{_safe_segment(job.id)}.wav"
    output_path.write_bytes(wav_bytes)

    asset = _upsert_asset(
        AssetRecord(
            id=f"audio:voice-studio-{_safe_segment(job.id)}",
            module="voice",
            type=AssetType.AUDIO,
            mime_type="audio/wav",
            storage_path=str(output_path),
            metadata={
                "title": title,
                "text": text,
                "speaker": speaker,
                "provider_id": _text(payload.get("provider_id")),
                "script_mode": _text(payload.get("script_mode")) or "single_speaker",
                "script_speakers": payload.get("script_speakers") or [],
                "character_voice_assignments": assignments,
                "output_settings": payload.get("output_settings") or {},
                "audio_effects": payload.get("audio_effects") or [],
                **audio_metadata,
            },
            source_job_id=job.id,
            created_at=_utcnow(),
            compat={"contract": "voice_studio_tts_v1"},
        )
    )
    return {
        "content": f"Speech audio saved to {output_path}",
        "log_message": "Voice Studio speech generated and saved",
        "output_refs": [_asset_output_ref(asset, title=title)],
    }


def _generate_audio_bytes(text: str, *, speaker: str, payload: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    try:
        from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

        provider = FasterQwen3TTSProvider()
        result = provider.generate_audio(
            text,
            speaker=speaker,
            language=_text(payload.get("language")) or "en",
            output_settings=payload.get("output_settings") or {},
            audio_effects=payload.get("audio_effects") or [],
        )
        encoded = _text(result.get("audio_base64")) or _text(result.get("audio"))
        if encoded:
            return base64.b64decode(encoded), {
                "sample_rate": result.get("sample_rate"),
                "duration": result.get("duration"),
                "provider_success": bool(result.get("success")),
                "provider_fallback": bool(result.get("is_fallback")),
                "provider_error": _text(result.get("error")),
            }
    except Exception as exc:
        return _fallback_wav(text), {
            "sample_rate": 12000,
            "duration": _fallback_duration(text),
            "provider_success": False,
            "provider_fallback": True,
            "provider_error": str(exc),
        }
    return _fallback_wav(text), {
        "sample_rate": 12000,
        "duration": _fallback_duration(text),
        "provider_success": False,
        "provider_fallback": True,
        "provider_error": "provider_returned_no_audio",
    }


def _fallback_wav(text: str) -> bytes:
    sample_rate = 12000
    duration = _fallback_duration(text)
    frame_count = max(int(sample_rate * duration), sample_rate // 2)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            t = index / sample_rate
            envelope = min(1.0, index / max(sample_rate * 0.03, 1), (frame_count - index) / max(sample_rate * 0.03, 1))
            value = int(32767 * 0.14 * envelope * (math.sin(2 * math.pi * 220 * t) + 0.45 * math.sin(2 * math.pi * 330 * t)))
            frames.extend(value.to_bytes(2, byteorder="little", signed=True))
        wav_file.writeframes(bytes(frames))
    return buffer.getvalue()


def _fallback_duration(text: str) -> float:
    return max(0.75, min(6.0, max(len(text.strip()), 1) / 16.0))


def _decode_audio_payload(value: Any) -> bytes:
    encoded = _require_text(value, "Audio sample is required")
    if "," in encoded and encoded.strip().lower().startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    try:
        return base64.b64decode(encoded, validate=False)
    except Exception as exc:
        raise ValueError("Audio sample could not be decoded") from exc


def _upsert_legacy_voice_manifest(voice_id: str, profile_name: str, payload: dict[str, Any], clone_path: Path) -> None:
    try:
        import app.shared as shared

        manifest_path = Path(shared.VOICE_CLONES_FILE)
    except Exception:
        manifest_path = _voice_clone_dir() / "voice_clones.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    except Exception:
        raw = {}
    raw[profile_name] = {
        "voice_clone_id": voice_id,
        "speaker": profile_name,
        "language": _text(payload.get("language")) or "English (US)",
        "gender": "neutral",
        "has_audio": True,
        "is_preloaded": False,
        "source_file_name": _text(payload.get("source_file_name")) or clone_path.name,
        "source_path": str(clone_path),
        "notes": _text(payload.get("notes")),
    }
    manifest_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _voice_clone_dir() -> Path:
    try:
        import app.shared as shared

        return Path(shared.VOICE_CLONES_DIR)
    except Exception:
        return resources_data_root().parent / "voice_clones"


def _upsert_asset(asset: AssetRecord) -> AssetRecord:
    return default_asset_store().upsert_asset(asset)


def _asset_output_ref(asset: AssetRecord, *, title: str) -> dict[str, Any]:
    return {
        "type": asset.type.value if hasattr(asset.type, "value") else str(asset.type),
        "asset_id": asset.id,
        "title": title,
        "storage_path": asset.storage_path,
        "mime_type": asset.mime_type,
    }


def _first_assignment_voice(assignments: list[Any]) -> str:
    for row in assignments:
        if isinstance(row, dict):
            value = _text(row.get("voice_id"))
            if value:
                return value
    return ""


def _voice_stem(value: str) -> str:
    if not value:
        return ""
    name = re.split(r"[\\/]", value)[-1]
    return name.rsplit(".", 1)[0]


def _tts_title(payload: dict[str, Any], job: JobRecord) -> str:
    speakers = payload.get("script_speakers")
    if isinstance(speakers, list) and len(speakers) > 1:
        return "multi_voice_script"
    speaker = _text(payload.get("speaker")) or "voice"
    return f"{speaker}_speech"


def _mime_for_path(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    cleaned = cleaned.strip("-._")
    return cleaned or "voice"


def _require_text(value: Any, message: str) -> str:
    result = _text(value)
    if not result:
        raise ValueError(message)
    return result


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
