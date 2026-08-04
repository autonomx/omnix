from app.providers.kyutai_authority import (
    KyutaiAuthorityMode,
    KyutaiReleaseMeasurements,
    classify_kyutai_probe_error,
    evaluate_kyutai_authority,
    parse_authority_mode,
    safe_kyutai_probe_error_code,
)


def _health(**overrides):
    payload = {
        "state": "closed",
        "upstream_ready": True,
        "last_ready_at": 995.0,
        "supported_languages": ["en", "fr"],
    }
    payload.update(overrides)
    return payload


def _passing_measurements(**overrides):
    values = {
        "median_end_to_audio_ms": 500.0,
        "p95_end_to_audio_ms": 800.0,
        "false_endpoint_rate": 0.01,
        "missed_endpoint_rate": 0.02,
        "interruption_to_silence_ms": 180.0,
        "underrun_turn_rate": 0.01,
        "downstream_p95_regression": 0.08,
    }
    values.update(overrides)
    return KyutaiReleaseMeasurements(**values)


def test_test_mode_requires_ready_warm_supported_provider() -> None:
    decision = evaluate_kyutai_authority(
        _health(),
        language="en",
        mode=KyutaiAuthorityMode.TEST,
        now=1_000.0,
        warm_max_age_seconds=10.0,
        quality_gate_passed=False,
        contention_gate_passed=False,
    )
    assert decision.eligible is True
    assert decision.reasons == ()


def test_auto_mode_fails_closed_until_release_evidence_passes() -> None:
    blocked = evaluate_kyutai_authority(
        _health(),
        language="en",
        mode="auto",
        now=1_000.0,
        quality_gate_passed=False,
        contention_gate_passed=False,
        measurements=_passing_measurements(),
    )
    assert blocked.eligible is False
    assert blocked.reasons == (
        "quality_gate_not_passed",
        "contention_gate_not_passed",
    )

    promoted = evaluate_kyutai_authority(
        _health(),
        language="fr",
        mode="auto",
        now=1_000.0,
        quality_gate_passed=True,
        contention_gate_passed=True,
        measurements=_passing_measurements(),
    )
    assert promoted.eligible is True


def test_auto_mode_rejects_approved_but_failed_measurements(monkeypatch) -> None:
    monkeypatch.setenv("KYUTAI_STT_QUALITY_GATE_PASSED", "true")
    monkeypatch.setenv("KYUTAI_STT_CONTENTION_GATE_PASSED", "true")
    decision = evaluate_kyutai_authority(
        _health(),
        language="en",
        mode="auto",
        now=1_000.0,
        measurements=_passing_measurements(
            p95_end_to_audio_ms=1_200.0,
            downstream_p95_regression=0.2,
        ),
    )
    assert decision.eligible is False
    assert "quality_metrics_not_satisfied" in decision.reasons
    assert "contention_metrics_not_satisfied" in decision.reasons
    assert decision.quality_metric_failures == (
        "p95_end_to_audio_ms:above_1000",
    )
    assert decision.contention_metric_failures == (
        "downstream_p95_regression:above_0.15",
    )


def test_auto_mode_requires_complete_measurement_evidence(monkeypatch) -> None:
    monkeypatch.setenv("KYUTAI_STT_QUALITY_GATE_PASSED", "true")
    monkeypatch.setenv("KYUTAI_STT_CONTENTION_GATE_PASSED", "true")
    decision = evaluate_kyutai_authority(
        _health(),
        language="en",
        mode="auto",
        now=1_000.0,
        measurements=KyutaiReleaseMeasurements(),
    )
    assert decision.eligible is False
    assert "median_end_to_audio_ms:missing" in decision.quality_metric_failures
    assert decision.contention_metric_failures == (
        "downstream_p95_regression:missing",
    )


def test_explicit_auto_approvals_cannot_bypass_measurement_gates() -> None:
    decision = evaluate_kyutai_authority(
        _health(),
        language="en",
        mode="auto",
        now=1_000.0,
        quality_gate_passed=True,
        contention_gate_passed=True,
        measurements=KyutaiReleaseMeasurements(),
    )

    assert decision.eligible is False
    assert decision.quality_gate_passed is False
    assert decision.contention_gate_passed is False
    assert "quality_metrics_not_satisfied" in decision.reasons
    assert "contention_metrics_not_satisfied" in decision.reasons
    assert "quality_gate_not_passed" in decision.reasons
    assert "contention_gate_not_passed" in decision.reasons


def test_authority_rejects_cold_or_unsupported_sessions() -> None:
    decision = evaluate_kyutai_authority(
        _health(last_ready_at=100.0),
        language="ja",
        mode="test",
        now=1_000.0,
        warm_max_age_seconds=10.0,
    )
    assert decision.eligible is False
    assert "language_not_supported" in decision.reasons
    assert "model_not_warm" in decision.reasons


def test_authority_surfaces_safe_probe_failure_classification() -> None:
    decision = evaluate_kyutai_authority(
        _health(
            upstream_ready=False,
            last_ready_at=None,
            last_error="Could not connect to Kyutai STT: [WinError 10061] Connection refused",
        ),
        language="en",
        mode="test",
        now=1_000.0,
    )
    assert decision.eligible is False
    assert decision.reasons == (
        "upstream_not_ready",
        "upstream_connection_refused",
        "model_not_warm",
    )


def test_authority_prefers_provider_structured_probe_code() -> None:
    decision = evaluate_kyutai_authority(
        _health(
            upstream_ready=False,
            last_ready_at=None,
            last_error="unclassified local transport detail",
            last_error_code="upstream_endpoint_not_found",
        ),
        language="en",
        mode="test",
        now=1_000.0,
    )
    assert decision.reasons == (
        "upstream_not_ready",
        "upstream_endpoint_not_found",
        "model_not_warm",
    )


def test_probe_error_classifier_does_not_expose_raw_error_text() -> None:
    assert classify_kyutai_probe_error("operation timed out") == "upstream_connect_timeout"
    assert classify_kyutai_probe_error("401 unauthorized token") == "upstream_auth_rejected"
    assert classify_kyutai_probe_error("HTTP 404") == "upstream_endpoint_not_found"
    assert classify_kyutai_probe_error("status code 503") == "upstream_service_unavailable"
    assert classify_kyutai_probe_error("certificate verify failed") == "upstream_tls_error"
    assert classify_kyutai_probe_error("no close frame received") == "upstream_connection_closed"
    assert classify_kyutai_probe_error("Expected Kyutai Ready, received 'Other'") == "upstream_protocol_error"
    assert classify_kyutai_probe_error("getaddrinfo failed") == "upstream_dns_error"
    assert classify_kyutai_probe_error("unexpected local failure detail") == "upstream_probe_failed"
    assert classify_kyutai_probe_error(None) is None


def test_structured_probe_code_is_allowlisted() -> None:
    assert safe_kyutai_probe_error_code("upstream_rate_limited") == "upstream_rate_limited"
    assert safe_kyutai_probe_error_code("private filesystem detail") is None
    assert safe_kyutai_probe_error_code(None) is None


def test_authority_mode_parser_rejects_unknown_values() -> None:
    assert parse_authority_mode(None) is KyutaiAuthorityMode.OBSERVATIONAL
    try:
        parse_authority_mode("production-ish")
    except ValueError as exc:
        assert "unsupported Kyutai authority mode" in str(exc)
    else:
        raise AssertionError("unknown authority mode was accepted")
