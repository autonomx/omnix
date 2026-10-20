"""``voice.export``: a stored WAV take as WAV, FLAC, MP3 or Opus, optionally loudness-normalized.

Takes stay lossless WAV; an export is a new ``export`` asset whose parent is the
take. Encoding is libsndfile through ``soundfile`` (MP3 as VBR), so no ffmpeg is
needed. Opus only runs at 8, 12, 16, 24 or 48 kHz; other rates are refused here
and the UI offers only valid ones.
"""
from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .effects import read_mono
from .loudness import LOUDNESS_PRESETS, integrated_loudness, normalize_loudness

EXPORT_FORMATS: dict[str, dict[str, str]] = {
    "wav16": {"format": "WAV", "subtype": "PCM_16", "extension": ".wav", "mime": "audio/wav"},
    "wav24": {"format": "WAV", "subtype": "PCM_24", "extension": ".wav", "mime": "audio/wav"},
    "flac": {"format": "FLAC", "subtype": "PCM_24", "extension": ".flac", "mime": "audio/flac"},
    "mp3": {"format": "MP3", "subtype": "MPEG_LAYER_III", "extension": ".mp3", "mime": "audio/mpeg"},
    "opus": {"format": "OGG", "subtype": "OPUS", "extension": ".opus", "mime": "audio/ogg"},
}
SAMPLE_RATES = (16_000, 22_050, 24_000, 44_100, 48_000)
OPUS_SAMPLE_RATES = (8_000, 12_000, 16_000, 24_000, 48_000)
DEFAULT_OPUS_RATE = 48_000


class ExportRequestError(ValueError):
    """The export request itself is invalid; retrying cannot help."""


def export_options(fmt: str) -> list[int]:
    """The sample rates the UI may offer for ``fmt``."""
    return list(OPUS_SAMPLE_RATES if fmt == "opus" else SAMPLE_RATES)


def resample(samples: np.ndarray, rate: int, target: int) -> np.ndarray:
    """Band-limited resampling (FFT method)."""
    if rate == target or not len(samples):
        return samples
    length = max(1, int(round(len(samples) * target / rate)))
    spectrum = np.fft.rfft(samples)
    resized = np.zeros(length // 2 + 1, dtype=complex)
    keep = min(len(spectrum), len(resized))
    resized[:keep] = spectrum[:keep]
    return np.fft.irfft(resized, length) * (length / len(samples))


def encode(samples: np.ndarray, rate: int, fmt: str) -> bytes:
    import soundfile as sf

    spec = EXPORT_FORMATS[fmt]
    buffer = io.BytesIO()
    options: dict[str, Any] = {}
    if fmt == "mp3":
        options["bitrate_mode"] = "VARIABLE"
        options["compression_level"] = 0.4  # about LAME V2-V3
    sf.write(buffer, np.clip(samples, -1.0, 1.0).astype(np.float32), rate,
             format=spec["format"], subtype=spec["subtype"], **options)
    return buffer.getvalue()


def render_export(
    wav_bytes: bytes, *, fmt: str, sample_rate: int | None = None, loudness: str = "none",
) -> tuple[bytes, dict[str, Any]]:
    """The encoded file and what was done to it."""
    if fmt not in EXPORT_FORMATS:
        raise ExportRequestError(f"unknown export format: {fmt}")
    if loudness not in LOUDNESS_PRESETS:
        raise ExportRequestError(f"unknown loudness preset: {loudness}")
    samples, source_rate = read_mono(wav_bytes)
    target_rate = int(sample_rate or (DEFAULT_OPUS_RATE if fmt == "opus" else source_rate))
    allowed = OPUS_SAMPLE_RATES if fmt == "opus" else (*SAMPLE_RATES, source_rate)
    if target_rate not in allowed:
        raise ExportRequestError(f"{fmt} cannot be exported at {target_rate} Hz")
    samples = resample(samples, source_rate, target_rate)
    details: dict[str, Any] = {"format": fmt, "sample_rate": target_rate, "source_sample_rate": source_rate}
    target_lufs = LOUDNESS_PRESETS[loudness]
    if target_lufs is not None:
        samples, measured, final = normalize_loudness(samples, target_rate, target_lufs)
        details.update(loudness_preset=loudness, target_lufs=target_lufs,
                       measured_lufs=_round(measured), output_lufs=_round(final))
    else:
        details["output_lufs"] = _round(integrated_loudness(samples, target_rate))
    details["duration"] = len(samples) / target_rate if target_rate else 0.0
    return encode(samples, target_rate, fmt), details


def _round(value: float) -> float | None:
    return round(value, 2) if math.isfinite(value) else None


def execute_export_job(job: Any, *, job_store: Any = None) -> dict[str, Any]:
    """Run ``voice.export``: read the source asset, encode, store an ``export`` asset."""
    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.assets.content import read_asset_bytes
    from app.jobs.inline_execution import require_execution_authority
    from app.runtime.paths import resources_data_root

    payload = job.input_payload or {}
    source_id = str(payload.get("asset_id") or (job.input_ref or {}).get("asset_id") or "").strip()
    if not source_id:
        raise ExportRequestError("asset_id is required")
    store = default_asset_store()
    source = store.get_asset(source_id)
    if source is None or source.type not in {AssetType.AUDIO, AssetType.CHAPTER_AUDIO, AssetType.RENDER}:
        raise ExportRequestError(f"{source_id} is not a stored audio take")
    from .watermarking import is_render, watermark_enabled

    if watermark_enabled() and is_render(source) and not source.metadata.get("watermark"):
        raise ExportRequestError("Watermarking is on and this render was made before it was; render it again to export it")
    fmt = str(payload.get("format") or "wav16").strip().lower()
    loudness = str(payload.get("loudness") or "none").strip().lower()
    rate_value = payload.get("sample_rate")
    sample_rate = int(rate_value) if rate_value not in (None, "") else None
    encoded, details = render_export(read_asset_bytes(source), fmt=fmt, sample_rate=sample_rate, loudness=loudness)

    spec = EXPORT_FORMATS[fmt]
    output_dir = resources_data_root() / "voice_studio" / "exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_source = "".join(char if char.isalnum() or char in "-_." else "-" for char in source_id).strip("-.")
    output_path = output_dir / f"{safe_source}-{fmt}-{details['sample_rate']}-{loudness}{spec['extension']}"
    require_execution_authority(job_store, job.id)
    output_path.write_bytes(encoded)
    title = str(source.metadata.get("title") or source_id)
    require_execution_authority(job_store, job.id)
    asset = store.upsert_asset(AssetRecord(
        id=f"export:{safe_source}-{fmt}-{details['sample_rate']}-{loudness}",
        module="voice",
        type=AssetType.EXPORT,
        mime_type=spec["mime"],
        storage_path=str(output_path),
        metadata={"title": f"{title} ({fmt.upper()})", **details,
                  **({"watermark": source.metadata["watermark"]} if source.metadata.get("watermark") else {})},
        source_job_id=job.id,
        parent_asset_ids=[source_id],
        created_at=datetime.now(timezone.utc).isoformat(),
        compat={"contract": "voice_studio_export_v1"},
    ))
    return {
        "content": f"Exported {title} as {fmt} at {details['sample_rate']} Hz to {Path(output_path).name}",
        "log_message": "Voice Studio export written",
        "output_refs": [{
            "type": "export", "asset_id": asset.id, "title": asset.metadata["title"],
            "mime_type": asset.mime_type, "parent_asset_id": source_id, **details,
        }],
    }


__all__ = [
    "EXPORT_FORMATS",
    "ExportRequestError",
    "OPUS_SAMPLE_RATES",
    "SAMPLE_RATES",
    "encode",
    "execute_export_job",
    "export_options",
    "render_export",
    "resample",
]
