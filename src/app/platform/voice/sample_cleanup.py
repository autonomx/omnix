"""Clean and check a voice sample before it is cloned.

Trims leading and trailing silence, normalizes loudness, and reports clipping
and an estimated signal-to-noise ratio. The clone form's Quality choice sets how
strict the check is: below its SNR floor the clone still saves, with a warning
that the voice may carry the room noise.

Only formats libsndfile reads (WAV, FLAC, Ogg, MP3) are cleaned. Browser
recordings (WebM) and M4A pass through unchanged and are reported as unchecked.
"""
from __future__ import annotations

import io
import logging
import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from .effects import write_mono

logger = logging.getLogger(__name__)
from .loudness import integrated_loudness, normalize_loudness

SAMPLE_TARGET_LUFS = -20.0
_SILENCE_DBFS = -45.0
_MARGIN_SECONDS = 0.1
_CLIP_LEVEL = 0.999
_CLIP_WARN_FRACTION = 0.001
_STRICTNESS_SNR_DB = {"high": 20.0, "standard": 15.0, "draft": 10.0}


@dataclass
class SampleReport:
    checked: bool
    strictness: str = "standard"
    duration_seconds: float = 0.0
    trimmed_seconds: float = 0.0
    loudness_lufs: float | None = None
    clipped_fraction: float = 0.0
    snr_db: float | None = None
    warnings: list[str] = field(default_factory=list)

    def as_metadata(self) -> dict[str, Any]:
        return asdict(self)


def strictness_for(quality: str) -> str:
    """The clone form's Quality label as a check strictness."""
    label = str(quality or "").casefold()
    if any(word in label for word in ("high", "studio", "recommended")):
        return "high"
    if any(word in label for word in ("draft", "fast", "preview")):
        return "draft"
    return "standard"


def _decode(audio: bytes) -> tuple[np.ndarray, int] | None:
    import soundfile as sf

    try:
        samples, rate = sf.read(io.BytesIO(audio), dtype="float64", always_2d=True)
    except Exception:
        # Formats soundfile cannot read are cloned as uploaded, unchecked.
        logger.info("Clone sample could not be decoded for checking", exc_info=True)
        return None
    return samples.mean(axis=1), int(rate)


def _frame_levels(samples: np.ndarray, rate: int) -> tuple[np.ndarray, int]:
    frame = max(1, int(rate * 0.02))
    count = max(1, len(samples) // frame)
    frames = samples[: count * frame].reshape(count, frame)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms), frame


def estimate_snr(samples: np.ndarray, rate: int) -> float | None:
    """Speech level (90th percentile frame) over the noise floor (10th percentile), in dB."""
    levels, _frame = _frame_levels(samples, rate)
    if len(levels) < 10:
        return None
    return float(np.percentile(levels, 90) - np.percentile(levels, 10))


def trim_silence(samples: np.ndarray, rate: int) -> np.ndarray:
    """Drop leading and trailing frames near the noise floor (keeping a 100 ms margin)."""
    levels, frame = _frame_levels(samples, rate)
    # Relative to this recording: just above its noise floor, below its speech.
    floor = float(np.percentile(levels, 10)) if len(levels) else _SILENCE_DBFS
    speech = float(np.percentile(levels, 90)) if len(levels) else 0.0
    threshold = max(_SILENCE_DBFS, min(floor + 6.0, speech - 6.0))
    voiced = np.flatnonzero(levels > threshold)
    if not len(voiced):
        return samples
    margin = int(rate * _MARGIN_SECONDS)
    start = max(0, voiced[0] * frame - margin)
    end = min(len(samples), (voiced[-1] + 1) * frame + margin)
    return samples[start:end]


def clean_sample(audio: bytes, *, quality: str = "") -> tuple[bytes, str | None, SampleReport]:
    """The cleaned sample (WAV), its new suffix, and the report.

    An undecodable sample comes back unchanged with ``None`` as the suffix.
    """
    strictness = strictness_for(quality)
    decoded = _decode(audio)
    if decoded is None:
        return audio, None, SampleReport(checked=False, strictness=strictness,
                                         warnings=["This recording format could not be checked or cleaned."])
    samples, rate = decoded
    report = SampleReport(checked=True, strictness=strictness, duration_seconds=len(samples) / rate if rate else 0.0)
    report.clipped_fraction = float(np.mean(np.abs(samples) >= _CLIP_LEVEL)) if len(samples) else 0.0
    report.snr_db = estimate_snr(samples, rate)
    trimmed = trim_silence(samples, rate)
    report.trimmed_seconds = round((len(samples) - len(trimmed)) / rate, 3) if rate else 0.0
    loudness = integrated_loudness(trimmed, rate)
    if math.isfinite(loudness):
        trimmed, _measured, final = normalize_loudness(trimmed, rate, SAMPLE_TARGET_LUFS)
        report.loudness_lufs = round(final, 2)
    if report.clipped_fraction > _CLIP_WARN_FRACTION:
        report.warnings.append("The recording clips; record a little quieter for a cleaner voice.")
    floor = _STRICTNESS_SNR_DB[strictness]
    if report.snr_db is not None and report.snr_db < floor:
        report.warnings.append(
            f"Background noise is high (about {report.snr_db:.0f} dB below the voice; "
            f"{strictness} quality expects {floor:.0f} dB). The cloned voice may carry the room noise."
        )
    duration = len(trimmed) / rate if rate else 0.0
    if duration < 5.0:
        report.warnings.append("The sample is shorter than 5 seconds; 10 to 30 seconds clones best.")
    return write_mono(trimmed, rate), ".wav", report


__all__ = ["SampleReport", "clean_sample", "estimate_snr", "strictness_for", "trim_silence"]
