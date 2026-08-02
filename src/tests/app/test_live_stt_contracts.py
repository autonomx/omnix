from __future__ import annotations

from app.providers.live_stt_contracts import (
    CAP_AUTHORITATIVE_FINAL,
    CAP_SEGMENTED_AUDIO,
    CircuitState,
    LiveSttCircuitBreaker,
    LiveSttNegotiation,
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

    assert breaker.state is CircuitState.OPEN
