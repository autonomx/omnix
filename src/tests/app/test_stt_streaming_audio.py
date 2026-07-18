from __future__ import annotations

import wave
from array import array

import pytest

from app.providers.stt_streaming_audio import (
    DEFAULT_SAMPLE_RATE,
    pcm16_duration_ms,
    trim_pcm16_edge_silence,
    write_pcm16_wav,
)


def _pcm(samples: list[int]) -> bytes:
    return array("h", samples).tobytes()


def test_trim_pcm16_edge_silence_preserves_padding() -> None:
    leading = [0] * 6_400
    speech = [2_000] * 3_200
    trailing = [0] * 6_400
    original = _pcm(leading + speech + trailing)

    trimmed, result = trim_pcm16_edge_silence(original, edge_padding_ms=100)

    assert result.speech_detected is True
    assert result.start_sample == 4_800
    assert result.end_sample == 11_200
    assert result.trimmed_samples == 6_400
    assert result.removed_samples == 9_600
    assert pcm16_duration_ms(trimmed) == pytest.approx(400.0)


def test_trim_pcm16_edge_silence_leaves_all_silence_unchanged() -> None:
    original = _pcm([0] * DEFAULT_SAMPLE_RATE)

    trimmed, result = trim_pcm16_edge_silence(original)

    assert trimmed == original
    assert result.speech_detected is False
    assert result.removed_samples == 0


def test_pcm16_helpers_reject_partial_samples(tmp_path) -> None:
    with pytest.raises(ValueError, match="whole samples"):
        pcm16_duration_ms(b"\x00")
    with pytest.raises(ValueError, match="whole samples"):
        trim_pcm16_edge_silence(b"\x00")
    with pytest.raises(ValueError, match="whole samples"):
        write_pcm16_wav(tmp_path / "bad.wav", b"\x00")


def test_write_pcm16_wav_emits_expected_mono_header(tmp_path) -> None:
    pcm = _pcm([100, -100, 200, -200])
    output = write_pcm16_wav(tmp_path / "voice.wav", pcm)

    with wave.open(str(output), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == DEFAULT_SAMPLE_RATE
        assert wav_file.getnframes() == 4
        assert wav_file.readframes(4) == pcm
