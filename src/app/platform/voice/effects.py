"""Voice Studio's audio effects: one chain, applied once to the assembled speech.

Processing order (shared by render and restitch):
raw segment audio -> speed and pitch per segment -> assembly with pauses ->
EQ, de-esser, compressor, reverb (here, on the whole take) -> volume and a peak
limiter -> watermark -> stored WAV. Effects run after assembly so reverb tails
and compression are consistent across lines; speed and pitch stay per segment
so tails and pauses are not time-stretched.

Effects are stable ids. Older jobs and settings saved display labels
("Equalizer", "De-esser" ...) while effects did nothing; those labels count as
off, so turning effects on never silently changes an existing render (podcast
jobs, saved Voice Studio settings). Noise reduction is not a TTS effect any
more (clean synthetic speech gains nothing from it); recorded samples get
cleaned when a voice is cloned instead.
"""
from __future__ import annotations

import io
import wave
from typing import Any, Iterable

import numpy as np

EFFECT_IDS = ("eq", "deesser", "compressor", "reverb")
EFFECT_LABELS = {"eq": "Equalizer", "deesser": "De-esser", "compressor": "Compression", "reverb": "Reverb"}
# The order the chain always applies effects in, whatever order they were picked.
_CHAIN_ORDER = {effect: index for index, effect in enumerate(EFFECT_IDS)}

_LIMITER_CEILING_DBFS = -1.0


def effect_ids(values: Iterable[Any] | None) -> list[str]:
    """Stable effect ids, in chain order; anything else (old display labels) is off."""
    found = {str(value or "").strip() for value in values or ()}
    return sorted(found.intersection(EFFECT_IDS), key=_CHAIN_ORDER.__getitem__)


def read_mono(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """PCM WAV as mono float64 samples in [-1, 1] and its sample rate."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
        frames = source.readframes(source.getnframes())
    if width == 2:
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    elif width == 4:
        samples = np.frombuffer(frames, dtype="<i4").astype(np.float64) / 2147483648.0
    elif width == 1:
        samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        values = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
        values = np.where(values >= 1 << 23, values - (1 << 24), values)
        samples = values.astype(np.float64) / float(1 << 23)
    else:
        raise ValueError(f"unsupported WAV sample width: {width} bytes")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def write_mono(samples: np.ndarray, rate: int) -> bytes:
    """Mono 16-bit PCM WAV."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def to_mono_pcm16(wav_bytes: bytes) -> bytes:
    """The same audio as mono 16-bit PCM (assembly needs one format)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        if source.getnchannels() == 1 and source.getsampwidth() == 2 and source.getcomptype() == "NONE":
            return wav_bytes
    samples, rate = read_mono(wav_bytes)
    return write_mono(samples, rate)


def _fft_filter(samples: np.ndarray, rate: int, gain_for: Any) -> np.ndarray:
    """Zero-phase filtering by a magnitude curve ``gain_for(freqs)``, padded against wrap-around."""
    pad = min(len(samples), rate // 2)
    padded = np.concatenate([np.zeros(pad), samples, np.zeros(pad)])
    spectrum = np.fft.rfft(padded)
    freqs = np.fft.rfftfreq(len(padded), 1.0 / rate)
    filtered = np.fft.irfft(spectrum * gain_for(freqs), len(padded))
    return filtered[pad: pad + len(samples)]


def equalize(samples: np.ndarray, rate: int) -> np.ndarray:
    """Low cut below 80 Hz (2nd-order) and a +3 dB presence shelf from about 3 kHz."""
    def gain(freqs: np.ndarray) -> np.ndarray:
        ratio = np.divide(freqs, 80.0, out=np.zeros_like(freqs), where=freqs > 0)
        low_cut = ratio ** 2 / np.sqrt(1.0 + ratio ** 4)
        shelf_db = 3.0 / (1.0 + np.exp(-(np.log2(np.maximum(freqs, 1.0)) - np.log2(3000.0)) * 4.0))
        return low_cut * 10 ** (shelf_db / 20)
    return _fft_filter(samples, rate, gain)


def _frame_envelope(samples: np.ndarray, frame: int) -> np.ndarray:
    """RMS per frame, as one value per frame."""
    count = max(1, int(np.ceil(len(samples) / frame)))
    padded = np.zeros(count * frame)
    padded[: len(samples)] = samples
    return np.sqrt(np.mean(padded.reshape(count, frame) ** 2, axis=1) + 1e-12)


def _smooth(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1 or len(values) < 2:
        return values
    kernel = np.ones(width) / width
    return np.convolve(np.pad(values, (width // 2, width - 1 - width // 2), mode="edge"), kernel, mode="valid")


def _gain_curve(envelope: np.ndarray, threshold_db: float, ratio: float) -> np.ndarray:
    level_db = 20 * np.log10(envelope)
    over = np.maximum(0.0, level_db - threshold_db)
    return 10 ** (-(over * (1.0 - 1.0 / ratio)) / 20)


def _per_sample(frame_gains: np.ndarray, frame: int, length: int) -> np.ndarray:
    centers = (np.arange(len(frame_gains)) + 0.5) * frame
    return np.interp(np.arange(length), centers, frame_gains)


def deess(samples: np.ndarray, rate: int, *, threshold_db: float = -32.0, ratio: float = 4.0) -> np.ndarray:
    """Compress only the 5-9 kHz sibilance band when it gets loud."""
    if rate < 18_000:  # The band is above Nyquist; nothing to do.
        return samples
    in_band = lambda freqs: ((freqs >= 5000.0) & (freqs <= 9000.0)).astype(float)  # noqa: E731
    band = _fft_filter(samples, rate, in_band)
    rest = samples - band
    frame = max(1, int(rate * 0.005))
    gains = _smooth(_gain_curve(_frame_envelope(band, frame), threshold_db, ratio), 3)
    return rest + band * _per_sample(gains, frame, len(samples))


def compress(samples: np.ndarray, rate: int, *, threshold_db: float = -20.0, ratio: float = 3.0) -> np.ndarray:
    """RMS compressor with makeup gain that restores the original level (at most +6 dB)."""
    frame = max(1, int(rate * 0.01))
    envelope = _frame_envelope(samples, frame)
    gains = _smooth(_gain_curve(envelope, threshold_db, ratio), 5)  # ~50 ms attack/release
    compressed = samples * _per_sample(gains, frame, len(samples))
    before = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0.0
    after = float(np.sqrt(np.mean(compressed ** 2))) if len(samples) else 0.0
    if before > 0 and after > 0:
        compressed = compressed * min(10 ** (6 / 20), before / after)
    return compressed


def reverb(samples: np.ndarray, rate: int, *, decay_seconds: float = 0.45, wet: float = 0.18) -> np.ndarray:
    """A short room: exponentially decaying noise impulse, mixed in; the tail extends the take."""
    length = max(1, int(rate * decay_seconds))
    time = np.arange(length) / rate
    impulse = np.random.default_rng(20261019).standard_normal(length) * np.exp(-6.9 * time / decay_seconds)
    impulse[: int(rate * 0.012)] = 0.0  # pre-delay
    impulse /= np.sqrt(np.sum(impulse ** 2)) or 1.0
    size = len(samples) + length - 1
    fft_size = 1 << (size - 1).bit_length()
    tail = np.fft.irfft(np.fft.rfft(samples, fft_size) * np.fft.rfft(impulse, fft_size), fft_size)[:size]
    dry = np.concatenate([samples, np.zeros(length - 1)])
    return (1.0 - wet) * dry + wet * tail


_EFFECTS = {"eq": equalize, "deesser": deess, "compressor": compress, "reverb": reverb}


def apply_effects(samples: np.ndarray, rate: int, effects: Iterable[Any]) -> np.ndarray:
    for effect in effect_ids(effects):
        samples = _EFFECTS[effect](samples, rate)
    return samples


def peak_limit(samples: np.ndarray, rate: int, *, ceiling_dbfs: float = _LIMITER_CEILING_DBFS,
               release_ms: float = 60.0) -> np.ndarray:
    """A peak limiter: only the moments above the ceiling are turned down, the rest keeps its level.

    The gain needed per 1 ms frame is spread over the release window on both
    sides (a look-ahead and a hold), lightly smoothed, and interpolated per
    sample; a final clip catches any interpolation overshoot.
    """
    if not samples.size:
        return samples
    ceiling = 10 ** (ceiling_dbfs / 20)
    peak = float(np.max(np.abs(samples)))
    if peak <= ceiling:
        return samples
    frame = max(1, int(rate * 0.001))
    count = int(np.ceil(len(samples) / frame))
    padded = np.zeros(count * frame)
    padded[: len(samples)] = np.abs(samples)
    frame_peaks = padded.reshape(count, frame).max(axis=1)
    needed = np.minimum(1.0, ceiling / np.maximum(frame_peaks, 1e-12))
    reach = max(1, int(release_ms / 1000 * rate / frame))
    if count > 1:
        windows = np.lib.stride_tricks.sliding_window_view(np.pad(needed, reach, mode="edge"), 2 * reach + 1)
        spread = windows.min(axis=1)
    else:
        spread = needed
    smoothed = np.minimum(_smooth(spread, 5), spread)
    gains = _per_sample(smoothed, frame, len(samples))
    return np.clip(samples * gains, -ceiling, ceiling)


def limit(samples: np.ndarray, *, ceiling_dbfs: float = _LIMITER_CEILING_DBFS, rate: int = 24_000) -> np.ndarray:
    """Never clip: peaks above the ceiling are limited, the rest of the take keeps its level."""
    return peak_limit(samples, rate, ceiling_dbfs=ceiling_dbfs)


def master_take(wav_bytes: bytes, effects: Iterable[Any], *, volume_db: float = 0.0) -> tuple[bytes, list[str]]:
    """Effects, then volume and the limiter, on an assembled take; returns the WAV and the effects applied."""
    applied = effect_ids(effects)
    if not applied and not volume_db:
        return wav_bytes, []
    samples, rate = read_mono(wav_bytes)
    samples = apply_effects(samples, rate, applied)
    if volume_db:
        samples = samples * 10 ** (volume_db / 20)
    return write_mono(limit(samples, rate=rate), rate), applied


__all__ = [
    "EFFECT_IDS",
    "EFFECT_LABELS",
    "apply_effects",
    "compress",
    "deess",
    "effect_ids",
    "equalize",
    "limit",
    "master_take",
    "read_mono",
    "reverb",
    "to_mono_pcm16",
    "write_mono",
]
