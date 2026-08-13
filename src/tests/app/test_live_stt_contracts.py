from __future__ import annotations

import asyncio
from array import array
from types import SimpleNamespace

from app.providers.live_stt_contracts import (
    CAP_AUTHORITATIVE_EOU,
    CAP_AUTHORITATIVE_FINAL,
    CAP_AUTHORITATIVE_PREVIEW,
    CAP_PARTIAL_TRANSCRIPTS,
    CAP_SEGMENTED_AUDIO,
    CircuitState,
    LiveSttCircuitBreaker,
    LiveSttNegotiation,
)
from app.providers.nemotron_eou_live_websocket import (
    HYBRID_NEGOTIATION,
    HybridSegment,
    _settle_stream_for_final,
    primary_pcm_slice,
)
from app.providers.nemotron_eou_quality import QualityFirstNemotronEouModelManager
from app.providers.nemotron_eou_streaming import (
    HybridStream,
    NemotronEouModelManager,
    StreamingUpdate,
    _normalize_streaming_hypotheses,
    has_eou_token,
    has_meaningful_transcript,
    strip_eou_control_tokens,
)


def test_live_stt_negotiation_emits_stable_ready_payload() -> None:
    negotiation = LiveSttNegotiation(
        provider="parakeet",
        protocol="segmented-v1",
        sample_rate=16_000,
        frame_samples=320,
        capabilities=frozenset({CAP_SEGMENTED_AUDIO, CAP_AUTHORITATIVE_FINAL}),
    )

    assert negotiation.ready_payload(connection_id="connection-1", maxSegmentAudioMs=15_000) == {
        "type": "ready",
        "protocol": "segmented-v1",
        "provider": "parakeet",
        "connectionId": "connection-1",
        "sampleRate": 16_000,
        "frameSamples": 320,
        "encoding": "pcm16le",
        "capabilities": [CAP_AUTHORITATIVE_FINAL, CAP_SEGMENTED_AUDIO],
        "configVersion": "live-stt-v1",
        "maxSegmentAudioMs": 15_000,
    }


def test_hybrid_stt_negotiation_separates_transcript_and_eou_authority() -> None:
    assert HYBRID_NEGOTIATION.provider == "nemotron_parakeet_eou"
    assert CAP_AUTHORITATIVE_FINAL in HYBRID_NEGOTIATION.capabilities
    assert CAP_PARTIAL_TRANSCRIPTS in HYBRID_NEGOTIATION.capabilities
    assert CAP_AUTHORITATIVE_EOU in HYBRID_NEGOTIATION.capabilities
    assert CAP_AUTHORITATIVE_PREVIEW in HYBRID_NEGOTIATION.capabilities


def test_eou_control_tokens_never_enter_authoritative_transcript() -> None:
    raw = "Where are we going? <EOU>"

    assert has_eou_token(raw) is True
    assert strip_eou_control_tokens(raw) == "Where are we going?"
    assert strip_eou_control_tokens("Hello <EOB> there <EOU>") == "Hello there"


def test_meaningful_transcript_requires_actual_user_text() -> None:
    assert has_meaningful_transcript("") is False
    assert has_meaningful_transcript("   ... ") is False
    assert has_meaningful_transcript("I") is True
    assert has_meaningful_transcript("yes") is True


def test_streaming_hypotheses_flatten_mapping_timestamps_for_continuation_merge() -> None:
    hypothesis = SimpleNamespace(
        timestamp={"timestep": [2, 5], "segment": [[2, 5]]},
    )
    untouched = SimpleNamespace(timestamp=[7])

    normalized = _normalize_streaming_hypotheses((hypothesis, untouched))

    assert normalized == [hypothesis, untouched]
    assert hypothesis.timestamp == [2, 5]
    assert untouched.timestamp == [7]


def test_model_manager_ignores_pre_speech_eou_and_rearms(monkeypatch) -> None:
    manager = NemotronEouModelManager()
    stream = SimpleNamespace(
        nemotron=SimpleNamespace(
            feed_pcm16=lambda _: StreamingUpdate("", False, False, 1.0),
        ),
        eou=SimpleNamespace(
            feed_pcm16=lambda _: StreamingUpdate("", False, True, 2.0),
        ),
        last_partial="",
        eou_rearm_count=0,
        ignored_pre_speech_eou_count=0,
    )
    rearmed: list[str] = []

    monkeypatch.setattr(manager, "ensure_stream", lambda _: stream)

    def fake_rearm(segment_id: str) -> bool:
        rearmed.append(segment_id)
        stream.eou_rearm_count += 1
        return True

    monkeypatch.setattr(manager, "rearm_eou", fake_rearm)

    update = manager.feed("segment-1", b"\x00\x00")

    assert update.eou is False
    assert update.transcript == ""
    assert rearmed == ["segment-1"]
    assert stream.ignored_pre_speech_eou_count == 1


def test_model_manager_surfaces_eou_after_meaningful_nemotron_text(monkeypatch) -> None:
    manager = NemotronEouModelManager()
    stream = SimpleNamespace(
        nemotron=SimpleNamespace(
            feed_pcm16=lambda _: StreamingUpdate("Yes", True, False, 1.0),
        ),
        eou=SimpleNamespace(
            feed_pcm16=lambda _: StreamingUpdate("", False, True, 2.0),
        ),
        last_partial="",
        eou_rearm_count=0,
        ignored_pre_speech_eou_count=0,
    )
    rearmed: list[str] = []

    monkeypatch.setattr(manager, "ensure_stream", lambda _: stream)

    def fake_rearm(segment_id: str) -> bool:
        rearmed.append(segment_id)
        stream.eou_rearm_count += 1
        return True

    monkeypatch.setattr(manager, "rearm_eou", fake_rearm)

    update = manager.feed("segment-2", b"\x00\x00")

    assert update.eou is True
    assert update.transcript == "Yes"
    assert rearmed == ["segment-2"]
    assert stream.ignored_pre_speech_eou_count == 0


def test_model_manager_rearms_only_eou_stream(monkeypatch) -> None:
    manager = NemotronEouModelManager()
    manager.eou_model = object()
    original_nemotron = object()
    original_eou = object()
    replacement_eou = object()
    stream = HybridStream(nemotron=original_nemotron, eou=original_eou)  # type: ignore[arg-type]
    manager._streams["segment-3"] = stream

    monkeypatch.setattr(
        "app.providers.nemotron_eou_streaming.CacheAwareRnntStream",
        lambda *args, **kwargs: replacement_eou,
    )

    assert manager.rearm_eou("segment-3") is True
    assert stream.nemotron is original_nemotron
    assert stream.eou is replacement_eou
    assert stream.eou_rearm_count == 1


def test_quality_first_final_prefers_full_buffer_decode(monkeypatch) -> None:
    manager = QualityFirstNemotronEouModelManager()
    manager._streams["segment-quality"] = SimpleNamespace(
        nemotron=SimpleNamespace(finalize_text=lambda: "How are"),
    )
    monkeypatch.setattr(
        manager,
        "transcribe_pcm16",
        lambda _: "How are you doing today?",
    )

    text, metrics = manager.finalize("segment-quality", b"\x00\x00")

    assert text == "How are you doing today?"
    assert metrics["authoritative_full_decode"] == 1.0
    assert metrics["streaming_final"] == 0.0
    assert metrics["authoritative_changed"] == 1.0
    assert metrics["streaming_chars"] == 7.0
    assert metrics["authoritative_chars"] == 24.0
    assert metrics["final_right_context"] == 13.0


def test_quality_first_final_uses_high_context_then_restores_live_context(monkeypatch) -> None:
    contexts: list[list[int]] = []

    class FakeEncoder:
        def set_default_att_context_size(self, *, att_context_size: list[int]) -> None:
            contexts.append(list(att_context_size))

    manager = QualityFirstNemotronEouModelManager()
    manager.nemotron_model = SimpleNamespace(encoder=FakeEncoder())
    manager._streams["segment-context"] = SimpleNamespace(
        nemotron=SimpleNamespace(finalize_text=lambda: "Then I score"),
    )

    def decode(_: bytes) -> str:
        assert contexts[-1] == [70, 13]
        return "Then let's go to a river."

    monkeypatch.setattr(manager, "transcribe_pcm16", decode)

    text, metrics = manager.finalize("segment-context", b"\x00\x00")

    assert text == "Then let's go to a river."
    assert contexts == [[70, 13], [70, 1]]
    assert metrics["final_right_context"] == 13.0
    assert metrics["authoritative_changed"] == 1.0


def test_quality_first_final_falls_back_to_streaming_if_full_decode_fails(monkeypatch) -> None:
    manager = QualityFirstNemotronEouModelManager()
    manager._streams["segment-fallback"] = SimpleNamespace(
        nemotron=SimpleNamespace(finalize_text=lambda: "Short but usable"),
    )

    def fail_decode(_: bytes) -> str:
        raise RuntimeError("decode_failed")

    monkeypatch.setattr(manager, "transcribe_pcm16", fail_decode)

    text, metrics = manager.finalize("segment-fallback", b"\x00\x00")

    assert text == "Short but usable"
    assert metrics["full_decode_failed"] == 1.0
    assert metrics["streaming_final"] == 1.0
    assert metrics["authoritative_full_decode"] == 0.0


def test_quality_preview_can_be_promoted_without_a_second_decode(monkeypatch) -> None:
    manager = QualityFirstNemotronEouModelManager()
    manager._streams["segment-preview"] = SimpleNamespace(
        nemotron=SimpleNamespace(finalize_text=lambda: "How do you feel"),
    )
    decode_calls: list[bytes] = []

    def decode(payload: bytes) -> str:
        decode_calls.append(payload)
        return "How do you feel about today?"

    monkeypatch.setattr(manager, "transcribe_pcm16", decode)

    preview_text, preview_metrics = manager.preview(b"\x00\x00")
    final_text, final_metrics = manager.finalize_from_preview(
        "segment-preview",
        preview_text,
        preview_metrics["preview_decode_ms"],
    )

    assert decode_calls == [b"\x00\x00"]
    assert final_text == "How do you feel about today?"
    assert final_metrics["authoritative_preview_reused"] == 1.0
    assert final_metrics["authoritative_full_decode"] == 1.0


def test_hybrid_stream_drops_cross_segment_overlap_before_inference() -> None:
    samples = array("h", [10, 20, 30, 40]).tobytes()

    assert primary_pcm_slice(100, 102, samples) == array("h", [30, 40]).tobytes()
    assert primary_pcm_slice(102, 102, samples) == samples
    assert primary_pcm_slice(100, 104, samples) == b""


def test_final_settle_discards_only_draft_tail_and_waits_for_active_feed() -> None:
    async def exercise() -> tuple[int, bool, bytes, bytes]:
        segment = HybridSegment(
            segment_id="segment-final",
            sequence=0,
            capture_start_sample=0,
            primary_start_sample=0,
        )
        segment.primary_audio.extend(b"\x01\x00\x02\x00")
        segment.stream_pending.extend(b"\x01\x00\x02\x00")
        feed_completed = False

        async def active_feed() -> None:
            nonlocal feed_completed
            await asyncio.sleep(0)
            feed_completed = True

        segment.stream_task = asyncio.create_task(active_feed())
        discarded = await _settle_stream_for_final(segment)
        return discarded, feed_completed, bytes(segment.primary_audio), bytes(segment.stream_pending)

    discarded, feed_completed, primary_audio, stream_pending = asyncio.run(exercise())

    assert discarded == 2
    assert feed_completed is True
    assert primary_audio == b"\x01\x00\x02\x00"
    assert stream_pending == b""


def test_authoritative_preview_reuse_requires_only_quiet_tail_audio() -> None:
    segment = HybridSegment(
        segment_id="segment-preview",
        sequence=0,
        capture_start_sample=0,
        primary_start_sample=0,
    )
    segment.append(0, array("h", [1200, -1200] * 160).tobytes())
    segment.remember_preview(
        request_id="preview-1",
        text="Hello there.",
        decode_ms=90.0,
        end_sample=320,
    )
    segment.append(320, array("h", [100, -100] * 160).tobytes())
    assert segment.can_reuse_preview() is True

    segment.append(640, array("h", [2000, -2000] * 160).tobytes())
    assert segment.can_reuse_preview() is False


def test_live_stt_circuit_breaker_opens_and_probes_after_cooldown() -> None:
    now = [100.0]
    breaker = LiveSttCircuitBreaker(
        failure_threshold=3,
        window_attempts=5,
        cooldown_seconds=60.0,
        max_cooldown_seconds=120.0,
        clock=lambda: now[0],
    )

    assert breaker.allow_new_session() is True
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()

    assert breaker.state is CircuitState.OPEN
    assert breaker.allow_new_session() is False
    assert breaker.snapshot().failures_in_window == 3

    now[0] += 60.0
    assert breaker.state is CircuitState.HALF_OPEN
    assert breaker.allow_new_session() is True
    assert breaker.allow_new_session() is False

    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED
    assert breaker.allow_new_session() is True


def test_live_stt_circuit_breaker_opens_immediately_for_non_transient_failure() -> None:
    breaker = LiveSttCircuitBreaker()

    breaker.record_failure(transient=False)
