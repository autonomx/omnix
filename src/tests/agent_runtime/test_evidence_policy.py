from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.agent_runtime.acceptance import evaluate_acceptance
from app.agent_runtime.contracts import (
    AgentRunSpec,
    EvidenceDecision,
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRequirement,
    EvidenceSourceOption,
    ModelRef,
    SubjectRef,
    TaskRevision,
)
from app.agent_runtime.evidence import (
    EvidenceCompilationError,
    build_evidence_receipt,
    classify_evidence,
    compile_task_authority,
    evaluate_evidence_set,
    freshness_max_age_seconds,
    resolve_request_mode,
)
from app.agent_runtime.profiles import get_agent_profile


def _receipt(
    *,
    source_class: str,
    subject: SubjectRef | None = None,
    age_seconds: int = 0,
    trust: str = "authoritative",
    manifest: str | None = "manifest-1",
) -> EvidenceReceipt:
    observed = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return EvidenceReceipt(
        receipt_id=f"receipt-{source_class}-{age_seconds}-{trust}",
        run_id="run-1",
        capability_id="test.capability",
        source_class=source_class,
        subject=subject,
        request_digest="req",
        source_manifest_id=manifest,
        observed_at=observed,
        executed_at=observed,
        trust_level=trust,
        result_digest="result",
    )


@pytest.mark.parametrize(
    "content,turn_mode,persistent,lane,expected,source",
    [
        ("/agent research NVDA", "deep", True, "agent", "agent", "explicit_command"),
        ("research NVDA", "quick", True, "agent", "quick_research", "turn_setting"),
        ("research NVDA", "deep", True, "agent", "deep_research", "turn_setting"),
        ("implement feature", None, False, "agent", "agent", "classifier"),
        ("hello", None, False, "chat", "auto", "classifier"),
    ],
)
def test_request_mode_precedence(content, turn_mode, persistent, lane, expected, source) -> None:
    selected = resolve_request_mode(
        content,
        turn_research_mode=turn_mode,
        persistent_agent=persistent,
        classifier_lane=lane,
    )
    assert selected.mode == expected
    assert selected.source == source


def test_timeless_conceptual_trading_question_needs_no_external_evidence() -> None:
    decision = classify_evidence("What is a stock split?", profile_id="trading-research")
    assert decision.policy.requirement == "none"
    assert decision.policy.external_access == "allowed"


def test_current_general_research_requires_web_evidence() -> None:
    decision = classify_evidence("What is the latest PostgreSQL release?", profile_id="research")
    assert decision.policy.requirement == "required"
    assert decision.policy.requirements[0].source_class == "software_release"
    compiled = compile_task_authority(get_agent_profile("research"), "latest PostgreSQL release", decision)
    assert compiled.required_external == ("research.web_search",)


def test_explicit_source_request_requires_attribution_ready_evidence() -> None:
    decision = classify_evidence(
        "Research the latest PostgreSQL release with sources",
        profile_id="research",
    )
    assert decision.policy.user_visible_attribution == "required"
    spec = AgentRunSpec(
        run_id="run-1",
        task="research",
        profile="research",
        model=ModelRef(provider_id="test", model_id="model"),
        evidence_policy=decision.policy,
        external_capabilities=["research.web_search"],
    )
    missing = evaluate_acceptance(spec, events=[], artifacts=[], evidence_set=None)
    assert not missing.passed
    assert "user_visible_attribution_unavailable" in missing.failures


def test_market_quote_fails_closed_without_authoritative_capability() -> None:
    decision = classify_evidence("What is NVDA trading at today?", profile_id="trading-research")
    assert decision.policy.requirements[0].source_class == "market_quote"
    with pytest.raises(EvidenceCompilationError, match="outside profile"):
        compile_task_authority(
            get_agent_profile("trading-research"),
            "What is NVDA trading at today?",
            decision,
        )


def test_external_forbidden_conflict_fails_before_agent_execution() -> None:
    decision = classify_evidence(
        "Tell me the latest PostgreSQL release without using the web",
        profile_id="research",
    )
    assert decision.policy.external_access == "forbidden"
    with pytest.raises(EvidenceCompilationError) as caught:
        compile_task_authority(get_agent_profile("research"), "latest", decision)
    assert caught.value.code == "external_evidence_forbidden"


def test_subject_bound_evidence_rejects_wrong_security() -> None:
    nvda = SubjectRef(type="security", canonical_id="NVDA:US", display_name="NVDA")
    tsla = SubjectRef(type="security", canonical_id="TSLA:US", display_name="TSLA")
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="quote",
                source_class="market_quote",
                subject=nvda,
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=60,
            )
        ],
    )
    evidence = evaluate_evidence_set(
        "run-1",
        policy,
        [_receipt(source_class="market_quote", subject=tsla)],
    )
    assert not evidence.passed
    assert evidence.requirements[0].status == "wrong_subject"


def test_evidence_set_rejects_stale_receipt() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="ci",
                source_class="repo_ci_state",
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=300,
            )
        ],
    )
    evidence = evaluate_evidence_set(
        "run-1",
        policy,
        [_receipt(source_class="repo_ci_state", age_seconds=301)],
    )
    assert not evidence.passed
    assert evidence.requirements[0].status == "stale"


def test_evidence_set_enforces_trust_floor() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="filing",
                source_class="company_filing",
                trust_floor="primary",
                acceptable_sources=[
                    EvidenceSourceOption(source_class="company_filing", trust_floor="primary")
                ],
            )
        ],
    )
    evidence = evaluate_evidence_set(
        "run-1",
        policy,
        [_receipt(source_class="company_filing", trust="reputable")],
    )
    assert not evidence.passed
    assert evidence.requirements[0].status == "insufficient_trust"


def test_freshness_policy_is_configurable(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_EVIDENCE_MAX_AGE_REPO_CI_STATE", "42")
    assert freshness_max_age_seconds("repo_ci_state") == 42
    monkeypatch.setenv("OMNIX_AGENT_EVIDENCE_MAX_AGE_REPO_CI_STATE", "0")
    with pytest.raises(EvidenceCompilationError) as caught:
        freshness_max_age_seconds("repo_ci_state")
    assert caught.value.code == "freshness_policy_unsatisfiable"


def test_semantic_adviser_is_used_only_as_structured_advice() -> None:
    advised = EvidenceDecision(
        policy=EvidencePolicy(
            requirement="required",
            requirements=[
                EvidenceRequirement(
                    id="advised",
                    source_class="general_current_web",
                    freshness="current",
                    trust_floor="reputable",
                )
            ],
        ),
        confidence=0.8,
        reason="semantic-current-fact",
        classifier="semantic",
    )
    called: list[tuple[str, str]] = []

    def adviser(task: str, profile: str):
        called.append((task, profile))
        return advised

    decision = classify_evidence(
        "Please look into whether that still holds",
        profile_id="research",
        semantic_adviser=adviser,
    )
    assert called
    assert decision == advised
    compiled = compile_task_authority(
        get_agent_profile("research"),
        "Please look into whether that still holds",
        decision,
    )
    assert compiled.required_external == ("research.web_search",)


def test_broker_receipt_is_bound_to_requirement_subject_and_manifest() -> None:
    decision = classify_evidence(
        "Research NVDA stock news today",
        profile_id="trading-research",
    )
    policy = decision.policy
    receipt = build_evidence_receipt(
        run_id="run-1",
        task_revision_id="rev-1",
        policy=policy,
        capability_id="research.web_search",
        request_input={"query": "NVDA stock news today"},
        result_payload={
            "output": {
                "items": [{"url": "https://example.com/nvda"}],
                "source_manifest_id": "manifest-42",
                "diagnostics": {"provider": "test"},
            }
        },
        error=None,
    )
    assert receipt is not None
    assert receipt.source_class == "market_news"
    assert receipt.subject is not None
    assert receipt.subject.qualifiers["ticker"] == "NVDA"
    assert receipt.source_manifest_id == "manifest-42"


def test_revision_aware_acceptance_uses_latest_effective_policy() -> None:
    original = AgentRunSpec(
        run_id="run-1",
        task="Implement change",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        capabilities=["workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
    )
    revision = TaskRevision(
        run_id="run-1",
        sequence=2,
        user_instruction="Actually just explain the issue",
        effective_objective="Just explain the issue",
        evidence_decision=EvidenceDecision(),
        required_local_capabilities=[],
        required_external_capabilities=[],
        expected_artifacts=[],
        acceptance_checks=[],
    )
    result = evaluate_acceptance(
        original,
        events=[],
        artifacts=[],
        task_revision=revision,
        evidence_set=evaluate_evidence_set("run-1", revision.evidence_decision.policy, []),
    )
    assert result.passed
    assert "successful_test_command" not in result.checks
