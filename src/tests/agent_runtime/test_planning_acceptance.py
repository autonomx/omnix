from __future__ import annotations

from app.agent_runtime.planning_acceptance import PlanningAcceptanceAssessment


def test_shadow_planning_failures_are_observable_but_do_not_block_acceptance() -> None:
    assessment = PlanningAcceptanceAssessment(
        mode="shadow",
        plan_revision_id="plan-1",
        failures=("unplanned_modified_path:src/example.py",),
    )

    assert assessment.would_block
    assert not assessment.blocks_acceptance
    assert not assessment.fail_closed


def test_enforce_hard_conformance_failure_blocks_but_can_remain_repairable() -> None:
    assessment = PlanningAcceptanceAssessment(
        mode="enforce",
        plan_revision_id="plan-1",
        failures=("planned_impact_not_modified:candidate-1:src/caller.py",),
        hard_gate_required=True,
    )

    assert assessment.would_block
    assert assessment.blocks_acceptance
    assert not assessment.fail_closed


def test_enforce_authority_integrity_failures_fail_closed() -> None:
    for failure in (
        "approved_plan_missing",
        "plan_task_revision_stale",
        "plan_engineering_contract_stale",
        "plan_inspection_evidence_stale",
        "plan_repository_guidance_stale",
        "planning_state_missing",
        "planning_state_task_revision_stale",
        "planning_active_plan_identity_mismatch",
        "planning_base_commit_changed",
        "planning_workspace_unavailable",
        "latest_plan_state_not_approved:stale",
        "unplanned_modified_path:src/unplanned.py",
        "preexisting_dirty_path_modified:src/preexisting.py",
    ):
        assessment = PlanningAcceptanceAssessment(
            mode="enforce",
            plan_revision_id="plan-1",
            failures=(failure,),
            hard_gate_required=True,
        )
        assert assessment.blocks_acceptance
        assert assessment.fail_closed, failure


def test_enforce_clean_plan_does_not_block_acceptance() -> None:
    assessment = PlanningAcceptanceAssessment(
        mode="enforce",
        plan_revision_id="plan-1",
        failures=(),
    )

    assert not assessment.would_block
    assert not assessment.blocks_acceptance
    assert not assessment.fail_closed
