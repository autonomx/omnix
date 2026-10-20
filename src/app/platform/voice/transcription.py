"""``stt.transcribe``: transcribe a stored audio asset with the configured STT provider.

Only stored assets are accepted (``asset_id``), never a server path: a path in a
job payload would let a request read any file on the worker host. The transcript
is saved as a ``transcript`` asset when ``save_transcript`` is on.

With ``timed`` (the Transcribe tool, Phase 2) the STT service's batch engine
returns word timing and, with ``diarize``, speaker labels; the asset then holds
an ``omnix-transcript-v1`` ``TranscriptDocument``. ``speakers`` fixes the
speaker count (0 lets the engine decide); ``language`` is recorded as given.

``check_render`` transcribes a Voice Studio render with timing and reports its
word error rate against the script recorded on the render, per line where the
render's timeline is known; it saves no transcript unless asked.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_AUDIO_SUFFIXES = {".wav", ".mp3", ".mp4", ".m4a", ".webm", ".ogg", ".flac"}
_MAX_TRANSCRIBE_BYTES = 500 * 1024 * 1024


class TranscriptionRequestError(ValueError):
    """The request names no usable audio; retrying cannot help."""


def _source_asset(job: Any) -> Any:
    from app.assets import AssetType, default_asset_store

    payload = job.input_payload or {}
    if payload.get("source_path"):
        raise TranscriptionRequestError("Transcription takes a stored audio asset, not a server path")
    asset_id = str((job.input_ref or {}).get("asset_id") or payload.get("asset_id") or "").strip()
    if not asset_id:
        raise TranscriptionRequestError("Choose an audio asset to transcribe")
    asset = default_asset_store().get_asset(asset_id)
    if asset is None:
        raise TranscriptionRequestError(f"Audio asset {asset_id} was not found")
    if asset.type not in {AssetType.AUDIO, AssetType.VOICE_SAMPLE, AssetType.VOICE_PROFILE, AssetType.CHAPTER_AUDIO,
                          AssetType.RENDER, AssetType.EXPORT}:
        raise TranscriptionRequestError(f"{asset_id} is not audio")
    return asset


def execute_transcribe_job(job: Any, *, job_store: Any = None) -> dict[str, Any]:
    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.assets.content import read_asset_bytes
    from app.jobs.inline_execution import require_execution_authority
    from app.providers.service import get_stt_provider
    from app.runtime.paths import resources_data_root

    payload = job.input_payload or {}
    asset = _source_asset(job)
    audio = read_asset_bytes(asset, max_bytes=_MAX_TRANSCRIBE_BYTES)
    suffix = Path(asset.storage_path or asset.metadata.get("file_name") or "audio.wav").suffix.lower()
    if suffix not in _AUDIO_SUFFIXES:
        suffix = ".wav"
    provider = get_stt_provider(str(payload.get("provider_id") or "").removeprefix("stt:") or None)
    if provider is None:
        raise RuntimeError("No speech-to-text provider is configured")
    if payload.get("timed") or payload.get("check_render"):
        return _execute_timed(job, job_store, asset, audio, suffix, provider)
    with tempfile.TemporaryDirectory(prefix="omnix-stt-") as directory:
        source = Path(directory) / f"source{suffix}"
        source.write_bytes(audio)
        # The batch engine is English-only until Phase 2; language is not sent.
        result = provider.transcribe(str(source))
    if not isinstance(result, dict) or not result.get("success"):
        detail = str(result.get("error") or "") if isinstance(result, dict) else ""
        raise RuntimeError(f"Transcription failed{': ' + detail if detail else ''}")
    text = str(result.get("text") or "").strip()
    provider_name = str(getattr(provider, "provider_name", "") or "stt")
    document = {
        "schema_version": 1,
        "source_asset_id": asset.id,
        "provider": provider_name,
        "text": text,
        "segments": result.get("segments") if isinstance(result.get("segments"), list) else [],
        "duration": result.get("duration"),
    }
    output_ref: dict[str, Any] = {"type": "transcript", "title": "Transcript", "content": text,
                                  "provider_id": provider_name, "source_asset_id": asset.id}
    if payload.get("save_transcript", True):
        output_dir = resources_data_root() / "voice_studio" / "transcripts"
        output_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(char if char.isalnum() or char in "-_." else "-" for char in job.id)
        path = output_dir / f"{safe}.json"
        require_execution_authority(job_store, job.id)
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        title = f"Transcript of {asset.metadata.get('title') or asset.metadata.get('profile_name') or asset.id}"
        require_execution_authority(job_store, job.id)
        record = default_asset_store().upsert_asset(AssetRecord(
            id=f"transcript:{safe}",
            module="stt",
            type=AssetType.TRANSCRIPT,
            mime_type="application/json",
            storage_path=str(path),
            metadata={"title": title, "provider": provider_name, "text": text, "duration": document["duration"]},
            source_job_id=job.id,
            parent_asset_ids=[asset.id],
            created_at=datetime.now(timezone.utc).isoformat(),
            compat={"contract": "voice_studio_transcript_v1"},
        ))
        output_ref.update(asset_id=record.id, title=title, mime_type=record.mime_type)
    return {
        "content": text,
        "log_message": "Audio transcribed",
        "output_refs": [output_ref],
    }


def _speaker_count(payload: dict[str, Any]) -> int:
    try:
        count = int(payload.get("speakers") or 0)
    except (TypeError, ValueError) as exc:
        raise TranscriptionRequestError("speakers must be a whole number") from exc
    if not 0 <= count <= 8:
        raise TranscriptionRequestError("speakers must be between 0 (automatic) and 8")
    return count


_REQUEST_FAILURES = {"model_unavailable", "unsupported", "invalid_request", "empty_audio", "decode_failed"}


def _render_script(asset: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """The script lines a render was made from and, when recorded, each line's span in it."""
    metadata = asset.metadata or {}
    lines = [segment for segment in metadata.get("script_segments") or [] if isinstance(segment, dict)
             and str(segment.get("text") or "").strip()]
    if not lines and str(metadata.get("text") or "").strip():
        lines = [{"speaker": str(metadata.get("speaker") or ""), "text": str(metadata["text"])}]
    if not lines:
        raise TranscriptionRequestError(f"{asset.id} records no script to check against")
    timeline = metadata.get("timeline")
    return lines, timeline if isinstance(timeline, list) else None


def _execute_timed(job: Any, job_store: Any, asset: Any, audio: bytes, suffix: str, provider: Any) -> dict[str, Any]:
    """Timed transcription; with ``check_render`` it scores a render against the script it was made from."""
    from .transcripts import render_check

    payload = job.input_payload or {}
    speakers = _speaker_count(payload)
    language = str(payload.get("language") or "").strip()[:16]
    check = bool(payload.get("check_render"))
    script = _render_script(asset) if check else None
    # A render check compares words, so it never needs speaker labels.
    diarize = bool(payload.get("diarize", True)) and not check
    document = transcribe_timed_audio(audio, f"source{suffix}", language=language, diarize=diarize,
                                      speakers=speakers, provider=provider)
    document = document.model_copy(update={"source_asset_id": asset.id})
    output_ref: dict[str, Any] = {"type": "transcript", "title": "Transcript", "content": document.text,
                                  "provider_id": document.engine, "source_asset_id": asset.id,
                                  "speakers": document.speakers, "duration": document.duration}
    log_message = "Audio transcribed with timing"
    if script is not None:
        report = render_check(document, *script)
        output_ref.update(type="render_check", title="Render check", render_check=report)
        log_message = f"Word error rate {float(report['word_error_rate']):.1%} against the script"
    if payload.get("save_transcript", not check):
        record = save_transcript_document(job.id, job_store, asset, document)
        output_ref.update(asset_id=record.id, title=record.metadata["title"], mime_type=record.mime_type)
    return {"content": document.text, "log_message": log_message, "output_refs": [output_ref]}


TRANSCRIPTION_RATE = 16_000


def speech_wav_16k(audio: bytes, filename: str) -> bytes:
    """Any recording as 16 kHz mono PCM WAV: all the ASR reads, and a small upload.

    Model services cap uploads (``OMNIX_MAX_UPLOAD_BYTES``, 50 MB by default); at
    16 kHz mono that is about 26 minutes, where 44.1 kHz stereo WAV is under 5.
    soundfile reads WAV, FLAC, Ogg and MP3; anything else goes through FFmpeg.
    """
    import io
    import subprocess
    import wave

    import numpy as np

    try:
        import soundfile as sf

        samples, rate = sf.read(io.BytesIO(audio), dtype="float32", always_2d=True)
        mono = samples.mean(axis=1)
        if rate != TRANSCRIPTION_RATE and len(mono):
            length = max(1, int(round(len(mono) * TRANSCRIPTION_RATE / rate)))
            mono = np.interp(np.linspace(0, len(mono) - 1, length), np.arange(len(mono)), mono)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(TRANSCRIPTION_RATE)
            target.writeframes((np.clip(mono, -1.0, 1.0) * 32767).astype("<i2").tobytes())
        return buffer.getvalue()
    except Exception:
        from app.runtime.ffmpeg import ffmpeg_binary

        suffix = Path(filename or "audio.wav").suffix or ".wav"
        with tempfile.TemporaryDirectory(prefix="omnix-stt-") as directory:
            source = Path(directory) / f"source{suffix}"
            source.write_bytes(audio)
            target_path = Path(directory) / "speech.wav"
            result = subprocess.run([ffmpeg_binary("transcription"), "-hide_banner", "-loglevel", "error", "-y",
                                     "-i", str(source), "-vn", "-ac", "1", "-ar", str(TRANSCRIPTION_RATE),
                                     "-c:a", "pcm_s16le", str(target_path)], capture_output=True, timeout=600, check=False)
            if result.returncode != 0:
                raise TranscriptionRequestError("The recording could not be decoded") from None
            return target_path.read_bytes()


def transcribe_timed_audio(audio: bytes, filename: str, *, language: str = "", diarize: bool = True,
                           speakers: int = 0, provider: Any = None) -> Any:
    """A timed (and, with ``diarize``, speaker-labelled) ``TranscriptDocument`` of a recording.

    The recording goes to the STT service as 16 kHz mono (``speech_wav_16k``).
    ``TranscriptionRequestError`` when retrying cannot help (no timed engine, a
    model to install, unreadable audio); ``RuntimeError`` otherwise.
    """
    from app.providers.catalog import DIARIZATION, WORD_TIMESTAMPS, provider_supports

    from .transcripts import TranscriptDocument

    if provider is None:
        from app.providers.service import get_stt_provider

        provider = get_stt_provider()
        if provider is None:
            raise RuntimeError("No speech-to-text provider is configured")
    name = str(getattr(provider, "provider_name", "") or "")
    timed = getattr(provider, "transcribe_timed", None)
    if timed is None or not provider_supports(name, WORD_TIMESTAMPS, "stt"):
        raise TranscriptionRequestError("The configured speech-to-text provider has no timed transcription")
    if diarize and not provider_supports(name, DIARIZATION, "stt"):
        raise TranscriptionRequestError("The configured speech-to-text provider cannot label speakers")
    speech = speech_wav_16k(audio, filename)
    with tempfile.TemporaryDirectory(prefix="omnix-stt-") as directory:
        source = Path(directory) / "speech.wav"
        source.write_bytes(speech)
        result = timed(str(source), language=language, diarize=diarize, speakers=int(speakers or 0))
    if not result.get("success"):
        message = str(result.get("error") or "Timed transcription failed")
        if result.get("code") in _REQUEST_FAILURES:
            raise TranscriptionRequestError(message)
        raise RuntimeError(message)
    return TranscriptDocument.model_validate(result["document"]).normalized()


def save_transcript_document(job_id: str, job_store: Any, source: Any, document: Any) -> Any:
    """Store a ``TranscriptDocument`` as the job's ``transcript`` asset, the source audio as its parent."""
    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.jobs.inline_execution import require_execution_authority
    from app.runtime.paths import resources_data_root

    output_dir = resources_data_root() / "voice_studio" / "transcripts"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(char if char.isalnum() or char in "-_." else "-" for char in job_id)
    path = output_dir / f"{safe}.json"
    require_execution_authority(job_store, job_id)
    path.write_text(json.dumps(document.model_dump(by_alias=True), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    title = f"Transcript of {source.metadata.get('title') or source.metadata.get('profile_name') or source.id}"
    require_execution_authority(job_store, job_id)
    return default_asset_store().upsert_asset(AssetRecord(
        id=f"transcript:{safe}",
        module="stt",
        type=AssetType.TRANSCRIPT,
        mime_type="application/json",
        storage_path=str(path),
        metadata={"title": title, "provider": document.engine, "text": document.text[:2000],
                  "duration": document.duration, "language": document.language, "speakers": document.speakers,
                  "diarized": document.diarized, "schema": document.schema_},
        source_job_id=job_id,
        parent_asset_ids=[source.id],
        created_at=datetime.now(timezone.utc).isoformat(),
        compat={"contract": document.schema_},
    ))


def execute_subtitles_job(job: Any, *, job_store: Any = None) -> dict[str, Any]:
    """``voice.subtitles``: SRT, WebVTT or plain-text files from a stored transcript (recipes use it)."""
    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.assets.content import read_asset_bytes
    from app.jobs.inline_execution import require_execution_authority
    from app.runtime.paths import resources_data_root

    from .transcripts import document_from_stored, export_transcript

    payload = job.input_payload or {}
    asset_id = str((job.input_ref or {}).get("asset_id") or payload.get("asset_id") or "").strip()
    store = default_asset_store()
    transcript = store.get_asset(asset_id) if asset_id else None
    if transcript is None or transcript.type != AssetType.TRANSCRIPT:
        raise TranscriptionRequestError("Subtitles are made from a stored transcript")
    formats = [fmt for fmt in payload.get("formats") or ["srt", "vtt"] if fmt in {"srt", "vtt", "txt"}]
    if not formats:
        raise TranscriptionRequestError("Choose srt, vtt or txt")
    document = document_from_stored(json.loads(read_asset_bytes(transcript, max_bytes=20 * 1024 * 1024)))
    output_dir = resources_data_root() / "voice_studio" / "subtitles"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(char if char.isalnum() or char in "-_." else "-" for char in job.id)
    title = str(transcript.metadata.get("title") or asset_id)
    refs = []
    for fmt in formats:
        text, mime = export_transcript(document, fmt)
        path = output_dir / f"{safe}.{fmt}"
        require_execution_authority(job_store, job.id)
        path.write_text(text, encoding="utf-8")
        record = store.upsert_asset(AssetRecord(
            id=f"export:subtitles-{safe}-{fmt}", module="voice", type=AssetType.EXPORT, mime_type=mime,
            storage_path=str(path), metadata={"title": f"{title} ({fmt.upper()})", "format": fmt},
            source_job_id=job.id, parent_asset_ids=[asset_id], created_at=datetime.now(timezone.utc).isoformat(),
            compat={"contract": "voice_studio_subtitles_v1"},
        ))
        refs.append({"type": "export", "kind": f"subtitles_{fmt}", "asset_id": record.id, "title": record.metadata["title"],
                     "mime_type": mime})
    return {"content": f"{len(refs)} subtitle file(s)", "log_message": "Subtitles written", "output_refs": refs}


__all__ = ["TranscriptionRequestError", "execute_subtitles_job", "execute_transcribe_job", "save_transcript_document", "speech_wav_16k",
           "transcribe_timed_audio"]
