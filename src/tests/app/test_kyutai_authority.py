from app.providers.kyutai_authority import (
    KyutaiAuthorityMode,
    evaluate_kyutai_authority,
    parse_authority_mode,
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
    )
    assert blocked.eligible is False
    assert blocked.reasons == ("quality_gate_not_passed", "contention_gate_not_passed")

    promoted = evaluate_kyutai_authority(
        _health(),
        language="fr",
        mode="auto",
        now=1_000.0,
        quality_gate_passed=True,
        contention_gate_passed=True,
    )
    assert promoted.eligible is True


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


def test_authority_mode_parser_rejects_unknown_values() -> None:
    assert parse_authority_mode(None) is KyutaiAuthorityMode.OBSERVATIONAL
    try:
        parse_authority_mode("production-ish")
    except ValueError as exc:
        assert "unsupported Kyutai authority mode" in str(exc)
    else:
        raise AssertionError("unknown authority mode was accepted")
