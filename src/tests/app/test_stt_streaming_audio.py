from __future__ import annotations

import asyncio
import wave
from array import array

import pytest

from app.providers.stt_live_websocket import SegmentBuffer
from app.providers.stt_segment_scheduler import (
    ProviderSegmentScheduler,
    SegmentQueueFullError,
)
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


def test_segment_buffer_has_exact_primary_sample_accounting() -> None:
    segment = SegmentBuffer(
        segment_id="segment-1",
        sequence=1,
        capture_start_sample=100,
        primary_start_sample=120,
    )

    assert segment.append(100, _pcm([1, 2, 3, 4])) == 104
    assert segment.append(102, _pcm([3, 4, 5, 6])) == 106
    assert bytes(segment.audio) == _pcm([1, 2, 3, 4, 5, 6])

    with pytest.raises(ValueError, match="audio_frame_gap"):
        segment.append(108, _pcm([7]))
    with pytest.raises(ValueError, match="audio_frame_partial_sample"):
        segment.append(106, b"\x00")


def test_provider_scheduler_serializes_inference_and_bounds_sessions() -> None:
    async def scenario() -> None:
        scheduler: ProviderSegmentScheduler[str] = ProviderSegmentScheduler(
            max_queued_jobs=2,
            max_session_jobs=1,
        )
        release = asyncio.Event()
        running = 0
        maximum_running = 0
        order: list[str] = []

        async def run(name: str) -> str:
            nonlocal running, maximum_running
            running += 1
            maximum_running = max(maximum_running, running)
            order.append(name)
            if name == "a":
                await release.wait()
            running -= 1
            return name

        first = await scheduler.submit(
            session_id="session-a",
            segment_id="a",
            sequence=0,
            run=lambda: run("a"),
        )
        await asyncio.sleep(0)
        second = await scheduler.submit(
            session_id="session-b",
            segment_id="b",
            sequence=0,
            run=lambda: run("b"),
        )
        with pytest.raises(SegmentQueueFullError, match="session_queue_full"):
            await scheduler.submit(
                session_id="session-b",
                segment_id="b2",
                sequence=1,
                run=lambda: run("b2"),
            )

        release.set()
        assert await first == "a"
        assert await second == "b"
        assert order == ["a", "b"]
        assert maximum_running == 1
        await scheduler.close()

    asyncio.run(scenario())
