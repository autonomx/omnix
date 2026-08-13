from __future__ import annotations

import struct

from app.gateway.tts_live_call_startup_frame_policy import (
    TTS_LIVE_CALL_FIRST_CHUNK_MAX_INITIAL_SILENCE_MS,
    TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD,
    TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES,
    live_call_max_initial_silence_ms_for_first_chunk,
)
from app.gateway.tts_stream_contract import (
    STREAM_MAX_INITIAL_SILENCE_MS,
    stream_pcm16_blocks,
)


def _pcm16(sample: int, count: int) -> bytes:
    return struct.pack("<h", sample) * count


def test_two_step_first_chunk_arms_nonzero_fallback_after_one_chunk() -> None:
    quiet_signal = _pcm16(1, TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES)
    max_initial_silence_ms = live_call_max_initial_silence_ms_for_first_chunk(
        quiet_signal,
        24_000,
    )

    assert max_initial_silence_ms == TTS_LIVE_CALL_FIRST_CHUNK_MAX_INITIAL_SILENCE_MS
    assert max_initial_silence_ms == 160.0

    blocks = list(
        stream_pcm16_blocks(
            iter([(quiet_signal, 24_000, {"chunk": 0})]),
            block_samples=TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES,
            silence_threshold=TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD,
            max_initial_silence_ms=max_initial_silence_ms,
        )
    )

    assert blocks
    first_samples = struct.unpack("<3840h", blocks[0][0])
    assert any(sample != 0 for sample in first_samples)


def test_two_step_first_chunk_still_rejects_exact_digital_silence() -> None:
    silence = _pcm16(0, TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES)

    blocks = list(
        stream_pcm16_blocks(
            iter([(silence, 24_000, {"chunk": 0})]),
            block_samples=TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES,
            silence_threshold=TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD,
            max_initial_silence_ms=live_call_max_initial_silence_ms_for_first_chunk(
                silence,
                24_000,
            ),
        )
    )

    assert blocks == []


def test_four_step_first_chunk_keeps_established_scan_window() -> None:
    four_step_samples = TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES * 2
    quiet_signal = _pcm16(1, four_step_samples)
    max_initial_silence_ms = live_call_max_initial_silence_ms_for_first_chunk(
        quiet_signal,
        24_000,
    )

    assert max_initial_silence_ms == STREAM_MAX_INITIAL_SILENCE_MS
    assert max_initial_silence_ms == 400.0

    blocks = list(
        stream_pcm16_blocks(
            iter([(quiet_signal, 24_000, {"chunk": 0})]),
            block_samples=TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES,
            silence_threshold=TTS_LIVE_CALL_INITIAL_SILENCE_THRESHOLD,
            max_initial_silence_ms=max_initial_silence_ms,
        )
    )

    assert blocks == []
