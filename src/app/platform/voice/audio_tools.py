"""Audio Tools jobs (Voice Studio Phase 4): isolate vocals, enhance speech, check watermarks.

Each job works on a stored audio asset (never a server path) through the audio
service, and stores what it makes as assets whose parent is the source, so a
stem or a cleaned recording always says where it came from.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audio_service import AudioServiceClient, AudioToolRequestError

_MAX_SOURCE_BYTES = 500 * 1024 * 1024
SEPARATION_MODELS = ("roformer", "demucs")


def _source(job: Any) -> Any:
    from app.assets import AssetType, default_asset_store

    payload = job.input_payload or {}
    if payload.get("source_path"):
        raise AudioToolRequestError("Audio tools take a stored audio asset, not a server path")
    asset_id = str((job.input_ref or {}).get("asset_id") or payload.get("asset_id") or "").strip()
    if not asset_id:
        raise AudioToolRequestError("Choose an audio asset")
    asset = default_asset_store().get_asset(asset_id)
    if asset is None:
        raise AudioToolRequestError(f"Audio asset {asset_id} was not found")
    audio_types = {AssetType.AUDIO, AssetType.VOICE_SAMPLE, AssetType.VOICE_PROFILE, AssetType.VOICE_TAKE,
                   AssetType.CHAPTER_AUDIO, AssetType.RENDER, AssetType.EXPORT}
    if asset.type not in audio_types or not str(asset.mime_type or "").startswith("audio/"):
        raise AudioToolRequestError(f"{asset_id} is not audio")
    return asset


def _read(asset: Any) -> tuple[bytes, str]:
    from app.assets.content import read_asset_bytes

    name = Path(asset.storage_path or asset.metadata.get("file_name") or "audio.wav").name
    try:
        return read_asset_bytes(asset, max_bytes=_MAX_SOURCE_BYTES), name
    except ValueError as exc:
        raise AudioToolRequestError(str(exc)) from exc


def _store(job: Any, job_store: Any, source: Any, *, suffix: str, wav: bytes, kind: str, title: str,
           extra: dict[str, Any]) -> Any:
    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.jobs.inline_execution import require_execution_authority
    from app.runtime.paths import resources_data_root

    output_dir = resources_data_root() / "voice_studio" / "audio_tools"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in job.id)
    path = output_dir / f"{safe}-{suffix}.wav"
    require_execution_authority(job_store, job.id)
    path.write_bytes(wav)
    return default_asset_store().upsert_asset(AssetRecord(
        id=f"audio:{safe}-{suffix}",
        module="voice",
        type=AssetType.AUDIO,
        mime_type="audio/wav",
        storage_path=str(path),
        metadata={"title": title, "kind": kind, **extra},
        source_job_id=job.id,
        parent_asset_ids=[source.id],
        created_at=datetime.now(timezone.utc).isoformat(),
        compat={"contract": "voice_studio_audio_tool_v1"},
    ))


def _ref(asset: Any) -> dict[str, Any]:
    return {"type": "audio", "kind": asset.metadata.get("kind"), "asset_id": asset.id,
            "title": asset.metadata.get("title"), "audio_url": f"/api/assets/{asset.id}/audio",
            "mime_type": asset.mime_type, "parent_asset_id": (asset.parent_asset_ids or [""])[0]}


def _title(asset: Any) -> str:
    return str(asset.metadata.get("title") or asset.metadata.get("profile_name") or asset.id)


def execute_isolate_job(job: Any, *, job_store: Any = None, client: Any = None) -> dict[str, Any]:
    """Split a recording into a vocal stem and a background stem."""
    payload = job.input_payload or {}
    model = str(payload.get("model") or "roformer").strip().lower()
    if model not in SEPARATION_MODELS:
        raise AudioToolRequestError(f"model must be one of {', '.join(SEPARATION_MODELS)}")
    source = _source(job)
    audio, name = _read(source)
    stems = (client or AudioServiceClient()).isolate(audio, name, model=model)
    extra = {"model": stems.model, "sample_rate": stems.sample_rate}
    vocals = _store(job, job_store, source, suffix="vocals", wav=stems.vocals, kind="stem_vocals",
                    title=f"{_title(source)} (vocals)", extra=extra)
    background = _store(job, job_store, source, suffix="background", wav=stems.background, kind="stem_background",
                        title=f"{_title(source)} (background)", extra=extra)
    return {"content": f"Separated {_title(source)} with {stems.model}", "log_message": "Vocals isolated",
            "output_refs": [_ref(vocals), _ref(background)]}


def execute_enhance_job(job: Any, *, job_store: Any = None, client: Any = None) -> dict[str, Any]:
    """Denoise a recorded voice (recordings, not TTS output)."""
    source = _source(job)
    audio, name = _read(source)
    enhanced, details = (client or AudioServiceClient()).enhance(audio, name)
    asset = _store(job, job_store, source, suffix="enhanced", wav=enhanced, kind="enhanced",
                   title=f"{_title(source)} (enhanced)", extra={"enhancer": details.get("model", "")})
    return {"content": f"Enhanced {_title(source)}", "log_message": "Speech enhanced", "output_refs": [_ref(asset)]}


def execute_detect_job(job: Any, *, job_store: Any = None, client: Any = None) -> dict[str, Any]:
    """Check a file for an AudioSeal watermark; reports whether this workspace's message is in it."""
    from .watermarking import workspace_message

    source = _source(job)
    audio, name = _read(source)
    result = (client or AudioServiceClient()).detect(audio, name)
    detected = bool(result.get("detected"))
    message = result.get("message")
    ours = detected and message is not None and int(message) == workspace_message()
    verdict = ("Watermarked by this workspace" if ours else "Watermarked" if detected else "No watermark found")
    return {
        "content": verdict,
        "log_message": f"Watermark check: {verdict.lower()} (probability {float(result.get('probability') or 0):.2f})",
        "output_refs": [{"type": "watermark_check", "title": verdict, "asset_id": source.id, "detected": detected,
                         "probability": result.get("probability"), "message": message, "this_workspace": ours}],
    }


__all__ = ["SEPARATION_MODELS", "execute_detect_job", "execute_enhance_job", "execute_isolate_job"]
