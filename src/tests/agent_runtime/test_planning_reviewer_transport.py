from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent_runtime import planning_review
from app.agent_runtime.budget import AgentBudgetError
from app.agent_runtime.planning_contracts import (
    ImplementationPlanSubmission,
    PlanAuthority,
)
from app.providers.structured.errors import StructuredOutputExhausted


class _FailingReviewer:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def review(self, **_kwargs):
        self.calls += 1
        raise self.error


def _spec():
    return SimpleNamespace(
        run_id="run-review-transport",
        model=SimpleNamespace(
            provider_id="llm:any-provider",
            model_id="any-model",
            reasoning_effort="high",
        ),
    )


def _revision():
    return SimpleNamespace(revision_id="revision-review-transport")


def _authority() -> PlanAuthority:
    return PlanAuthority(
        engineering_contract_digest="engineering",
        planning_baseline_id="baseline",
        inspection_evidence_digest="evidence",
        repository_guidance_digest="guidance",
    )


def test_plan_review_timeout_default_is_provider_neutral(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_PLAN_REVIEW_TIMEOUT_SECONDS", raising=False)
    assert planning_review.plan_semantic_review_timeout_seconds() == 180.0

    monkeypatch.setenv("OMNIX_AGENT_PLAN_REVIEW_TIMEOUT_SECONDS", "240")
    assert planning_review.plan_semantic_review_timeout_seconds() == 240.0

    monkeypatch.setenv("OMNIX_AGENT_PLAN_REVIEW_TIMEOUT_SECONDS", "900")
    assert planning_review.plan_semantic_review_timeout_seconds() == 300.0


def test_plan_review_transport_attempts_are_bounded_separately(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_AGENT_PLAN_REVIEW_TRANSPORT_ATTEMPTS", raising=False)
    assert planning_review.plan_semantic_review_transport_attempts() == 2

    monkeypatch.setenv("OMNIX_AGENT_PLAN_REVIEW_TRANSPORT_ATTEMPTS", "3")
    assert planning_review.plan_semantic_review_transport_attempts() == 3

    monkeypatch.setenv("OMNIX_AGENT_PLAN_REVIEW_TRANSPORT_ATTEMPTS", "99")
    assert planning_review.plan_semantic_review_transport_attempts() == 3


def test_reviewer_transport_failure_retries_same_plan_then_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_PLAN_REVIEW_TRANSPORT_ATTEMPTS", "2")
    root = TimeoutError("review deadline exceeded")
    reviewer = _FailingReviewer(
        StructuredOutputExhausted(
            "structured review failed",
            last_error=root,
        )
    )
    submission = ImplementationPlanSubmission()

    review = planning_review.review_plan_semantics_safely(
        reviewer,
        spec=_spec(),
        revision=_revision(),
        submission=submission,
        authority=_authority(),
        evidence=[],
        candidates=[],
        review_round=1,
        final_round=False,
    )

    assert reviewer.calls == 2
    assert review.status == "unavailable"
    assert review.verdict == "revise"
    assert review.plan_digest == planning_review.plan_semantic_digest(submission)
    assert "reviewer transport attempts exhausted (2)" in (review.failure_reason or "")
    assert "TimeoutError: review deadline exceeded" in (review.failure_reason or "")
    assert review.findings[0].code == "reviewer_unavailable"


def test_reviewer_budget_failure_is_not_retried_as_transport(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_AGENT_PLAN_REVIEW_TRANSPORT_ATTEMPTS", "3")
    reviewer = _FailingReviewer(
        StructuredOutputExhausted(
            "structured review failed",
            last_error=AgentBudgetError("budget_max_steps_exceeded"),
        )
    )

    with pytest.raises(AgentBudgetError, match="budget_max_steps_exceeded"):
        planning_review.review_plan_semantics_safely(
            reviewer,
            spec=_spec(),
            revision=_revision(),
            submission=ImplementationPlanSubmission(),
            authority=_authority(),
            evidence=[],
            candidates=[],
            review_round=1,
            final_round=False,
        )

    assert reviewer.calls == 1


def test_durable_block_and_broker_preflight_prevent_pi_resubmission_loop() -> None:
    root = Path(__file__).parents[2] / "app" / "agent_runtime"
    repository_source = (root / "planning_repository.py").read_text(encoding="utf-8")
    broker_source = (root / "pi_broker_extension.ts").read_text(encoding="utf-8")

    assert "plan.semantic_review.status == \"unavailable\"" in repository_source
    assert "self.mark_state_blocked(" in repository_source
    assert "omnix_agent_planning_state.status = 'blocked'" in repository_source
    assert "omnix_agent_planning_state.task_revision_id = EXCLUDED.task_revision_id" in repository_source

    assert "planningReviewerTransportBlock" in broker_source
    assert 'String(state?.status || "") !== "blocked"' in broker_source
    assert "plan_semantic_review_transport_exhausted" in broker_source
    assert "Do not resubmit/amend the same plan" in broker_source
