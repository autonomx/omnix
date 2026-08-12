from __future__ import annotations

import struct

from app.providers.nemotron_eou_quality import (
    QualityFirstNemotronEouModelManager,
    _pcm16_peak_abs,
)


class FakeNemotronStream:
    def __init__(self, text: str) -> None:
        self.text = text

    def finalize_text(self) -> str:
        return self.text


class FakeHybridStream:
    def __init__(self, text: str) -> None:
        self.nemotron = FakeNemotronStream(text)


class StubQualityManager(QualityFirstNemotronEouModelManager):
    def __init__(self, outputs: list[str]) -> None:
        super().__init__()
        self.outputs = list(outputs)
        self.decode_inputs: list[bytes] = []

    def _transcribe_quality_pcm16(self, pcm16le: bytes) -> str:
        self.decode_inputs.append(pcm16le)
        if not self.outputs:
            raise AssertionError("unexpected_quality_decode")
        return self.outputs.pop(0)


def _pcm(sample: int, count: int) -> bytes:
    return struct.pack("<h", sample) * count


def _seed(manager: StubQualityManager, *, segment_id: str, text: str, audio: bytes) -> None:
    manager._streams[segment_id] = FakeHybridStream(text)  # type: ignore[assignment]
    manager._quality_audio[segment_id] = bytearray(audio)


def test_predecode_reuses_identical_prefix_with_quiet_tail() -> None:
    manager = StubQualityManager(["authoritative sentence"])
    segment_id = "segment-quiet-tail"
    audio = _pcm(1_500, 3_200)
    _seed(manager, segment_id=segment_id, text="streaming sentence", audio=audio)

    manager._run_predecode(segment_id)
    final_audio = audio + _pcm(0, 1_600)
    text, metrics = manager.finalize(segment_id, final_audio)

    assert text == "authoritative sentence"
    assert metrics["authoritative_predecode_reused"] == 1.0
    assert metrics["authoritative_full_decode"] == 1.0
    assert len(manager.decode_inputs) == 1


def test_predecode_changed_streaming_text_forces_fresh_full_decode() -> None:
    manager = StubQualityManager(["early authoritative", "final authoritative"])
    segment_id = "segment-changed-text"
    audio = _pcm(1_500, 3_200)
    _seed(manager, segment_id=segment_id, text="early streaming", audio=audio)

    manager._run_predecode(segment_id)
    manager._streams[segment_id].nemotron.text = "later streaming"  # type: ignore[attr-defined]
    text, metrics = manager.finalize(segment_id, audio)

    assert text == "final authoritative"
    assert metrics["authoritative_predecode_reused"] == 0.0
    assert len(manager.decode_inputs) == 2


def test_predecode_nonquiet_tail_forces_fresh_full_decode() -> None:
    manager = StubQualityManager(["early authoritative", "final authoritative"])
    segment_id = "segment-nonquiet-tail"
    audio = _pcm(1_500, 3_200)
    _seed(manager, segment_id=segment_id, text="same streaming", audio=audio)

    manager._run_predecode(segment_id)
    final_audio = audio + _pcm(manager.predecode_tail_peak + 1, 320)
    text, metrics = manager.finalize(segment_id, final_audio)

    assert text == "final authoritative"
    assert metrics["authoritative_predecode_reused"] == 0.0
    assert metrics["predecode_tail_peak"] == float(manager.predecode_tail_peak + 1)
    assert len(manager.decode_inputs) == 2


def test_pcm_peak_is_conservative_for_partial_samples() -> None:
    assert _pcm16_peak_abs(_pcm(-321, 4)) == 321
    assert _pcm16_peak_abs(b"\x00") == 32_767
