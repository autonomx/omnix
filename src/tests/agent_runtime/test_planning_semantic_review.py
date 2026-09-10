from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, TaskRequirement, TaskRevision, WorkspaceSpec
from app.agent_runtime.planning_contracts import (
    ImplementationPlanRevision,
    ImplementationPlanSubmission,
    PlanAuthority,
    PlanItem,
    PlanReviewFinding,
    PlanSemanticReview,
    RequirementPlanCoverage,
)
from app.agent_runtime.planning_review import (
    PLAN_REVIEW_PROTOCOL_VERSION,
    plan_review_system_prompt,
    plan_semantic_digest,
    plan_semantic_review_freshness_failures,
    plan_semantic_review_gate_failures,
    plan_semantic_review_max_rounds,
    plan_semantic_review_required,
    review_plan_semantics_safely,
)


def _spec(tmp_path: Path, *, provider_id: str = "llm:chatgpt_codex") -> AgentRunSpec:
    return AgentRunSpec(
        run_id="run-plan-review",
        task=(
            "The left side panel when minimized stays the same size as before being minimized. "
            "It should be like the right side bar when minimized."
        ),
        objective="Make the minimized left sidebar collapse like the minimized right sidebar.",
        profile="coding",
        model=ModelRef(
            provider_id=provider_id,
            model_id=("llm:chatgpt_codex:gpt-5.6-luna" if provider_id != "test" else "model"),
            reasoning_effort="high" if provider_id != "test" else None,
        ),
        capabilities=["workspace.read", "workspace.edit", "workspace.test"],
        expected_artifacts=["diff"],
        workspace=WorkspaceSpec(root=str(tmp_path)),
    )


def _revision() -> TaskRevision:
    instruction = (
        "The left side panel when minimized stays the same size as before being minimized. "
        "It should be like the right side bar when minimized."
    )
    return TaskRevision(
        revision_id="revision-plan-review",
        run_id="run-plan-review",
        sequence=1,
        user_instruction=instruction,
        effective_objective="Make the minimized left sidebar collapse like the minimized right sidebar.",
        requirements=[
            TaskRequirement(
                id="R-sidebar-collapse",
                description="The minimized left sidebar must collapse to the compact behavior used by the right sidebar.",
            )
        ],
    )


def _submission(*, inverted: bool) -> ImplementationPlanSubmission:
    intent = (
        "Preserve the expanded left-sidebar width while minimized, matching the right sidebar."
        if inverted
        else "Collapse the left sidebar to its minimized width, matching the right sidebar's compact state."
    )
    return ImplementationPlanSubmission(
        requirement_coverage=[
            RequirementPlanCoverage(
                requirement_id="R-sidebar-collapse",
                plan_item_ids=["sidebar-layout"],
            )
        ],
        changes=[
            PlanItem(
                id="sidebar-layout",
                intent=intent,
                paths=["src/apps/web/src/features/chatbot/ChatSidebar.tsx"],
                requirement_ids=["R-sidebar-collapse"],
                allowed_effects=["mutate"],
            )
        ],
    )


def _authority() -> PlanAuthority:
    return PlanAuthority(
        engineering_contract_digest="engineering",
        planning_baseline_id="baseline",
        inspection_evidence_digest="evidence",
        repository_guidance_digest="guidance",
    )


def _review(submission: ImplementationPlanSubmission, *, blocking: bool) -> PlanSemanticReview:
    findings = (
        [
            PlanReviewFinding(
                code="objective_reversal",
                severity="blocking",
                problem="The plan preserves the reported bug instead of applying the requested minimized behavior.",
                user_requirement="Left sidebar should behave like the minimized right sidebar.",
                plan_statement="Preserve the expanded left-sidebar width while minimized.",
                recommendation="Collapse the minimized left sidebar instead of preserving expanded width.",
            )
        ]
        if blocking
        else [
            PlanReviewFinding(
                code="consider_shared_constant",
                severity="suggestion",
                problem="A shared compact-width constant could reduce future drift.",
            )
        ]
    )
    return PlanSemanticReview(
        review_round=1,
        reviewer_session_id="fresh-reviewer-session",
        protocol_version=PLAN_REVIEW_PROTOCOL_VERSION,
        task_revision_id="revision-plan-review",
        plan_digest=plan_semantic_digest(submission),
        engineering_contract_digest="engineering",
        inspection_evidence_digest="evidence",
        repository_guidance_digest="guidance",
        model_provider_id="llm:chatgpt_codex",
        model_id="gpt-5.6-luna",
        reasoning_effort="high",
        verdict="revise" if blocking else "approve",
        objective_fidelity=not blocking,
        requirement_coverage=True,
        assumption_quality=True,
        architecture_fit=True,
        validation_quality=True,
        findings=findings,
    )


class _BlockingReviewer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def review(self, **kwargs) -> PlanSemanticReview:
        self.calls.append(dict(kwargs))
        submission = kwargs["submission"]
        authority = kwargs["authority"]
        revision = kwargs["revision"]
        return PlanSemanticReview(
            review_round=int(kwargs["review_round"]),
            reviewer_session_id="reviewer-b",
            protocol_version=PLAN_REVIEW_PROTOCOL_VERSION,
            task_revision_id=revision.revision_id,
            plan_digest=plan_semantic_digest(submission),
            engineering_contract_digest=authority.engineering_contract_digest,
            inspection_evidence_digest=authority.inspection_evidence_digest,
            repository_guidance_digest=authority.repository_guidance_digest,
            model_provider_id="test-reviewer",
            model_id="review-model",
            verdict="revise",
            objective_fidelity=False,
            requirement_coverage=True,
            assumption_quality=True,
            architecture_fit=True,
            validation_quality=True,
            findings=[
                PlanReviewFinding(
                    code="objective_reversal",
                    severity="blocking",
                    problem="Current buggy behavior was inverted into desired behavior.",
                    user_requirement=revision.user_instruction,
                    plan_statement=submission.changes[0].intent,
                )
            ],
        )


def test_inverted_sidebar_plan_is_blocked_when_independent_reviewer_flags_reversal(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    revision = _revision()
    submission = _submission(inverted=True)
    reviewer = _BlockingReviewer()

    review = review_plan_semantics_safely(
        reviewer,
        spec=spec,
        revision=revision,
        submission=submission,
        authority=_authority(),
        evidence=[],
        candidates=[],
        review_round=1,
        final_round=False,
    )

    assert reviewer.calls
    assert review.verdict == "revise"
    assert not review.objective_fidelity
    assert plan_semantic_review_gate_failures(review, required=True) == [
        "plan_semantic_review_blocking:objective_reversal"
    ]


def test_nonblocking_review_suggestion_does_not_prevent_plan_approval() -> None:
    submission = _submission(inverted=False)
    review = _review(submission, blocking=False)

    assert review.verdict == "approve"
    assert plan_semantic_review_gate_failures(review, required=True) == []


def test_review_contract_cannot_approve_with_blocking_finding() -> None:
    submission = _submission(inverted=True)
    payload = _review(submission, blocking=True).model_dump(mode="python")
    payload["verdict"] = "approve"

    with pytest.raises(ValidationError):
        PlanSemanticReview.model_validate(payload)


def test_review_is_bound_to_exact_plan_digest_and_protocol() -> None:
    submission = _submission(inverted=False)
    review = _review(submission, blocking=False)
    plan = ImplementationPlanRevision(
        run_id="run-plan-review",
        task_revision_id="revision-plan-review",
        sequence=1,
        status="approved",
        authority=_authority(),
        requirement_coverage=submission.requirement_coverage,
        changes=submission.changes,
        semantic_review=review,
    )

    assert plan_semantic_review_freshness_failures(plan, required=True) == []

    changed = plan.model_copy(
        update={
            "changes": [
                plan.changes[0].model_copy(update={"intent": "Preserve full width after all."})
            ]
        }
    )
    assert "plan_semantic_review_plan_digest_stale" in plan_semantic_review_freshness_failures(
        changed,
        required=True,
    )

    stale_review = review.model_copy(update={"protocol_version": "older-review-protocol"})
    stale = plan.model_copy(update={"semantic_review": stale_review})
    assert "plan_semantic_review_protocol_stale" in plan_semantic_review_freshness_failures(
        stale,
        required=True,
    )


def test_unavailable_reviewer_fails_closed_without_consuming_planner_reasoning(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    revision = _revision()
    submission = _submission(inverted=False)

    review = review_plan_semantics_safely(
        None,
        spec=spec,
        revision=revision,
        submission=submission,
        authority=_authority(),
        evidence=[],
        candidates=[],
        review_round=1,
        final_round=False,
    )

    assert review.status == "unavailable"
    assert review.verdict == "revise"
    assert plan_semantic_review_gate_failures(review, required=True) == [
        "plan_semantic_review_unavailable",
        "plan_semantic_review_blocking:reviewer_unavailable",
    ]


def test_auto_mode_requires_review_for_production_provider_but_not_test_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_AGENT_PLAN_REVIEW_MODE", "auto")
    assert plan_semantic_review_required(_spec(tmp_path, provider_id="llm:chatgpt_codex"))
    assert not plan_semantic_review_required(_spec(tmp_path, provider_id="test"))


def test_review_round_limit_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_PLAN_REVIEW_MAX_ROUNDS", "999")
    assert plan_semantic_review_max_rounds() == 5
    monkeypatch.setenv("OMNIX_AGENT_PLAN_REVIEW_MAX_ROUNDS", "3")
    assert plan_semantic_review_max_rounds() == 3


def test_review_prompt_explicitly_guards_current_vs_desired_state_inversion() -> None:
    prompt = plan_review_system_prompt()

    assert "BEFORE/current" in prompt
    assert "AFTER/desired" in prompt
    assert "broken current behavior must not be turned into behavior to preserve" in prompt
    assert "hidden reasoning" in prompt
    assert "Consensus means no blocking findings" in prompt
