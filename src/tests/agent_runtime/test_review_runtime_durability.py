from __future__ import annotations

from app.agent_runtime.contracts import (
    AgentRunSnapshot,
    AgentRunSpec,
    ModelRef,
    ReviewResult,
    ReviewSnapshot,
    TaskRequirement,
    TaskRevision,
)
from app.agent_runtime.review_runtime import (
    REVIEW_PROTOCOL_VERSION,
    classify_runtime_failure,
    finish_protocol_failed_attempt,
    new_review_attempt,
    retry_slots,
    review_payload_is_protocol_valid,
    reviewer_child_run_id,
)


def _model(model_id: str = "review-model") -> ModelRef:
    return ModelRef(provider_id="test", model_id=model_id, reasoning_effort="high")


def _snapshot(*, state: str = "state-1", revision: str = "revision-1") -> ReviewSnapshot:
    return ReviewSnapshot(
        snapshot_id="snapshot-1",
        run_id="parent-1",
        task_revision_id=revision,
        workspace_state_id=state,
        base_commit_sha="a" * 40,
        patch_checksum=state,
        workspace_root="/tmp/review",
    )


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="revision-1",
        run_id="parent-1",
        sequence=1,
        user_instruction="Fix the bug",
        effective_objective="Fix the bug",
        requirements=[TaskRequirement(id="R1", description="Fix behavior")],
    )


def _failed_child(reason: str) -> AgentRunSnapshot:
    spec = AgentRunSpec(
        run_id="reviewer-1",
        parent_run_id="parent-1",
        task="review",
        objective="review",
        profile="coding-reviewer",
        model=_model(),
        quality_policy="off",
    )
    return AgentRunSnapshot(
        run_id=spec.run_id,
        spec=spec,
        status="failed",
        last_error=reason,
    )


def test_reviewer_identity_changes_for_every_authority_bearing_retry_input() -> None:
    snapshot = _snapshot()
    base = reviewer_child_run_id(
        parent_run_id="parent-1",
        snapshot=snapshot,
        reviewer_slot=0,
        runtime_attempt=1,
        model=_model(),
    )
    assert base != reviewer_child_run_id(
        parent_run_id="parent-1",
        snapshot=snapshot,
        reviewer_slot=0,
        runtime_attempt=2,
        model=_model(),
    )
    assert base != reviewer_child_run_id(
        parent_run_id="parent-1",
        snapshot=snapshot,
        reviewer_slot=1,
        runtime_attempt=1,
        model=_model(),
    )
    assert base != reviewer_child_run_id(
        parent_run_id="parent-1",
        snapshot=snapshot,
        reviewer_slot=0,
        runtime_attempt=1,
        model=_model("other-model"),
    )
    assert base != reviewer_child_run_id(
        parent_run_id="parent-1",
        snapshot=_snapshot(state="state-2"),
        reviewer_slot=0,
        runtime_attempt=1,
        model=_model(),
    )
    assert base != reviewer_child_run_id(
        parent_run_id="parent-1",
        snapshot=snapshot,
        reviewer_slot=0,
        runtime_attempt=1,
        model=_model(),
        protocol_version="review-v3",
    )


def test_local_reviewer_budget_is_retryable_but_parent_global_budget_is_not() -> None:
    local_class, _, local_retryable = classify_runtime_failure(
        _failed_child("agent_run_budget_exhausted: budget_max_steps_exceeded")
    )
    global_class, _, global_retryable = classify_runtime_failure(
        _failed_child("parent_global_budget_exhausted:max_steps")
    )
    rate_class, _, rate_retryable = classify_runtime_failure(
        _failed_child("model_rate_limit_exceeded: HTTP 429")
    )

    assert (local_class, local_retryable) == ("reviewer_local_budget_exhausted", True)
    assert (global_class, global_retryable) == ("parent_global_budget_exhausted", False)
    assert (rate_class, rate_retryable) == ("provider_rate_limited", True)


def test_protocol_failure_retries_same_slot_without_substantive_result() -> None:
    snapshot = _snapshot()
    attempt = new_review_attempt(
        parent_run_id="parent-1",
        reviewer_run_id="reviewer-1",
        snapshot=snapshot,
        reviewer_slot=0,
        runtime_attempt=1,
        model=_model(),
    )
    failed = finish_protocol_failed_attempt(attempt)

    launch, pending, exhausted = retry_slots(
        required_slots=1,
        attempts=[failed],
        results=[],
    )
    assert launch == [0]
    assert pending == []
    assert exhausted == []


def test_only_complete_required_review_schema_is_protocol_valid() -> None:
    revision = _revision()
    valid = (
        '{"verdict":"approve","requirements":[{"requirement_id":"R1",'
        '"status":"satisfied","evidence":"checked"}],"findings":[],'
        '"missing_tests":[],"residual_risks":[]}'
    )
    missing_requirement = (
        '{"verdict":"approve","requirements":[],"findings":[],'
        '"missing_tests":[],"residual_risks":[]}'
    )

    assert review_payload_is_protocol_valid(valid, revision)
    assert not review_payload_is_protocol_valid(missing_requirement, revision)


def test_substantive_result_resolves_slot_and_stops_runtime_retry() -> None:
    snapshot = _snapshot()
    attempt = new_review_attempt(
        parent_run_id="parent-1",
        reviewer_run_id="reviewer-1",
        snapshot=snapshot,
        reviewer_slot=0,
        runtime_attempt=1,
        model=_model(),
        protocol_version=REVIEW_PROTOCOL_VERSION,
    )
    result = ReviewResult(
        run_id="parent-1",
        reviewer_run_id="reviewer-1",
        review_snapshot_id=snapshot.snapshot_id,
        task_revision_id=snapshot.task_revision_id,
        workspace_state_id=snapshot.workspace_state_id,
        verdict="changes_required",
    )

    launch, pending, exhausted = retry_slots(
        required_slots=1,
        attempts=[attempt],
        results=[result],
    )
    assert launch == []
    assert pending == []
    assert exhausted == []
