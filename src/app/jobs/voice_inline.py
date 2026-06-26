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

from .models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobRecord

VOICE_STUDIO_JOB_TYPES = {
    "tts.synthesize",
    "tts.multi_speaker_synthesize",
    "voice-cloning.create-profile",
}
DEFAULT_UNTAGGED_SPEAKER = "Narrator"


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
    assignments_by_speaker = _assignments_by_speaker(assignments)
    segments = _script_segments(payload, text)
    primary_voice = _text(payload.get("voice_id")) or _first_assignment_voice(assignments)
    default_speaker = _voice_stem(primary_voice) or _text(payload.get("speaker")) or DEFAULT_UNTAGGED_SPEAKER

    wav_chunks: list[bytes] = []
    segment_outputs: list[dict[str, Any]] = []
    for segment in segments:
        speaker_name = _text(segment.get("speaker")) or DEFAULT_UNTAGGED_SPEAKER
        assignment = assignments_by_speaker.get(speaker_name.casefold(), {})
        voice_id = _text(assignment.get("voice_id")) or primary_voice
        generated_speaker = _voice_stem(voice_id) or speaker_name or default_speaker
        wav_bytes, metadata = _generate_audio_bytes(_text(segment.get("text")), speaker=generated_speaker, payload=payload)
        wav_chunks.append(wav_bytes)
        segment_outputs.append(
            {
                "index": int(segment.get("index") or len(segment_outputs)),
                "speaker": speaker_name,
                "text": _text(segment.get("text")),
                "voice_id": voice_id,
                "style": _text(assignment.get("style")),
                "sample_rate": metadata.get("sample_rate"),
                "duration": metadata.get("duration"),
                "provider_success": metadata.get("provider_success"),
                "provider_fallback": metadata.get("provider_fallback"),
                "provider_error": metadata.get("provider_error"),
            }
        )

    wav_bytes, combined_metadata = _combine_segment_wavs(wav_chunks, text)
    title = _tts_title(payload, job)
    output_dir = resources_data_root() / "voice_studio"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_safe_segment(title)}-{_safe_segment(job.id)}.wav"
    output_path.write_bytes(wav_bytes)

    metadata = {
        "title": title,
        "text": text,
        "speaker": default_speaker,
        "provider_id": _text(payload.get("provider_id")),
        "script_mode": "multi_speaker" if len({segment["speaker"] for segment in segments}) > 1 else "single_speaker",
        "script_speakers": payload.get("script_speakers") or _speakers_from_segments(segments),
        "script_segments": segments,
        "segment_outputs": segment_outputs,
        "character_voice_assignments": assignments,
        "output_settings": payload.get("output_settings") or {},
        "audio_effects": payload.get("audio_effects") or [],
        **combined_metadata,
    }
    asset = _upsert_asset(
        AssetRecord(
            id=f"audio:voice-studio-{_safe_segment(job.id)}",
            module="voice",
            type=AssetType.AUDIO,
            mime_type="audio/wav",
            storage_path=str(output_path),
            metadata=metadata,
            source_job_id=job.id,
            created_at=_utcnow(),
            compat={"contract": "voice_studio_tts_v2", "generation_mode": "segment_stitch"},
        )
    )
    output_ref = _asset_output_ref(asset, title=title)
    output_ref.update(
        {
            "data_url": f"data:audio/wav;base64,{base64.b64encode(wav_bytes).decode('utf-8')}",
            "duration": combined_metadata.get("duration"),
            "segments": segment_outputs,
        }
    )
    return {
        "content": f"Speech audio saved to {output_path}",
        "log_message": "Voice Studio speech generated per script segment and saved",
        "output_refs": [output_ref],
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


def _combine_segment_wavs(wav_chunks: list[bytes], fallback_text: str) -> tuple[bytes, dict[str, Any]]:
    if not wav_chunks:
        wav_bytes = _fallback_wav(fallback_text)
        return wav_bytes, {"sample_rate": 12000, "duration": _fallback_duration(fallback_text), "segment_count": 1}
    if len(wav_chunks) == 1:
        metadata = _wav_metadata(wav_chunks[0])
        metadata["segment_count"] = 1
        return wav_chunks[0], metadata
    try:
        combined = _concat_wavs(wav_chunks)
        metadata = _wav_metadata(combined)
        metadata["segment_count"] = len(wav_chunks)
        return combined, metadata
    except Exception:
        wav_bytes = _fallback_wav(fallback_text)
        return wav_bytes, {
            "sample_rate": 12000,
            "duration": _fallback_duration(fallback_text),
            "segment_count": len(wav_chunks),
            "provider_fallback": True,
            "provider_error": "segment_audio_concat_failed",
        }


def _concat_wavs(wav_chunks: list[bytes]) -> bytes:
    params = None
    frames = bytearray()
    for wav_bytes in wav_chunks:
        with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
            current_params = (wav_file.getnchannels(), wav_file.getsampwidth(), wav_file.getframerate())
            if params is None:
                params = current_params
            if current_params != params:
                raise ValueError("segment audio parameters do not match")
            frames.extend(wav_file.readframes(wav_file.getnframes()))
            frames.extend(b"\x00" * current_params[0] * current_params[1] * max(int(current_params[2] * 0.16), 1))
    channels, sample_width, frame_rate = params or (1, 2, 12000)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(sample_width)
        output.setframerate(frame_rate)
        output.writeframes(bytes(frames))
    return buffer.getvalue()


def _wav_metadata(wav_bytes: bytes) -> dict[str, Any]:
    with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
    return {"sample_rate": sample_rate, "duration": frame_count / sample_rate if sample_rate else 0.0}


def _fallback_duration(text: str) -> float:
    return max(0.75, min(6.0, max(len(text.strip()), 1) / 16.0))


def _script_segments(payload: dict[str, Any], text: str) -> list[dict[str, Any]]:
    raw_segments = payload.get("script_segments")
    if isinstance(raw_segments, list):
        segments = []
        for index, raw in enumerate(raw_segments):
            if not isinstance(raw, dict):
                continue
            segment_text = _text(raw.get("text"))
            if segment_text:
                segments.append({"index": int(raw.get("index") or index), "speaker": _text(raw.get("speaker")) or DEFAULT_UNTAGGED_SPEAKER, "text": segment_text})
        if segments:
            return segments

    segments: list[dict[str, Any]] = []
    untagged: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        tagged = _parse_tagged_line(line)
        if tagged:
            if untagged:
                segments.append({"index": len(segments), "speaker": DEFAULT_UNTAGGED_SPEAKER, "text": " ".join(untagged)})
                untagged = []
            segments.append({"index": len(segments), **tagged})
        else:
            untagged.append(line)
    if untagged:
        segments.append({"index": len(segments), "speaker": DEFAULT_UNTAGGED_SPEAKER, "text": " ".join(untagged)})
    return segments or [{"index": 0, "speaker": DEFAULT_UNTAGGED_SPEAKER, "text": text.strip()}]


def _parse_tagged_line(line: str) -> dict[str, str] | None:
    colon = line.find(":")
    if colon <= 0:
        return None
    speaker = line[:colon].strip()
    content = line[colon + 1 :].strip()
    if not speaker or not content or len(speaker) > 50:
        return None
    return {"speaker": speaker, "text": content}


def _speakers_from_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for segment in segments:
        speaker = _text(segment.get("speaker")) or DEFAULT_UNTAGGED_SPEAKER
        counts[speaker] = counts.get(speaker, 0) + 1
    return [{"name": speaker, "count": count} for speaker, count in counts.items()]


def _assignments_by_speaker(assignments: list[Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for row in assignments:
        if isinstance(row, dict):
            speaker = _text(row.get("speaker"))
            if speaker:
                mapped[speaker.casefold()] = row
    return mapped


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
    speaker = _text(payload.get("speaker")) or DEFAULT_UNTAGGED_SPEAKER
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
