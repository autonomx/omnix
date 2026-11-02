"""A voice reference ends at its speech: quiet after it biased Qwen to generate silence on live calls."""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from app.providers.reference_audio import KEPT_AFTER_SPEECH_SECONDS, trim_trailing_quiet

RATE = 24_000


def _clip(*parts: tuple[float, float]) -> np.ndarray:
    """Sections of (seconds, loudness): a tone at that level, so the level is the section's rough RMS."""
    sections = []
    for seconds, level in parts:
        times = np.arange(int(seconds * RATE)) / RATE
        sections.append(np.sin(2 * np.pi * 220 * times).astype(np.float32) * level * np.sqrt(2))
    return np.concatenate(sections)


def test_the_quiet_after_the_last_speech_goes_and_the_speech_stays() -> None:
    trimmed = trim_trailing_quiet(_clip((1.0, 0.1), (0.8, 0.001)), RATE)
    assert 1.0 <= len(trimmed) / RATE <= 1.0 + 0.1 + KEPT_AFTER_SPEECH_SECONDS + 0.001


def test_a_pause_inside_the_speech_and_quiet_before_it_are_kept() -> None:
    clip = _clip((0.5, 0.001), (1.0, 0.1), (0.7, 0.001), (1.0, 0.1), (0.5, 0.001))
    trimmed = trim_trailing_quiet(clip, RATE)
    assert 3.2 <= len(trimmed) / RATE <= 3.2 + 0.1 + KEPT_AFTER_SPEECH_SECONDS + 0.001
    assert np.array_equal(trimmed, clip[:len(trimmed)])


def test_quiet_is_judged_against_the_clips_own_loudness() -> None:
    # Background noise at 0.03 is audible by the absolute floor, not beside speech at 0.8.
    assert len(trim_trailing_quiet(_clip((1.0, 0.8), (1.0, 0.03)), RATE)) / RATE < 1.2


def test_a_clip_that_ends_at_its_speech_is_unchanged() -> None:
    clip = _clip((1.0, 0.1))
    assert len(trim_trailing_quiet(clip, RATE)) == len(clip)


@pytest.mark.parametrize("clip", [np.zeros(RATE, dtype=np.float32), np.zeros(0, dtype=np.float32), _clip((1.0, 0.002))])
def test_a_clip_with_nothing_audible_is_returned_as_it_is(clip: np.ndarray) -> None:
    assert trim_trailing_quiet(clip, RATE) is clip


def test_the_model_sees_exactly_the_silence_it_asked_for(tmp_path) -> None:
    pytest.importorskip("torch")
    from app.providers.vendor.faster_qwen3_tts.model import FasterQwen3TTS

    path = tmp_path / "reference.wav"
    sf.write(str(path), _clip((1.0, 0.1), (0.8, 0.001)), RATE)
    load = FasterQwen3TTS._load_ref_audio_with_silence
    bare, rate = load(None, path, silence_secs=0.0)
    padded, _ = load(None, path, silence_secs=0.5)
    assert rate == RATE and len(bare) / RATE < 1.2
    assert len(padded) - len(bare) == int(0.5 * RATE)
