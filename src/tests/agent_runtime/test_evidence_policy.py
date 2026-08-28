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
    WorkspaceSpec,
    ModelRef,
    SubjectRef,
    TaskRevision,
)
from app.agent_runtime.evidence import (
    DEFAULT_FRESHNESS_SECONDS,
    EvidenceCompilationError,
    build_evidence_receipt,
    classify_evidence,
    compile_evidence,
    compile_task_authority,
    evaluate_evidence_set,
    fallback_capabilities_for_requirement,
    freshness_max_age_seconds,
    resolve_evidence_call,
    resolve_request_mode,
    validate_required_evidence_capabilities,
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


def test_market_quote_compiles_to_read_only_authoritative_market_capability() -> None:
    decision = classify_evidence("What is NVDA trading at today?", profile_id="trading-research")
    assert decision.policy.requirements[0].source_class == "market_quote"
    compiled = compile_task_authority(
        get_agent_profile("trading-research"),
        "What is NVDA trading at today?",
        decision,
    )
    assert compiled.required_external == ("trading.market_quote",)


def test_required_connected_evidence_fails_preflight_when_connection_is_unavailable(monkeypatch) -> None:
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
        validate_required_evidence_capabilities(["trading.market_quote"])
    assert caught.value.code == "required_connection_unavailable"


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



def test_evidence_freshness_uses_provider_source_timestamp() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="quote-source-time",
                source_class="market_quote",
                freshness="current",
                trust_floor="authoritative",
                max_age_seconds=60,
            )
        ],
    )
    receipt = _receipt(source_class="market_quote", trust="authoritative")
    receipt = receipt.model_copy(
        update={
            "freshest_source_at": datetime.now(timezone.utc) - timedelta(seconds=61),
            "observed_at": datetime.now(timezone.utc),
        }
    )
    result = evaluate_evidence_set("run-1", policy, [receipt])
    assert not result.passed
    assert result.requirements[0].status == "stale"



def test_source_fallback_uses_profile_compatible_alternative() -> None:
    requirement = EvidenceRequirement(
        id="repo-fallback",
        source_class="repo_ci_state",
        freshness="current",
        trust_floor="reputable",
        fallback_policy="allow_fallback",
        acceptable_sources=[
            EvidenceSourceOption(
                source_class="general_current_web",
                trust_floor="reputable",
                preference=50,
            )
        ],
    )
    decision = EvidenceDecision(
        policy=EvidencePolicy(requirement="required", requirements=[requirement]),
        confidence=0.8,
        reason="test",
    )
    compiled = compile_task_authority(
        get_agent_profile("research"),
        "check status",
        decision,
    )
    assert compiled.required_external == ("research.web_search",)


def test_fail_closed_source_does_not_use_fallback() -> None:
    requirement = EvidenceRequirement(
        id="repo-no-fallback",
        source_class="repo_ci_state",
        freshness="current",
        trust_floor="reputable",
        fallback_policy="fail_closed",
        acceptable_sources=[
            EvidenceSourceOption(
                source_class="general_current_web",
                trust_floor="reputable",
                preference=50,
            )
        ],
    )
    decision = EvidenceDecision(
        policy=EvidencePolicy(requirement="required", requirements=[requirement]),
        confidence=0.8,
        reason="test",
    )
    with pytest.raises(EvidenceCompilationError) as caught:
        compile_task_authority(get_agent_profile("research"), "check status", decision)
    assert caught.value.code == "required_source_outside_profile_ceiling"


def test_repository_evidence_subject_is_bound_to_immutable_commit(monkeypatch, tmp_path) -> None:
    from app.agent_runtime.service import AgentRunService

    requirement = EvidenceRequirement(
        id="ci",
        source_class="repo_ci_state",
        freshness="current",
        trust_floor="authoritative",
    )
    policy = EvidencePolicy(requirement="required", requirements=[requirement])
    workspace = WorkspaceSpec(
        root=str(tmp_path),
        repository=str(tmp_path),
        base_ref="main",
    )
    monkeypatch.setattr(
        AgentRunService,
        "_resolve_repository_commit",
        staticmethod(lambda _repository, _ref: "abc123"),
    )
    bound = AgentRunService._bind_repository_evidence_policy(
        policy,
        workspace=workspace,
        repository_name="autonomx/omnix",
    )
    subject = bound.requirements[0].subject
    assert subject is not None
    assert subject.canonical_id == "autonomx/omnix"
    assert subject.qualifiers["requested_ref"] == "main"
    assert subject.qualifiers["resolved_commit"] == "abc123"



def test_revision_filters_do_not_reuse_prior_tool_or_evidence_rows() -> None:
    from app.agent_runtime.contracts import AgentArtifact, AgentEvent, TaskRevision
    from app.agent_runtime.service import AgentRunService

    revision = TaskRevision(
        run_id="run-1",
        sequence=2,
        user_instruction="new task",
        effective_objective="new task",
    )
    prior_event = AgentEvent(
        run_id="run-1",
        event_type="tool.completed",
        payload={"tool_call_id": "old", "task_revision_id": "rev-old"},
    )
    current_event = AgentEvent(
        run_id="run-1",
        event_type="tool.completed",
        payload={"tool_call_id": "new", "task_revision_id": revision.revision_id},
    )
    assert AgentRunService._events_for_revision(
        [prior_event, current_event],
        revision,
    ) == [current_event]

    prior_artifact = AgentArtifact(
        run_id="run-1",
        kind="diff",
        name="old.diff",
        metadata={"task_revision_id": "rev-old"},
    )
    current_artifact = AgentArtifact(
        run_id="run-1",
        kind="diff",
        name="new.diff",
        metadata={"task_revision_id": revision.revision_id},
    )
    assert AgentRunService._artifacts_for_revision(
        [prior_artifact, current_artifact],
        revision,
    ) == [current_artifact]

    prior_receipt = _receipt(source_class="general_current_web")
    prior_receipt = prior_receipt.model_copy(update={"task_revision_id": "rev-old"})
    current_receipt = _receipt(source_class="general_current_web")
    current_receipt = current_receipt.model_copy(update={"task_revision_id": revision.revision_id})
    assert AgentRunService._receipts_for_revision(
        [prior_receipt, current_receipt],
        revision,
    ) == [current_receipt]



def test_required_subject_qualifiers_must_be_present_on_receipt() -> None:
    from app.agent_runtime.evidence import subject_matches

    required = SubjectRef(
        type="repository_ref",
        canonical_id="autonomx/omnix",
        qualifiers={"resolved_commit": "abc123"},
    )
    broad = SubjectRef(
        type="repository_ref",
        canonical_id="autonomx/omnix",
        qualifiers={},
    )
    assert subject_matches(required, broad) is False


def test_generic_equity_ticker_subject_is_canonicalized() -> None:
    decision = classify_evidence(
        "What is AAPL trading at today?",
        profile_id="trading-research",
    )
    requirement = decision.policy.requirements[0]
    assert requirement.source_class == "market_quote"
    assert requirement.subject is not None
    assert requirement.subject.qualifiers["ticker"] == "AAPL"


def test_mixed_web_results_cannot_inherit_primary_filing_trust() -> None:
    receipt = build_evidence_receipt(
        run_id="run-1",
        task_revision_id="rev-1",
        policy=EvidencePolicy(
            requirement="required",
            requirements=[
                EvidenceRequirement(
                    id="filing",
                    source_class="company_filing",
                    trust_floor="primary",
                    subject=SubjectRef(
                        type="security",
                        canonical_id="AAPL:US",
                        display_name="AAPL",
                        qualifiers={"ticker": "AAPL"},
                    ),
                    acceptable_sources=[
                        EvidenceSourceOption(
                            source_class="company_filing",
                            trust_floor="primary",
                            preference=0,
                        )
                    ],
                )
            ],
        ),
        capability_id="research.web_search",
        request_input={"query": "AAPL SEC filing"},
        result_payload={
            "output": {
                "items": [
                    {"url": "https://www.sec.gov/example"},
                    {"url": "https://example.com/summary"},
                ],
                "diagnostics": {"provider": "test"},
            }
        },
        error=None,
    )
    assert receipt is not None
    assert receipt.trust_level == "reputable"



def test_semantic_adviser_cannot_override_no_external_constraint() -> None:
    advised = EvidenceDecision(
        policy=EvidencePolicy(requirement="none", external_access="allowed"),
        confidence=0.9,
        reason="semantic",
        classifier="semantic",
    )
    decision = classify_evidence(
        "Investigate my inbox without using the web",
        profile_id="personal-assistant",
        semantic_adviser=lambda _task, _profile: advised,
    )
    assert decision.policy.external_access == "forbidden"


def test_low_confidence_semantic_none_gets_conservative_current_floor() -> None:
    advised = EvidenceDecision(
        policy=EvidencePolicy(requirement="none"),
        confidence=0.4,
        reason="uncertain",
        classifier="semantic",
    )
    decision = classify_evidence(
        "Investigate GME momentum",
        profile_id="trading-research",
        semantic_adviser=lambda _task, _profile: advised,
    )
    assert decision.policy.requirement == "required"
    assert decision.policy.requirements[0].source_class == "market_news"
    assert decision.classifier == "conservative"


def test_as_of_date_requires_source_timestamp_and_enforces_boundary() -> None:
    as_of = datetime(2026, 8, 1, tzinfo=timezone.utc)
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="historical",
                source_class="general_current_web",
                freshness="as_of_date",
                as_of_date=as_of,
                max_age_seconds=86400,
            )
        ],
    )
    no_source_time = _receipt(source_class="general_current_web")
    assert not evaluate_evidence_set("run-1", policy, [no_source_time], now=as_of).passed

    valid = no_source_time.model_copy(
        update={"freshest_source_at": as_of - timedelta(hours=1)}
    )
    assert evaluate_evidence_set("run-1", policy, [valid], now=as_of).passed

    future = no_source_time.model_copy(
        update={"freshest_source_at": as_of + timedelta(hours=1)}
    )
    assert not evaluate_evidence_set("run-1", policy, [future], now=as_of).passed


def test_current_semantic_source_without_freshness_policy_fails_compilation(monkeypatch) -> None:
    monkeypatch.setitem(DEFAULT_FRESHNESS_SECONDS, "general_current_web", None)
    requirement = EvidenceRequirement(
        id="current-no-age",
        source_class="general_current_web",
        freshness="current",
        max_age_seconds=None,
    )
    decision = EvidenceDecision(
        policy=EvidencePolicy(requirement="required", requirements=[requirement])
    )
    with pytest.raises(EvidenceCompilationError) as caught:
        compile_evidence(get_agent_profile("research"), decision)
    assert caught.value.code == "freshness_policy_unsatisfiable"



def test_compound_market_request_compiles_multiple_evidence_requirements() -> None:
    decision = classify_evidence(
        "Give me NVDA's current quote, today's catalysts, and latest SEC filing",
        profile_id="trading-research",
    )
    assert decision.policy.requirement == "required"
    assert [row.source_class for row in decision.policy.requirements] == [
        "market_quote",
        "company_filing",
        "market_news",
    ]
    compiled = compile_evidence(get_agent_profile("trading-research"), decision)
    assert set(compiled.required_external) == {
        "trading.market_quote",
        "research.web_search",
    }


def test_shared_web_transport_binds_call_to_specific_requirement() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="news",
                source_class="market_news",
                subject=SubjectRef(
                    type="security",
                    canonical_id="NVDA:US",
                    qualifiers={"ticker": "NVDA"},
                ),
                freshness="current",
                max_age_seconds=3600,
                trust_floor="reputable",
            ),
            EvidenceRequirement(
                id="filing",
                source_class="company_filing",
                subject=SubjectRef(
                    type="security",
                    canonical_id="NVDA:US",
                    qualifiers={"ticker": "NVDA"},
                ),
                freshness="current",
                max_age_seconds=86400,
                trust_floor="primary",
            ),
        ],
    )
    requirement, source = resolve_evidence_call(
        policy,
        "research.web_search",
        {"query": "NVDA latest SEC filing 10-Q"},
    )
    assert requirement is not None
    assert requirement.id == "filing"
    assert source == "company_filing"

    requirement, source = resolve_evidence_call(
        policy,
        "research.web_search",
        {"query": "NVDA catalysts and headlines today"},
    )
    assert requirement is not None
    assert requirement.id == "news"
    assert source == "market_news"


def test_allow_fallback_compiles_all_bounded_alternative_capabilities() -> None:
    requirement = EvidenceRequirement(
        id="fallback",
        source_class="general_current_web",
        trust_floor="reputable",
        acceptable_sources=[
            EvidenceSourceOption(
                source_class="repo_contents",
                trust_floor="reputable",
                preference=100,
            )
        ],
        fallback_policy="allow_fallback",
    )
    decision = EvidenceDecision(
        policy=EvidencePolicy(requirement="required", requirements=[requirement])
    )
    compiled = compile_evidence(get_agent_profile("research"), decision)
    assert compiled.external_groups == (("research.web_search", "github.read_repo"),)
    assert set(compiled.required_external) == {
        "research.web_search",
        "github.read_repo",
    }
    assert fallback_capabilities_for_requirement(
        requirement,
        current_capability="research.web_search",
        issued_capabilities=compiled.required_external,
    ) == ("github.read_repo",)


def test_receipt_uses_explicit_requirement_source_binding() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            EvidenceRequirement(
                id="news",
                source_class="market_news",
                trust_floor="reputable",
            ),
            EvidenceRequirement(
                id="filing",
                source_class="company_filing",
                trust_floor="primary",
            ),
        ],
    )
    receipt = build_evidence_receipt(
        run_id="run-1",
        task_revision_id="rev-1",
        policy=policy,
        capability_id="research.web_search",
        request_input={"query": "NVDA 10-Q SEC filing"},
        result_payload={
            "output": {
                "items": [{"url": "https://www.sec.gov/example"}],
                "diagnostics": {"provider": "test"},
            }
        },
        error=None,
        requirement_id="filing",
        source_class_hint="company_filing",
    )
    assert receipt is not None
    assert receipt.source_class == "company_filing"
    assert receipt.trust_level == "primary"
