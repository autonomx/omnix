from __future__ import annotations

import pytest

from app.characters.visemes import fit_visemes, viseme_sequence


def test_viseme_sequence_covers_distinct_visual_mouth_groups() -> None:
    sequence = viseme_sequence("Maya loves five blue owls.")
    assert sequence[0] == "MBP"
    assert "A" in sequence
    assert "FV" in sequence
    assert "L" in sequence
    assert "O" in sequence
    assert "U" in sequence
    assert sequence[-1] == "silence"


def test_fit_visemes_uses_actual_audio_duration() -> None:
    cues = fit_visemes("Hello Maya", 1_250)
    assert cues[0].start_ms == 0
    assert cues[-1].start_ms + cues[-1].duration_ms == pytest.approx(1_250)
    assert all(cue.duration_ms > 0 for cue in cues)
    assert all(left.start_ms < right.start_ms for left, right in zip(cues, cues[1:], strict=False))


def test_empty_text_produces_bounded_silence() -> None:
    cues = fit_visemes("", 400)
    assert len(cues) == 1
    assert cues[0].viseme == "silence"
    assert cues[0].duration_ms == pytest.approx(400)
