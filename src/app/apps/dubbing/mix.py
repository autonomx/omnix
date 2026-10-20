"""Mixing dubbed lines over the original background (Voice Studio Phase 6).

Each fitted take starts where its source line started. The background stem is
ducked while dubbed speech plays (with short attack and release ramps, so the
music does not pump), and the result is levelled to ``TARGET_LUFS``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DUCK_DB = -9.0
DUCK_ATTACK_SECONDS = 0.08
DUCK_RELEASE_SECONDS = 0.35
TARGET_LUFS = -16.0


@dataclass(frozen=True)
class PlacedTake:
    start_seconds: float
    samples: np.ndarray  # mono float at the mix rate


def _envelope(active: np.ndarray, rate: int) -> np.ndarray:
    """A 0..1 ducking envelope from a boolean speech mask, ramped in and out."""
    attack = max(1, int(DUCK_ATTACK_SECONDS * rate))
    release = max(1, int(DUCK_RELEASE_SECONDS * rate))
    envelope = np.zeros(len(active), dtype=np.float32)
    level = 0.0
    up, down = 1.0 / attack, 1.0 / release
    # A sample-level loop is too slow in Python; work on 10 ms blocks instead.
    block = max(1, rate // 100)
    for start in range(0, len(active), block):
        target = 1.0 if active[start:start + block].any() else 0.0
        step = up * block if target > level else down * block
        level = min(target, level + step) if target > level else max(target, level - step)
        envelope[start:start + block] = level
    return envelope


def mix_dub(takes: list[PlacedTake], background: np.ndarray, rate: int) -> np.ndarray:
    """The dubbed mix: the takes on the timeline over the ducked background, levelled."""
    from app.platform.voice.contracts import integrated_loudness, normalize_loudness

    length = max([len(background)] + [int(take.start_seconds * rate) + len(take.samples) for take in takes])
    voice = np.zeros(length, dtype=np.float32)
    for take in takes:
        start = max(0, int(round(take.start_seconds * rate)))
        voice[start:start + len(take.samples)] += take.samples.astype(np.float32)
    bed = np.zeros(length, dtype=np.float32)
    bed[: len(background)] = background.astype(np.float32)
    duck = 10 ** (DUCK_DB / 20)
    gain = 1.0 - (1.0 - duck) * _envelope(np.abs(voice) > 1e-4, rate)
    mixed = voice + bed * gain
    if np.max(np.abs(mixed)) == 0 or not np.isfinite(integrated_loudness(mixed, rate)):
        return mixed
    levelled, _gain, _measured = normalize_loudness(mixed, rate, TARGET_LUFS)
    return np.asarray(levelled, dtype=np.float32)
