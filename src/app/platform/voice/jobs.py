"""Inline Voice Studio job execution for local backend wiring."""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import tempfile
import wave
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from app.assets import AssetRecord, AssetType, default_asset_store
from app.providers.tts_service import voice_stem
from app.persistence.blob_store import default_blob_store
from app.runtime.paths import resources_data_root

from app.jobs.models import CompleteJobRequest, CreateJobRequest, FailJobRequest, JobRecord
from app.jobs.inline_execution import mark_inline_execution, require_execution_authority

from .script import DEFAULT_UNTAGGED_SPEAKER, MAX_PAUSE_MS, parse_script, script_speakers

VOICE_STUDIO_JOB_TYPES = {
    "tts.synthesize",
    "tts.multi_speaker_synthesize",
    "voice-cloning.create-profile",
    "voice-cloning.transcribe-sample",
    "voice.export",
    "voice.restitch",
    "voice.design",
    "voice.design.save",
    "voice.blend",
    "audio.isolate",
    "audio.enhance",
    "audio.watermark-detect",
    "voice.subtitles",
    "stt.transcribe",
    "models.install",
    "models.remove",
}


def _failure_code(exc: Exception) -> tuple[str, bool]:
    """The failure code and whether a retry could help."""
    from app.providers.exceptions import TtsEngineNotLoaded

    from .audio_service import AudioServiceUnavailable, AudioToolRequestError
    from .design import DesignRequestError
    from .export import ExportRequestError
    from .model_install import ModelInstallError
    from .transcription import TranscriptionRequestError
    from .watermarking import WatermarkUnavailable

    if isinstance(exc, TtsEngineNotLoaded):
        # Retrying would only find the same engine loaded; the user selects it.
        return "engine_not_loaded", False
    if isinstance(exc, (ExportRequestError, TranscriptionRequestError, ModelInstallError, DesignRequestError,
                        AudioToolRequestError)):
        return "invalid_request", False
    if isinstance(exc, WatermarkUnavailable):
        return "watermark_unavailable", True
    if isinstance(exc, AudioServiceUnavailable):
        return "audio_service_unavailable", True
    return "voice_studio_job_failed", True


SWAP_RETRY_SECONDS = 5.0
# A job waits this long for its engine to be swapped in at most, then fails with the reason.
SWAP_WAIT_LIMIT_SECONDS = 1800.0


def _defer_for_swap(job_store: Any, job: JobRecord, exc: Exception) -> JobRecord | None:
    """A pinned engine is not loaded: ask the swap controller for it and wait, without spending an attempt.

    Only with the TTS service (swaps need it) and a worker that can defer. A
    request the controller already failed (the engine does not fit, or would
    not load) fails the job with that reason instead of waiting again.
    """
    from app.providers.exceptions import TtsEngineNotLoaded

    from .swap_controller import swaps_enabled

    if not isinstance(exc, TtsEngineNotLoaded) or not callable(getattr(job_store, "defer_job", None)):
        return None
    if not swaps_enabled():
        return None
    from app.persistence.tts_swap import request_swap, swap_request_failure, swap_wait_seconds

    failure = swap_request_failure(job.id)
    if failure:
        exc.args = (f"{exc.requested} could not be swapped in: {failure}",)
        return None
    if swap_wait_seconds(job.id) > SWAP_WAIT_LIMIT_SECONDS:  # timed from its first request, not its queueing
        exc.args = (f"{exc.requested} was not swapped in within {SWAP_WAIT_LIMIT_SECONDS / 60:.0f} minutes",)
        return None
    request_swap(exc.requested, job.id)
    return job_store.defer_job(job.id, delay_seconds=SWAP_RETRY_SECONDS,
                               reason=f"waiting for {exc.requested} to be swapped in") or job


def wait_for_engine(job_store: Any, job: Any, exc: Exception) -> Any | None:
    """For other modules' jobs (dubbing): wait for a pinned engine the way Voice Studio's jobs do."""
    return _defer_for_swap(job_store, job, exc)


def clone_voice(job: Any, job_store: Any, *, name: str, wav: bytes, reference_text: str, language: str) -> str:
    """Store ``wav`` as a library voice with its exact words (no STT); returns the voice id to speak with."""
    result = execute_clone_profile(job, {"profile_name": name, "language": language, "quality": "Draft",
                                         "reference_text": reference_text, "source_kind": "extracted",
                                         "source_file_name": f"{name}.wav"}, wav, job_store=job_store)
    return str(result["output_refs"][0]["asset_id"])


def _finish_swap_wait(job: JobRecord) -> None:
    """Tell the swap controller this job no longer needs a swapped-in engine."""
    from .swap_controller import swaps_enabled

    if not swaps_enabled():
        return
    try:
        from app.persistence.tts_swap import finish_swap_request

        finish_swap_request(job.id)
    except Exception as exc:  # never let bookkeeping fail a finished job
        import logging

        logging.getLogger(__name__).warning("Swap request of %s could not be closed: %s", job.id, exc)


def execute_voice_studio_job(job_store: Any, job: JobRecord) -> JobRecord:
    """Run a Voice Studio job synchronously and persist generated assets."""
    job_store.mark_running(job.id)
    try:
        if job.type == "voice-cloning.create-profile":
            result = _execute_clone_job(job, job_store=job_store)
        elif job.type == "voice-cloning.transcribe-sample":
            result = _execute_transcribe_sample_job(job)
        elif job.type in {"tts.synthesize", "tts.multi_speaker_synthesize", "voice.restitch"}:
            result = _execute_tts_job(job, job_store=job_store)
        elif job.type in {"models.install", "models.remove", "models.verify"}:
            from .model_install import execute_model_job

            result = execute_model_job(job, job_store=job_store)
        elif job.type == "voice.export":
            from .export import execute_export_job

            result = execute_export_job(job, job_store=job_store)
        elif job.type == "stt.transcribe":
            from .transcription import execute_transcribe_job

            result = execute_transcribe_job(job, job_store=job_store)
        elif job.type == "voice.subtitles":
            from .transcription import execute_subtitles_job

            result = execute_subtitles_job(job, job_store=job_store)
        elif job.type == "voice.design":
            from .design import execute_design_job

            result = execute_design_job(job, job_store=job_store)
        elif job.type == "voice.design.save":
            from .design import execute_design_save_job

            result = execute_design_save_job(job, job_store=job_store)
        elif job.type == "voice.blend":
            from .design import execute_blend_job

            result = execute_blend_job(job, job_store=job_store)
        elif job.type in {"audio.isolate", "audio.enhance", "audio.watermark-detect"}:
            from .audio_tools import execute_detect_job, execute_enhance_job, execute_isolate_job

            run = {"audio.isolate": execute_isolate_job, "audio.enhance": execute_enhance_job,
                   "audio.watermark-detect": execute_detect_job}[job.type]
            result = run(job, job_store=job_store)
        else:  # pragma: no cover - guarded by caller.
            raise RuntimeError(f"Unsupported Voice Studio job type: {job.type}")
    except Exception as exc:
        from app.models.packs import PackCancelled

        if isinstance(exc, PackCancelled):
            # The user cancelled a download: the partial pack is gone, and the job ends as cancelled.
            return job_store.finalize_cancel(job.id, "cancelled by the user") or job
        deferred = _defer_for_swap(job_store, job, exc)
        if deferred is not None:
            return deferred
        _finish_swap_wait(job)
        code, retryable = _failure_code(exc)
        failed = job_store.fail_job(
            job.id,
            FailJobRequest(
                code=code,
                message=str(exc) or "Voice Studio job failed",
                retryable=retryable,
                details={"job_type": job.type, "module": job.module},
            ),
        )
        return failed or job

    _finish_swap_wait(job)
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


def _execute_clone_job(job: JobRecord, *, job_store: Any = None) -> dict[str, Any]:
    payload = job.input_payload or {}
    return execute_clone_profile(job, payload, _sample_audio_bytes(payload), job_store=job_store)


def execute_clone_profile(job: JobRecord, payload: dict[str, Any], audio_bytes: bytes, *,
                          job_store: Any = None) -> dict[str, Any]:
    """Clean, check and store a voice sample as a library voice (uploaded, recorded or designed).

    A ``design`` entry in ``payload`` (the description, seed, model revision and
    parameters) marks the voice ``source: designed`` and is kept on the asset.
    """
    profile_name = _require_text(payload.get("profile_name"), "Voice name is required")
    source_file_name = _text(payload.get("source_file_name")) or f"{profile_name}.wav"
    suffix = Path(source_file_name).suffix.lower() or ".wav"
    if suffix not in {".wav", ".mp3", ".mp4", ".m4a", ".webm", ".ogg", ".flac"}:
        suffix = ".wav"

    from .sample_cleanup import clean_sample

    preparation = _prepare_sample(audio_bytes, source_file_name, payload)
    audio_bytes = preparation.pop("audio")
    if preparation.get("steps"):
        suffix = ".wav"
    # Trim silence, level the loudness, and check noise and clipping before cloning.
    audio_bytes, cleaned_suffix, sample_report = clean_sample(audio_bytes, quality=_text(payload.get("quality")))
    suffix = cleaned_suffix or suffix

    voice_id = _safe_segment(profile_name)
    clone_dir = _voice_clone_dir()
    clone_dir.mkdir(parents=True, exist_ok=True)
    clone_path = clone_dir / f"{voice_id}{suffix}"
    require_execution_authority(job_store, job.id)
    clone_path.write_bytes(audio_bytes)
    reference_text, transcript_source, stt_provider = _reference_transcript(payload, clone_path)
    require_execution_authority(job_store, job.id)
    transcript_path = _write_reference_metadata(
        clone_dir=clone_dir,
        voice_id=voice_id,
        profile_name=profile_name,
        clone_path=clone_path,
        language=_text(payload.get("language")) or "English (US)",
        reference_text=reference_text,
        transcript_source=transcript_source,
        stt_provider=stt_provider,
    )
    enriched_payload = {
        **payload,
        "reference_text": reference_text,
        "transcript_source": transcript_source,
        "transcript_path": str(transcript_path) if transcript_path else "",
        "stt_provider_id": stt_provider,
    }
    require_execution_authority(job_store, job.id)
    _upsert_legacy_voice_manifest(voice_id, profile_name, enriched_payload, clone_path)

    require_execution_authority(job_store, job.id)
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
                "reference_text": reference_text,
                "transcript_source": transcript_source,
                "transcript_path": str(transcript_path) if transcript_path else "",
                "stt_provider_id": stt_provider,
                "has_audio": True,
                "source": "blended" if payload.get("blend") else "designed" if payload.get("design") else "cloned",
                "sample_check": sample_report.as_metadata(),
                **({"sample_preparation": preparation["steps"]} if preparation.get("steps") else {}),
                **({"design": dict(payload["design"])} if payload.get("design") else {}),
                **({"blend": dict(payload["blend"])} if payload.get("blend") else {}),
            },
            source_job_id=job.id,
            created_at=_utcnow(),
            compat={"contract": "voice_studio_clone_v1", "storage_hint": "resources/voice_clones"},
        )
    )
    output_ref = _asset_output_ref(asset, title=profile_name)
    output_ref["sample_check"] = sample_report.as_metadata()
    warnings = " ".join(sample_report.warnings)
    return {
        "content": f"Voice clone '{profile_name}' saved to {clone_path}" + (f". {warnings}" if warnings else ""),
        "log_message": "Voice clone profile stored locally",
        "output_refs": [output_ref],
    }


def _prepare_sample(audio: bytes, filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Optional audio-service steps before the sample check: isolate the voice, then denoise it.

    Asked for in the clone form (``isolate_vocals``, ``enhance_sample``). Each
    needs the audio service; when it is unavailable the clone fails rather than
    quietly cloning the unprepared sample.
    """
    steps: list[str] = []
    if not (payload.get("isolate_vocals") or payload.get("enhance_sample")):
        return {"audio": audio, "steps": steps}
    from .audio_service import AudioServiceClient

    client = AudioServiceClient()
    if payload.get("isolate_vocals"):
        stems = client.isolate(audio, filename, model="roformer")
        audio, filename = stems.vocals, "vocals.wav"
        steps.append(f"isolated vocals ({stems.model})")
    if payload.get("enhance_sample"):
        audio, details = client.enhance(audio, filename)
        steps.append(f"enhanced ({details.get('model') or 'speech enhancement'})")
    return {"audio": audio, "steps": steps}


def _execute_transcribe_sample_job(job: JobRecord) -> dict[str, Any]:
    """Transcribe a clone sample without creating a voice-library entry."""
    payload = job.input_payload or {}
    audio_bytes = _sample_audio_bytes(payload)
    source_file_name = _text(payload.get("source_file_name")) or "voice-sample.wav"
    suffix = Path(source_file_name).suffix.lower() or ".wav"
    if suffix not in {".wav", ".mp3", ".mp4", ".m4a", ".webm", ".ogg", ".flac"}:
        suffix = ".wav"

    with tempfile.TemporaryDirectory(prefix="omnix-voice-transcript-") as temp_dir:
        sample_path = Path(temp_dir) / f"sample{suffix}"
        sample_path.write_bytes(audio_bytes)
        transcript, _source, provider_name = _reference_transcript(
            {**payload, "reference_text": "", "generate_transcript": True},
            sample_path,
        )

    return {
        "content": transcript,
        "log_message": "Voice clone sample transcribed",
        "output_refs": [
            {
                "type": "transcript",
                "title": "Reference transcript",
                "content": transcript,
                "provider_id": provider_name,
            }
        ],
    }


def _reference_transcript(payload: dict[str, Any], clone_path: Path) -> tuple[str, str, str]:
    manual_text = _text(payload.get("reference_text"))
    if manual_text:
        return manual_text, "manual", ""
    if not bool(payload.get("generate_transcript")):
        return "", "", ""

    from app.providers.service import get_stt_provider

    requested_provider = _text(payload.get("stt_provider_id"))
    provider = get_stt_provider(requested_provider or None)
    if provider is None:
        raise ValueError(
            "The configured STT provider is unavailable; enter a reference transcript "
            "manually or disable STT generation"
        )

    result = provider.transcribe(
        str(clone_path),
        language=_text(payload.get("language")) or None,
    )
    transcript = _text(result.get("text")) if isinstance(result, dict) else ""
    if not isinstance(result, dict) or not result.get("success") or not transcript:
        detail = _text(result.get("error")) if isinstance(result, dict) else ""
        raise ValueError(
            f"STT could not generate a reference transcript{': ' + detail if detail else ''}"
        )

    provider_name = (
        requested_provider
        or _text(getattr(provider, "provider_name", ""))
        or "configured-stt"
    )
    return transcript, "stt", provider_name


def _write_reference_metadata(
    *,
    clone_dir: Path,
    voice_id: str,
    profile_name: str,
    clone_path: Path,
    language: str,
    reference_text: str,
    transcript_source: str,
    stt_provider: str,
) -> Path | None:
    if not reference_text:
        return None
    transcript_path = clone_dir / f"{voice_id}.json"
    transcript_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "voice_id": voice_id,
                "profile_name": profile_name,
                "audio_path": str(clone_path),
                "language": language,
                "ref_text": reference_text,
                "transcript_source": transcript_source,
                "stt_provider": stt_provider,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return transcript_path


def tts_engine_id(payload: dict[str, Any]) -> str:
    """The engine a job names (``tts:`` facade prefixes allowed); empty means the selected one."""
    return _text(payload.get("provider_id")).removeprefix("tts:")


def _script_takes(script_id: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """A saved script's lines as segments, and each line's selected take."""
    from .scripts_repository import get_script

    script = get_script(script_id)
    segments: list[dict[str, Any]] = []
    selected: dict[str, dict[str, Any]] = {}
    for line in script["lines"]:
        segment: dict[str, Any] = {"index": line["position"], "speaker": line["speaker"], "text": line["text"],
                                   "line_id": line["id"]}
        if line.get("pause_before_ms") is not None:
            segment["pause_before_ms"] = line["pause_before_ms"]
        if line.get("delivery_instruction"):
            segment["delivery_instruction"] = line["delivery_instruction"]
        segments.append(segment)
        take = next((entry for entry in line.get("takes", []) if entry["id"] == line.get("selected_take_id")), None)
        if take is not None:
            selected[line["id"]] = take
    return segments, selected


def _take_audio(take: dict[str, Any]) -> bytes:
    from app.assets.content import read_asset_bytes

    asset = default_asset_store().get_asset(str(take["asset_id"]))
    if asset is None:
        raise RuntimeError(f"take {take['id']} lost its audio ({take['asset_id']}); render the line again")
    return read_asset_bytes(asset)


def _store_take(job: JobRecord, job_store: Any, *, script_id: str, line_id: str, engine: str, text: str,
                wav_bytes: bytes, duration: float) -> None:
    """Keep one rendered line as a selectable take (asset type ``voice_take``)."""
    from .scripts_repository import record_take
    from .watermarking import mark

    wav_bytes, watermark = mark(wav_bytes)

    take_dir = resources_data_root() / "voice_studio" / "takes"
    take_dir.mkdir(parents=True, exist_ok=True)
    asset_id = f"voice_take:{_safe_segment(job.id)}-{_safe_segment(line_id)}"
    path = take_dir / f"{_safe_segment(job.id)}-{_safe_segment(line_id)}.wav"
    require_execution_authority(job_store, job.id)
    path.write_bytes(wav_bytes)
    _upsert_asset(AssetRecord(
        id=asset_id, module="voice", type=AssetType.VOICE_TAKE, mime_type="audio/wav", storage_path=str(path),
        metadata={"title": text[:80], "script_id": script_id, "line_id": line_id, "engine": engine, "duration": duration,
                  **({"watermark": watermark} if watermark else {})},
        source_job_id=job.id, created_at=_utcnow(), compat={"contract": "voice_studio_take_v1"},
    ))
    record_take(script_id=script_id, line_id=line_id, asset_id=asset_id, job_id=job.id, engine=engine,
                text=text, duration=duration)


def _execute_tts_job(job: JobRecord, *, job_store: Any = None) -> dict[str, Any]:
    from app.providers.catalog import DELIVERY_INSTRUCTION, provider_supports
    from app.providers.service import pinned_tts_provider
    from app.providers.tts_priority import generation_class

    from .assembly import AudioSpan, PausePolicy, assemble_chapter
    from .effects import effect_ids, master_take, to_mono_pcm16
    from .output_settings import NEUTRAL

    payload = job.input_payload or {}
    restitch = job.type == "voice.restitch"
    script_id = _text(payload.get("script_id"))
    selected_takes: dict[str, dict[str, Any]] = {}
    if script_id:
        script_segments, selected_takes = _script_takes(script_id)
    if restitch:
        if not script_id:
            raise ValueError("voice.restitch needs a saved script")
        segments = script_segments
        text = "\n".join(f"{segment['speaker']}: {segment['text']}" for segment in segments)
    else:
        text = _require_text(payload.get("text"), "Text is required")
        segments = _script_segments(payload, text)
    raw_assignments = payload.get("character_voice_assignments")
    assignments: list[Any] = raw_assignments if isinstance(raw_assignments, list) else []
    assignments_by_speaker = _assignments_by_speaker(assignments)
    primary_voice = _text(payload.get("voice_id")) or _first_assignment_voice(assignments)
    default_speaker = voice_stem(primary_voice) or _text(payload.get("speaker")) or DEFAULT_UNTAGGED_SPEAKER
    # Lines to render again; the other lines of a saved script reuse their selected take.
    render_lines = payload.get("render_line_ids")
    render_only = {str(item) for item in render_lines} if script_id and isinstance(render_lines, list) else None

    # The engine the job names, never switched to (see ``pinned_tts_provider``); loaded on first need.
    resolved: dict[str, Any] = {}

    def engine_provider() -> Any:
        if "provider" not in resolved:
            provider = pinned_tts_provider(tts_engine_id(payload) or None)
            if provider is None:
                raise RuntimeError("Configured TTS provider is unavailable")
            resolved["provider"] = provider
            resolved["engine"] = _text(getattr(provider, "provider_name", "")) or tts_engine_id(payload)
        return resolved["provider"]

    # Studio renders are not live speech: they yield the GPU to calls (previews ask a little sooner).
    priority: Literal["preview", "offline"] = "preview" if (job.priority or 0) >= 1 else "offline"

    spans: list[AudioSpan] = []
    segment_outputs: list[dict[str, Any]] = []
    for position, segment in enumerate(segments):
        speaker_name = _text(segment.get("speaker")) or DEFAULT_UNTAGGED_SPEAKER
        assignment = assignments_by_speaker.get(speaker_name.casefold(), {})
        voice_id = _text(assignment.get("voice_id")) or primary_voice
        generated_speaker = voice_stem(voice_id) or speaker_name or default_speaker
        instruction = _text(segment.get("delivery_instruction")) or _text(assignment.get("delivery_instruction"))
        line_id = _text(segment.get("line_id"))
        reuse = selected_takes.get(line_id) if line_id and (restitch or (render_only is not None and line_id not in render_only)) else None
        if restitch and reuse is None:
            raise ValueError(f"line {position + 1} ({speaker_name}) has no take yet; render it first")
        if reuse is not None:
            wav_bytes = _take_audio(reuse)
            metadata = {**_wav_metadata(wav_bytes), "provider_success": True, "provider_fallback": False,
                        "provider_error": "", "voice_controls": {}, "reused_take_id": reuse["id"]}
            sent_instruction = ""
        else:
            provider = engine_provider()
            delivery_supported = provider_supports(resolved["engine"], DELIVERY_INSTRUCTION, "tts")
            sent_instruction = instruction if delivery_supported else ""
            with generation_class(priority):
                wav_bytes, metadata = _generate_audio_bytes(
                    _text(segment.get("text")), speaker=generated_speaker, payload=payload,
                    provider=provider, instruct=sent_instruction or None,
                )
            if script_id and line_id:
                _store_take(job, job_store, script_id=script_id, line_id=line_id, engine=resolved["engine"],
                            text=_text(segment.get("text")), wav_bytes=wav_bytes,
                            duration=float(metadata.get("duration") or 0.0))
        pause_before = segment.get("pause_before_ms")
        spans.append(AudioSpan(
            render_id=f"segment-{position}",
            render_key=f"{job.id}:{position}",
            speaker_id=speaker_name.casefold(),
            source_text=_text(segment.get("text")),
            wav_bytes=to_mono_pcm16(wav_bytes),
            pause_before_ms=int(pause_before) if isinstance(pause_before, (int, float)) else None,
        ))
        segment_outputs.append(
            {
                "index": int(segment.get("index") or len(segment_outputs)),
                "speaker": speaker_name,
                "text": _text(segment.get("text")),
                "voice_id": voice_id,
                "style": _text(assignment.get("style")),
                "delivery_instruction": sent_instruction,
                "pause_before_ms": spans[-1].pause_before_ms,
                "sample_rate": metadata.get("sample_rate"),
                "duration": metadata.get("duration"),
                "provider_success": metadata.get("provider_success"),
                "provider_fallback": metadata.get("provider_fallback"),
                "provider_error": metadata.get("provider_error"),
                "voice_controls": metadata.get("voice_controls"),
                "line_id": line_id,
                "reused_take_id": metadata.get("reused_take_id", ""),
            }
        )

    if not spans:
        raise ValueError("No TTS audio segments were generated")
    # Pauses and per-speaker loudness, the same assembly audiobook chapters use.
    assembled = assemble_chapter(spans, policy=PausePolicy())
    raw_settings = payload.get("output_settings")
    output_settings: dict[str, Any] = raw_settings if isinstance(raw_settings, dict) else {}
    volume_db = _volume_db(output_settings, NEUTRAL["volume"])
    requested_effects = effect_ids(payload.get("audio_effects"))
    wav_bytes, applied_effects = master_take(assembled.wav_bytes, requested_effects, volume_db=volume_db)
    from .watermarking import mark

    # After the effects chain, before anything is written (opt-in; see ``watermarking``).
    wav_bytes, watermark = mark(wav_bytes)
    combined_metadata = _wav_metadata(wav_bytes)
    combined_metadata["segment_count"] = len(spans)
    title = _tts_title(payload, job)
    output_dir = resources_data_root() / "voice_studio"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_safe_segment(title)}-{_safe_segment(job.id)}.wav"
    require_execution_authority(job_store, job.id)
    output_path.write_bytes(wav_bytes)

    metadata = {
        "title": title,
        "text": text,
        "speaker": default_speaker,
        "provider_id": tts_engine_id(payload),
        # The engine that actually rendered (pinning guarantees it is the one asked for).
        "rendered_engine": resolved.get("engine", ""),
        "script_id": script_id,
        "script_mode": "multi_speaker" if len({segment["speaker"] for segment in segments}) > 1 else "single_speaker",
        "script_speakers": payload.get("script_speakers") or script_speakers(segments),
        "script_segments": segments,
        "segment_outputs": segment_outputs,
        "character_voice_assignments": assignments,
        "output_settings": output_settings,
        "audio_effects": applied_effects,
        "volume_db": volume_db,
        "assembly_key": assembled.assembly_key,
        **({"watermark": watermark} if watermark else {}),
        "timeline": [
            {"segment": index, "start": entry.start_seconds, "end": entry.end_seconds,
             "pause_before": entry.pause_before_seconds}
            for index, entry in enumerate(assembled.timeline)
        ],
        **combined_metadata,
    }
    require_execution_authority(job_store, job.id)
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
            # Served from the stored asset; job rows never embed the audio.
            "audio_url": asset_audio_url(asset.id),
            "duration": combined_metadata.get("duration"),
            "segments": segment_outputs,
        }
    )
    return {
        "content": f"Speech audio saved to {output_path}",
        "log_message": "Voice Studio speech generated per script segment and saved",
        "output_refs": [output_ref],
    }


def _volume_db(output_settings: dict[str, Any], neutral: float) -> float:
    from .output_settings import audio_adjustments

    return float(audio_adjustments(output_settings).get("volume", neutral) or 0.0)


def _generate_audio_bytes(
    text: str, *, speaker: str, payload: dict[str, Any], provider: Any = None, instruct: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """One segment from the engine, with speed and pitch applied; volume waits for the whole take."""
    from app.providers.exceptions import TtsEngineNotLoaded

    try:
        from app.providers.service import pinned_tts_provider

        from .output_settings import adjust_wav, audio_adjustments, sampling_overrides

        if provider is None:
            provider = pinned_tts_provider(tts_engine_id(payload) or None)
        if provider is None:
            raise RuntimeError("Configured TTS provider is unavailable")
        output_settings = payload.get("output_settings") if isinstance(payload.get("output_settings"), dict) else {}
        sampling = sampling_overrides(str(getattr(provider, "provider_name", "") or ""), output_settings)
        if instruct:
            sampling = {**sampling, "instruct": instruct}
        result = provider.generate_audio(
            text,
            speaker=speaker,
            language=_tts_language_code(payload.get("language")),
            parity_mode=True,
            non_streaming_mode=True,
            use_cuda_graphs=False,
            **sampling,
        )
        if not isinstance(result, dict):
            raise RuntimeError("TTS provider returned an invalid response")

        provider_error = _text(result.get("error"))
        provider_fallback = bool(result.get("is_fallback") or result.get("fallback"))
        if not result.get("success") or provider_fallback:
            reason = provider_error or _text(result.get("fallback_reason")) or "TTS provider did not produce speech audio"
            raise RuntimeError(reason)

        encoded = _text(result.get("audio_base64")) or _text(result.get("audio"))
        if not encoded:
            raise RuntimeError("TTS provider returned no speech audio")
        try:
            wav_bytes = base64.b64decode(encoded)
        except Exception as exc:
            raise RuntimeError("TTS provider returned invalid base64 audio") from exc
        if not wav_bytes:
            raise RuntimeError("TTS provider returned empty speech audio")
        # Speed and pitch per segment; volume is applied once to the assembled take.
        adjustments = {name: value for name, value in audio_adjustments(output_settings).items() if name != "volume"}
        if adjustments:
            wav_bytes = adjust_wav(wav_bytes, adjustments)
        timing = _wav_metadata(wav_bytes) if adjustments else {
            "sample_rate": result.get("sample_rate"), "duration": result.get("duration"),
        }
        return wav_bytes, {
            **timing,
            "provider_success": True,
            "provider_fallback": False,
            "provider_error": "",
            "voice_controls": {"sampling": {key: value for key, value in sampling.items() if key != "instruct"},
                               "audio": adjustments},
        }
    except TtsEngineNotLoaded:
        raise
    except Exception as exc:
        raise RuntimeError(f"Real TTS generation failed for speaker '{speaker}': {exc}") from exc


def _tts_language_code(value: Any) -> str:
    """Normalize UI language labels to provider language codes.

    The Qwen3 provider maps short codes such as ``en`` to its supported
    language name (``English``). Podcast forms use display labels like
    ``English (US)``, which the provider runtime does not accept directly.
    """
    raw = _text(value)
    if not raw:
        return "en"

    compact = re.sub(r"[^a-z]+", "", raw.casefold())
    first_word = re.split(r"[^a-z]+", raw.casefold(), maxsplit=1)[0]
    language_map = {
        "en": "en",
        "eng": "en",
        "english": "en",
        "englishus": "en",
        "englishuk": "en",
        "enus": "en",
        "engb": "en",
        "zh": "zh",
        "chinese": "zh",
        "mandarin": "zh",
        "ja": "ja",
        "japanese": "ja",
        "fr": "fr",
        "french": "fr",
        "de": "de",
        "german": "de",
        "es": "es",
        "spanish": "es",
        "it": "it",
        "italian": "it",
        "ru": "ru",
        "russian": "ru",
        "ko": "ko",
        "korean": "ko",
        "pt": "pt",
        "portuguese": "pt",
    }
    return language_map.get(compact) or language_map.get(first_word) or raw


def _wav_metadata(wav_bytes: bytes) -> dict[str, Any]:
    with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
    return {"sample_rate": sample_rate, "duration": frame_count / sample_rate if sample_rate else 0.0}


def _script_segments(payload: dict[str, Any], text: str) -> list[dict[str, Any]]:
    """The client's parsed segments when sent (the shared grammar), else the script parsed here."""
    raw_segments = payload.get("script_segments")
    segments: list[dict[str, Any]] = []
    if isinstance(raw_segments, list):
        for index, raw in enumerate(raw_segments):
            if not isinstance(raw, dict):
                continue
            segment_text = _text(raw.get("text"))
            if not segment_text:
                continue
            segment: dict[str, Any] = {
                "index": int(raw.get("index") or index),
                "speaker": _text(raw.get("speaker")) or DEFAULT_UNTAGGED_SPEAKER,
                "text": segment_text,
            }
            pause = raw.get("pause_before_ms")
            if isinstance(pause, (int, float)) and not isinstance(pause, bool) and pause >= 0 and segments:
                segment["pause_before_ms"] = int(min(MAX_PAUSE_MS, pause))
            instruction = _text(raw.get("delivery_instruction"))
            if instruction:
                segment["delivery_instruction"] = instruction[:500]
            line_id = _text(raw.get("line_id"))
            if line_id:
                segment["line_id"] = line_id[:100]
            segments.append(segment)
        if segments:
            return segments
    return parse_script(text) or [{"index": 0, "speaker": DEFAULT_UNTAGGED_SPEAKER, "text": text.strip()}]


def _assignments_by_speaker(assignments: list[Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for row in assignments:
        if isinstance(row, dict):
            speaker = _text(row.get("speaker"))
            if speaker:
                mapped[speaker.casefold()] = row
    return mapped


MAX_CLONE_SAMPLE_BYTES = 50 * 1024 * 1024


def asset_audio_url(asset_id: str) -> str:
    return f"/api/assets/{quote(asset_id, safe='')}/audio"


def store_inline_clone_sample(input_payload: dict[str, Any]) -> dict[str, Any]:
    """Move an inline base64 sample into the blob store at job admission.

    The job row then carries only the content-addressed blob key and digest,
    never the audio itself.
    """
    if not input_payload.get("sample_audio_base64"):
        return input_payload
    audio = _decode_audio_payload(input_payload["sample_audio_base64"])
    if not audio:
        raise ValueError("Audio sample is required")
    if len(audio) > MAX_CLONE_SAMPLE_BYTES:
        raise ValueError("Audio sample is too large")
    if not _is_audio_container(audio):
        raise ValueError("Audio sample is not a WAV, MP3, MP4, WebM, Ogg or FLAC file")
    digest = hashlib.sha256(audio).hexdigest()
    suffix = Path(_text(input_payload.get("source_file_name")) or "sample.wav").suffix.lower()
    if suffix not in {".wav", ".mp3", ".mp4", ".m4a", ".webm", ".ogg", ".flac"}:
        suffix = ".wav"
    record = default_blob_store().put_bytes(f"voice-samples/{digest[:2]}/{digest}{suffix}", audio)
    updated = {key: value for key, value in input_payload.items() if key != "sample_audio_base64"}
    updated["sample_blob_key"] = record["storage_key"]
    updated["sample_sha256"] = digest
    return updated


def _is_audio_container(data: bytes) -> bool:
    """A sample's leading bytes name an accepted audio container (ASVS 12.2.1)."""
    head = data[:12]
    return (
        (head[:4] == b"RIFF" and head[8:12] == b"WAVE")
        or head[:4] in {b"OggS", b"fLaC", b"\x1aE\xdf\xa3"}
        or head[:3] == b"ID3"
        or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
        or head[4:8] == b"ftyp"
    )


def _sample_audio_bytes(payload: dict[str, Any]) -> bytes:
    key = _text(payload.get("sample_blob_key"))
    if key:
        return default_blob_store().read_bytes(key, expected_checksum=_text(payload.get("sample_sha256")) or None)
    # Jobs queued before samples moved to the blob store.
    return _decode_audio_payload(payload.get("sample_audio_base64"))


def _decode_audio_payload(value: Any) -> bytes:
    encoded = _require_text(value, "Audio sample is required")
    if "," in encoded and encoded.strip().lower().startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    try:
        return base64.b64decode(encoded, validate=False)
    except Exception as exc:
        raise ValueError("Audio sample could not be decoded") from exc


def _upsert_legacy_voice_manifest(voice_id: str, profile_name: str, payload: dict[str, Any], clone_path: Path) -> None:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        return
    from app.runtime.paths import VOICE_CLONES_FILE

    manifest_path = Path(VOICE_CLONES_FILE)
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
        "ref_text": _text(payload.get("reference_text")),
        "transcript_source": _text(payload.get("transcript_source")),
        "transcript_path": _text(payload.get("transcript_path")),
        "stt_provider": _text(payload.get("stt_provider_id")),
    }
    manifest_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _voice_clone_dir() -> Path:
    from app.runtime.paths import VOICE_CLONES_DIR

    return Path(VOICE_CLONES_DIR)


def _upsert_asset(asset: AssetRecord) -> AssetRecord:
    return default_asset_store().upsert_asset(asset)


def _asset_output_ref(asset: AssetRecord, *, title: str) -> dict[str, Any]:
    return {
        "type": asset.type.value if hasattr(asset.type, "value") else str(asset.type),
        "asset_id": asset.id,
        "title": title,
        "mime_type": asset.mime_type,
    }


def _first_assignment_voice(assignments: list[Any]) -> str:
    for row in assignments:
        if isinstance(row, dict):
            value = _text(row.get("voice_id"))
            if value:
                return value
    return ""


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
