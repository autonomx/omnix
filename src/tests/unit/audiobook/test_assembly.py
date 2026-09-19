from __future__ import annotations

import io
import wave
from array import array

import pytest

from app.audiobook.assembly import AudioSpan, PausePolicy, assemble_chapter


def _wav(level: int, frames: int = 1600) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        samples = array("h", [level if index % 2 else -level for index in range(frames)])
        writer.writeframes(samples.tobytes())
    return output.getvalue()


def test_explicit_pause_policy_and_chapter_loudness() -> None:
    result = assemble_chapter([
        AudioSpan("one", "key-one", "narrator", "First.", _wav(1000)),
        AudioSpan("two", "key-two", "narrator", "Second.\n\n", _wav(3000)),
        AudioSpan("three", "key-three", "character", "Third.", _wav(1000)),
    ], policy=PausePolicy(same_speaker_ms=250, speaker_change_ms=500, paragraph_ms=700))
    assert result.timeline[0].pause_before_seconds == 0
    assert result.timeline[1].pause_before_seconds == pytest.approx(0.25)
    assert result.timeline[2].pause_before_seconds == pytest.approx(0.7)
    assert result.duration_seconds == pytest.approx(1.25)
    assert result.applied_gain_db > 0
    assert result.peak_dbfs <= -0.9
    with wave.open(io.BytesIO(result.wav_bytes), "rb") as reader:
        assert reader.getnframes() == 20000


def test_render_audio_change_changes_assembly_identity() -> None:
    first = assemble_chapter([AudioSpan("one", "key", "narrator", "Text", _wav(1000))])
    changed = assemble_chapter([AudioSpan("one", "key", "narrator", "Text", _wav(1100))])
    assert first.assembly_key != changed.assembly_key


def test_sample_rate_mismatch_fails_without_dropping_audio() -> None:
    content = _wav(1000)
    other = io.BytesIO()
    with wave.open(other, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(24000)
        writer.writeframes(array("h", [1000] * 100).tobytes())
    with pytest.raises(ValueError, match="sample rates"):
        assemble_chapter([
            AudioSpan("one", "one", "a", "Text", content),
            AudioSpan("two", "two", "b", "Text", other.getvalue()),
        ])
