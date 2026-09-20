from __future__ import annotations

import io
import wave
from array import array

import pytest

from app.audiobook.assembly import AudioSpan, PausePolicy, assemble_chapter
from app.audiobook.assembly_file import AudioFileSpan, assemble_chapter_file, assembly_key_for
from app.persistence.blob_store import LocalBlobStore


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


def test_file_mastering_matches_existing_output_and_timeline(tmp_path) -> None:
    blobs = LocalBlobStore(tmp_path / "blobs")
    inputs = [
        AudioSpan("one", "key-one", "narrator", "First.", _wav(1000, 100000)),
        AudioSpan("two", "key-two", "narrator", "Second.\n\n", _wav(3000)),
        AudioSpan("three", "key-three", "character", "Third.", _wav(1000)),
    ]
    files = []
    for index, span in enumerate(inputs):
        key = f"render/{index}.wav"
        record = blobs.put_bytes(key, span.wav_bytes)
        files.append(AudioFileSpan(
            span.render_id, span.render_key, span.speaker_id, span.source_text,
            key, record["checksum_sha256"], f"span-{index}",
        ))
    expected = assemble_chapter(inputs)
    output = tmp_path / "chapter.wav"
    actual = assemble_chapter_file(blobs, files, output)
    assert output.read_bytes() == expected.wav_bytes
    assert actual.timeline == expected.timeline
    assert actual.assembly_key == expected.assembly_key
    assert assembly_key_for(files) == actual.assembly_key


def test_segments_of_one_source_span_have_no_extra_pause(tmp_path) -> None:
    blobs = LocalBlobStore(tmp_path / "blobs")
    files = []
    for index in range(2):
        key = f"render/{index}.wav"
        record = blobs.put_bytes(key, _wav(1000))
        files.append(AudioFileSpan(
            str(index), str(index), "narrator", "A sentence. ", key,
            record["checksum_sha256"], "same-source-span",
        ))
    actual = assemble_chapter_file(blobs, files, tmp_path / "chapter.wav")
    assert actual.timeline[1].pause_before_seconds == 0
