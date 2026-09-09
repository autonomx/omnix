from __future__ import annotations

from app.agent_runtime.coding_quality import repair_prompt
from app.agent_runtime.contracts import ReviewFinding, ReviewResult, TaskRevision


def test_quality_repair_returns_reasoning_to_pi_and_hard_gates_only_when_required() -> None:
    revision = TaskRevision(
        revision_id="revision-plan-repair",
        run_id="run-plan-repair",
        sequence=1,
        user_instruction="Fix the regression",
        effective_objective="Fix the regression",
    )
    review = ReviewResult(
        run_id=revision.run_id,
        reviewer_run_id="reviewer-1",
        review_snapshot_id="snapshot-1",
        task_revision_id=revision.revision_id,
        workspace_state_id="state-1",
        verdict="changes_required",
        findings=[
            ReviewFinding(
                severity="high",
                category="correctness",
                problem="A caller still uses the old behavior.",
                recommended_fix="Update the caller and regression coverage.",
            )
        ],
    )

    prompt = repair_prompt(revision, review, [], attempt=2)

    assert "continue the normal Pi inspect/reason/edit/test loop" in prompt
    assert "Ordinary in-scope repair edits do not require a PlanDelta" in prompt
    assert "explicitly blocks a consequential operation" in prompt
    assert "omnix_plan" in prompt
    assert "Before ANY repair mutation" not in prompt
