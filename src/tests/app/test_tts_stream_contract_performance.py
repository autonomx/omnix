from __future__ import annotations

import numpy as np

from app.gateway.tts_stream_contract import (
    audio_chunk_to_pcm16_bytes,
    initial_speech_start_byte,
)


def _decode_pcm16(payload: bytes) -> list[int]:
    return np.frombuffer(payload, dtype="<i2").astype(np.int32).tolist()


def test_audio_chunk_to_pcm16_bytes_vectorizes_clipping_and_non_finite_values() -> None:
    audio = np.asarray(
        [0.0, 0.5, -0.5, 1.0, -1.0, 2.0, -2.0, np.nan, np.inf, -np.inf],
        dtype=np.float32,
    )

    assert _decode_pcm16(audio_chunk_to_pcm16_bytes(audio)) == [
        0,
        16383,
        -16383,
        32767,
        -32767,
        32767,
        -32767,
        0,
        32767,
        -32767,
    ]


def test_audio_chunk_to_pcm16_bytes_uses_first_channel_for_multichannel_input() -> None:
    stereo = np.asarray([[0.25, 0.75], [-0.25, -0.75]], dtype=np.float32)

    assert _decode_pcm16(audio_chunk_to_pcm16_bytes(stereo)) == [8191, -8191]


def test_initial_speech_start_byte_preserves_configured_preroll() -> None:
    sample_rate = 1_000
    samples = np.zeros(200, dtype="<i2")
    samples[100] = 20_000

    assert initial_speech_start_byte(
        samples.tobytes(),
        sample_rate=sample_rate,
        threshold=0.01,
        preroll_ms=40.0,
    ) == 120


def test_initial_speech_start_byte_handles_negative_full_scale_without_overflow() -> None:
    samples = np.asarray([0, -32_768], dtype="<i2")

    assert initial_speech_start_byte(
        samples.tobytes(),
        sample_rate=24_000,
        threshold=0.5,
        preroll_ms=0.0,
    ) == 2


def test_initial_speech_start_byte_returns_none_for_silence() -> None:
    samples = np.zeros(64, dtype="<i2")

    assert initial_speech_start_byte(
        samples.tobytes(),
        sample_rate=24_000,
        threshold=0.01,
        preroll_ms=40.0,
    ) is None
