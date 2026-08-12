from __future__ import annotations

import asyncio
import struct
import wave
from array import array

import pytest

from app.providers.nemotron_eou_quality import (
    QualityFirstNemotronEouModelManager,
    _pcm16_peak_abs,
)
from app.providers.stt_live_websocket import (
    MAX_REPLAY_RESULTS,
    SegmentBuffer,
    SegmentSessionState,
)
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


def test_completed_segment_buffers_are_released_and_replay_results_are_bounded() -> None:
    state = SegmentSessionState(session_id="stt:test")

    for sequence in range(MAX_REPLAY_RESULTS + 5):
        segment_id = f"segment-{sequence}"
        state.segments[segment_id] = SegmentBuffer(
            segment_id=segment_id,
            sequence=sequence,
            capture_start_sample=sequence * 100,
            primary_start_sample=sequence * 100,
        )
        state.remember_result(
            {
                "type": "result_available",
                "sequence": sequence,
                "segmentId": segment_id,
                "resultId": f"result-{sequence}",
            }
        )
        state.release_segment(segment_id)

    assert state.segments == {}
    assert state.inflight == {}
    assert len(state.results) == MAX_REPLAY_RESULTS
    assert min(state.results) == 5
    assert max(state.results) == MAX_REPLAY_RESULTS + 4


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


class _FakeNemotronStream:
    def __init__(self, text: str) -> None:
        self.text = text

    def finalize_text(self) -> str:
        return self.text


class _FakeHybridStream:
    def __init__(self, text: str) -> None:
        self.nemotron = _FakeNemotronStream(text)


class _StubQualityManager(QualityFirstNemotronEouModelManager):
    def __init__(self, outputs: list[str]) -> None:
        super().__init__()
        self.outputs = list(outputs)
        self.decode_inputs: list[bytes] = []

    def _transcribe_quality_pcm16(self, pcm16le: bytes) -> str:
        self.decode_inputs.append(pcm16le)
        if not self.outputs:
            raise AssertionError("unexpected_quality_decode")
        return self.outputs.pop(0)


def _quality_pcm(sample: int, count: int) -> bytes:
    return struct.pack("<h", sample) * count


def _seed_quality(
    manager: _StubQualityManager,
    *,
    segment_id: str,
    text: str,
    audio: bytes,
) -> None:
    manager._streams[segment_id] = _FakeHybridStream(text)  # type: ignore[assignment]
    manager._quality_audio[segment_id] = bytearray(audio)


def test_authoritative_predecode_reuses_identical_prefix_with_quiet_tail() -> None:
    manager = _StubQualityManager(["authoritative sentence"])
    segment_id = "segment-quiet-tail"
    audio = _quality_pcm(1_500, 3_200)
    _seed_quality(manager, segment_id=segment_id, text="streaming sentence", audio=audio)

    manager._run_predecode(segment_id)
    text, metrics = manager.finalize(segment_id, audio + _quality_pcm(0, 1_600))

    assert text == "authoritative sentence"
    assert metrics["authoritative_predecode_reused"] == 1.0
    assert metrics["authoritative_full_decode"] == 1.0
    assert len(manager.decode_inputs) == 1


def test_authoritative_predecode_changed_text_forces_fresh_decode() -> None:
    manager = _StubQualityManager(["early authoritative", "final authoritative"])
    segment_id = "segment-changed-text"
    audio = _quality_pcm(1_500, 3_200)
    _seed_quality(manager, segment_id=segment_id, text="early streaming", audio=audio)

    manager._run_predecode(segment_id)
    manager._streams[segment_id].nemotron.text = "later streaming"  # type: ignore[attr-defined]
    text, metrics = manager.finalize(segment_id, audio)

    assert text == "final authoritative"
    assert metrics["authoritative_predecode_reused"] == 0.0
    assert len(manager.decode_inputs) == 2


def test_authoritative_predecode_nonquiet_tail_forces_fresh_decode() -> None:
    manager = _StubQualityManager(["early authoritative", "final authoritative"])
    segment_id = "segment-nonquiet-tail"
    audio = _quality_pcm(1_500, 3_200)
    _seed_quality(manager, segment_id=segment_id, text="same streaming", audio=audio)

    manager._run_predecode(segment_id)
    tail_sample = manager.predecode_tail_peak + 1
    text, metrics = manager.finalize(segment_id, audio + _quality_pcm(tail_sample, 320))

    assert text == "final authoritative"
    assert metrics["authoritative_predecode_reused"] == 0.0
    assert metrics["predecode_tail_peak"] == float(tail_sample)
    assert len(manager.decode_inputs) == 2


def test_authoritative_predecode_peak_is_conservative_for_partial_samples() -> None:
    assert _pcm16_peak_abs(_quality_pcm(-321, 4)) == 321
    assert _pcm16_peak_abs(b"\x00") == 32_767
