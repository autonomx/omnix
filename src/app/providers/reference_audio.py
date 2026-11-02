"""A voice reference's audio, prepared for the model to continue from."""
from __future__ import annotations

import numpy as np

QUIET_WINDOW_SECONDS = 0.1
QUIET_ABSOLUTE_RMS = 0.015
QUIET_RELATIVE_TO_PEAK = 0.05
KEPT_AFTER_SPEECH_SECONDS = 0.05


def trim_trailing_quiet(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """The clip without the quiet after its last speech.

    In the acoustic-prompt mode the model continues from the end of the reference, and a clip that ends in quiet
    biases it to continue the quiet: Qwen spent its phrase's token budget on silence, so live calls lost words. A clip
    with no audible window is returned as it is.
    """
    window = max(1, int(sample_rate * QUIET_WINDOW_SECONDS))
    levels = np.array([np.sqrt(np.mean(audio[start:start + window] ** 2)) for start in range(0, len(audio), window)])
    if not len(levels):
        return audio
    audible = levels >= max(QUIET_ABSOLUTE_RMS, float(levels.max()) * QUIET_RELATIVE_TO_PEAK)
    if not audible.any():
        return audio
    speech_end = (len(levels) - int(np.argmax(audible[::-1]))) * window
    return audio[:min(len(audio), speech_end + int(sample_rate * KEPT_AFTER_SPEECH_SECONDS))]


__all__ = ["trim_trailing_quiet"]
