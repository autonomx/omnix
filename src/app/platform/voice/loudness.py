"""Integrated loudness (ITU-R BS.1770-4) and loudness-normalized export, in numpy.

The worker environment has no scipy, so the K-weighting filter is applied as a
magnitude response per 400 ms gating block (Parseval) rather than as an IIR
recursion. The biquads are the standard BS.1770 pair, re-derived for the
signal's sample rate. Block energy from a circular filter differs from the
recursive one by well under 0.1 dB for speech-length blocks.
"""
from __future__ import annotations

import math

import numpy as np

PODCAST_LUFS = -16.0
BROADCAST_LUFS = -23.0
LOUDNESS_PRESETS = {"none": None, "podcast": PODCAST_LUFS, "broadcast": BROADCAST_LUFS}

_BLOCK_SECONDS = 0.4
_OVERLAP = 0.75
_ABSOLUTE_GATE_LUFS = -70.0
_RELATIVE_GATE_LU = -10.0
_TRUE_PEAK_CEILING_DBFS = -1.0


def _biquad_response(b: tuple[float, float, float], a: tuple[float, float, float], freqs: np.ndarray, rate: int) -> np.ndarray:
    z = np.exp(-1j * 2 * np.pi * freqs / rate)
    numerator = b[0] + b[1] * z + b[2] * z * z
    denominator = a[0] + a[1] * z + a[2] * z * z
    return np.abs(numerator / denominator) ** 2


def _k_weighting_power(freqs: np.ndarray, rate: int) -> np.ndarray:
    """|H(f)|^2 of the BS.1770 pre-filter (high shelf) and RLB high-pass."""
    # Stage 1: +4 dB high shelf at 1500 Hz.
    gain_db, q, fc = 4.0, 1 / math.sqrt(2), 1500.0
    amp = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * fc / rate
    alpha = math.sin(w0) / (2 * q)
    cos = math.cos(w0)
    shelf_b = (
        amp * ((amp + 1) + (amp - 1) * cos + 2 * math.sqrt(amp) * alpha),
        -2 * amp * ((amp - 1) + (amp + 1) * cos),
        amp * ((amp + 1) + (amp - 1) * cos - 2 * math.sqrt(amp) * alpha),
    )
    shelf_a = (
        (amp + 1) - (amp - 1) * cos + 2 * math.sqrt(amp) * alpha,
        2 * ((amp - 1) - (amp + 1) * cos),
        (amp + 1) - (amp - 1) * cos - 2 * math.sqrt(amp) * alpha,
    )
    # Stage 2: high-pass at 38 Hz, Q 0.5.
    q, fc = 0.5, 38.0
    w0 = 2 * math.pi * fc / rate
    alpha = math.sin(w0) / (2 * q)
    cos = math.cos(w0)
    pass_b = ((1 + cos) / 2, -(1 + cos), (1 + cos) / 2)
    pass_a = (1 + alpha, -2 * cos, 1 - alpha)
    return _biquad_response(shelf_b, shelf_a, freqs, rate) * _biquad_response(pass_b, pass_a, freqs, rate)


def _block_mean_squares(samples: np.ndarray, rate: int) -> np.ndarray:
    block = max(1, int(round(rate * _BLOCK_SECONDS)))
    step = max(1, int(round(block * (1 - _OVERLAP))))
    if len(samples) < block:
        samples = np.concatenate([samples, np.zeros(block - len(samples))])
    starts = np.arange(0, len(samples) - block + 1, step)
    power = _k_weighting_power(np.fft.rfftfreq(block, 1.0 / rate), rate)
    weights = np.full(power.shape, 2.0)
    weights[0] = 1.0
    if block % 2 == 0:
        weights[-1] = 1.0
    result = np.empty(len(starts))
    for offset in range(0, len(starts), 512):  # bounded memory for long takes
        chunk = starts[offset: offset + 512]
        frames = np.stack([samples[start: start + block] for start in chunk])
        spectra = np.abs(np.fft.rfft(frames, axis=1)) ** 2
        result[offset: offset + len(chunk)] = (spectra * power * weights).sum(axis=1) / (block * block)
    return result


def integrated_loudness(samples: np.ndarray, rate: int) -> float:
    """Gated integrated loudness of mono audio in LUFS; ``-inf`` for silence."""
    if not len(samples) or rate <= 0:
        return float("-inf")
    mean_squares = _block_mean_squares(np.asarray(samples, dtype=np.float64), rate)
    with np.errstate(divide="ignore"):
        loudness = -0.691 + 10 * np.log10(mean_squares)
    gated = mean_squares[loudness > _ABSOLUTE_GATE_LUFS]
    if not len(gated):
        return float("-inf")
    relative_gate = -0.691 + 10 * math.log10(float(np.mean(gated))) + _RELATIVE_GATE_LU
    with np.errstate(divide="ignore"):
        kept = gated[(-0.691 + 10 * np.log10(gated)) > relative_gate]
    if not len(kept):
        return float("-inf")
    return -0.691 + 10 * math.log10(float(np.mean(kept)))


def normalize_loudness(samples: np.ndarray, rate: int, target_lufs: float) -> tuple[np.ndarray, float, float]:
    """Gain to ``target_lufs`` with peaks limited to -1 dBFS; returns samples, measured and final loudness.

    Limiting the peaks takes a little loudness back, so the gain is corrected
    once after the first pass; the result lands within a few tenths of a LU.
    """
    from .effects import peak_limit

    measured = integrated_loudness(samples, rate)
    if not math.isfinite(measured):
        return samples, measured, measured
    gain = 10 ** ((target_lufs - measured) / 20)
    adjusted = peak_limit(samples * gain, rate, ceiling_dbfs=_TRUE_PEAK_CEILING_DBFS)
    first = integrated_loudness(adjusted, rate)
    if math.isfinite(first) and abs(target_lufs - first) > 0.1:
        gain *= 10 ** ((target_lufs - first) / 20)
        adjusted = peak_limit(samples * gain, rate, ceiling_dbfs=_TRUE_PEAK_CEILING_DBFS)
    return adjusted, measured, integrated_loudness(adjusted, rate)


__all__ = [
    "BROADCAST_LUFS",
    "LOUDNESS_PRESETS",
    "PODCAST_LUFS",
    "integrated_loudness",
    "normalize_loudness",
]
