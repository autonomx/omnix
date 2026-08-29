from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.agent_runtime.contracts import (
    EvidenceDecision,
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRequirement,
    EvidenceSourceOption,
)
from app.agent_runtime.evidence import (
    EvidenceCompilationError,
    classify_evidence,
    compile_task_authority,
    evaluate_evidence_set,
    validate_required_evidence_capabilities,
)
from app.agent_runtime.profiles import get_agent_profile


@pytest.mark.parametrize(
    "prompt,profile_id",
    [
        ("Tell me the latest PostgreSQL release without using the web", "research"),
        ("What is NVDA trading at right now? Don't use anything external.", "trading-research"),
        ("Check whether the bedroom lamp is on without using any external service", "house"),
        ("Check my calendar for tomorrow without using external services", "personal-assistant"),
    ],
)
def test_current_required_evidence_plus_external_forbidden_fails_closed(
    prompt: str,
    profile_id: str,
) -> None:
    decision = classify_evidence(prompt, profile_id=profile_id)
    assert decision.policy.external_access == "forbidden"
    assert decision.policy.requirement == "required"
    with pytest.raises(EvidenceCompilationError) as caught:
        compile_task_authority(get_agent_profile(profile_id), prompt, decision)
    assert caught.value.code == "external_evidence_forbidden"


@pytest.mark.parametrize(
    "capability",
    [
        "trading.market_quote",
        "weather.current",
        "gmail.read_email",
        "calendar.read_availability",
        "home.get_state",
    ],
)
def test_required_connection_unavailable_is_preflight_failure(
    monkeypatch,
    capability: str,
) -> None:
    from app.assistant_tools import gate
    from app.assistant_tools.models import AssistantToolReviewDecision

    monkeypatch.setattr(
        gate,
        "review_assistant_tool_request",
        lambda request: AssistantToolReviewDecision(
            tool_id=request.tool_id,
            action_id=request.action_id,
            allowed=False,
            reason="missing_connection",
        ),
    )
    with pytest.raises(EvidenceCompilationError) as caught:
        validate_required_evidence_capabilities([capability])
    assert caught.value.code == "required_connection_unavailable"


def test_missing_required_evidence_fails_acceptance_set() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="quote",
                source_class="market_quote",
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=60,
            )
        ],
    )
    result = evaluate_evidence_set("run-1", policy, [])
    assert result.passed is False
    assert result.missing_requirements == ["quote"]


def test_stale_current_evidence_does_not_satisfy_requirement() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="weather",
                source_class="weather_state",
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=300,
            )
        ],
    )
    now = datetime.now(timezone.utc)
    receipt = EvidenceReceipt(
        run_id="run-1",
        capability_id="weather.current",
        source_class="weather_state",
        request_digest="request",
        result_digest="result",
        trust_level="authoritative",
        observed_at=now - timedelta(seconds=301),
        executed_at=now - timedelta(seconds=301),
    )
    result = evaluate_evidence_set("run-1", policy, [receipt], now=now)
    assert result.passed is False
    assert result.requirements[0].status == "stale"


def test_low_trust_result_does_not_satisfy_primary_requirement() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="filing",
                source_class="company_filing",
                trust_floor="primary",
            )
        ],
    )
    receipt = EvidenceReceipt(
        run_id="run-1",
        capability_id="research.web_search",
        source_class="company_filing",
        request_digest="request",
        result_digest="result",
        trust_level="reputable",
    )
    result = evaluate_evidence_set("run-1", policy, [receipt])
    assert result.passed is False
    assert result.requirements[0].status == "insufficient_trust"


def test_fail_closed_requirement_does_not_fall_back_to_general_web() -> None:
    decision = EvidenceDecision(
        policy=EvidencePolicy(
            requirement="required",
            requirements=[
                EvidenceRequirement(
                    id="ci",
                    source_class="repo_ci_state",
                    freshness="current",
                    trust_floor="reputable",
                    fallback_policy="fail_closed",
                    acceptable_sources=[
                        EvidenceSourceOption(
                            source_class="general_current_web",
                            trust_floor="reputable",
                            preference=10,
                        )
                    ],
                )
            ],
        ),
        confidence=1.0,
        reason="test",
    )
    with pytest.raises(EvidenceCompilationError) as caught:
        compile_task_authority(
            get_agent_profile("research"),
            "check current CI",
            decision,
        )
    assert caught.value.code == "required_source_outside_profile_ceiling"


def test_allow_fallback_can_use_profile_compatible_source() -> None:
    decision = EvidenceDecision(
        policy=EvidencePolicy(
            requirement="required",
            requirements=[
                EvidenceRequirement(
                    id="ci",
                    source_class="repo_ci_state",
                    freshness="current",
                    trust_floor="reputable",
                    fallback_policy="allow_fallback",
                    acceptable_sources=[
                        EvidenceSourceOption(
                            source_class="general_current_web",
                            trust_floor="reputable",
                            preference=10,
                        )
                    ],
                )
            ],
        ),
        confidence=1.0,
        reason="test",
    )
    compiled = compile_task_authority(
        get_agent_profile("research"),
        "check current CI",
        decision,
    )
    assert compiled.required_external == ("research.web_search",)


def test_as_of_date_without_source_timestamp_is_rejected() -> None:
    boundary = datetime(2026, 1, 1, tzinfo=timezone.utc)
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="historical",
                source_class="general_current_web",
                freshness="as_of_date",
                as_of_date=boundary,
                max_age_seconds=86400,
            )
        ],
    )
    receipt = EvidenceReceipt(
        run_id="run-1",
        capability_id="research.web_search",
        source_class="general_current_web",
        request_digest="request",
        result_digest="result",
        trust_level="reputable",
        observed_at=boundary,
        executed_at=boundary,
    )
    result = evaluate_evidence_set("run-1", policy, [receipt], now=boundary)
    assert result.passed is False


def test_required_evidence_outside_profile_ceiling_fails_compilation() -> None:
    decision = EvidenceDecision(
        policy=EvidencePolicy(
            requirement="required",
            requirements=[
                EvidenceRequirement(
                    id="email",
                    source_class="email_state",
                    freshness="current",
                    trust_floor="authoritative",
                )
            ],
        ),
        confidence=1.0,
        reason="test",
    )
    with pytest.raises(EvidenceCompilationError) as caught:
        compile_task_authority(get_agent_profile("research"), "check email", decision)
    assert caught.value.code == "required_source_outside_profile_ceiling"
