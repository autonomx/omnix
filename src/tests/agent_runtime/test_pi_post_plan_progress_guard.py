from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[2] / "app" / "agent_runtime"


def _guard_source() -> str:
    return (ROOT / "pi_guard_extension.ts").read_text(encoding="utf-8")


def _broker_source() -> str:
    return (ROOT / "pi_broker_extension.ts").read_text(encoding="utf-8")


def test_post_plan_progress_guard_is_bound_to_current_approved_plan() -> None:
    source = _guard_source()

    assert "/planning/check" in source
    assert "payload?.passed === true && planRevisionId" in source
    assert "progressPlanRevisionId !== approvedPlanRevisionId" in source
    assert "progressPlanRevisionId = null" in source
    assert "The progress guard is an efficiency policy, not correctness authority." in source
    assert "if (!response.ok) return undefined" in source


def test_post_plan_progress_guard_counts_investigation_not_lifetime_tool_calls() -> None:
    source = _guard_source()

    assert 'const investigationTools = new Set(["read", "grep", "find", "ls"]);' in source
    assert "readOnlyGitCommand" in source
    assert "postPlanInvestigationCalls += 1" in source
    assert "postPlanInvestigationCalls <= postPlanInvestigationLimit" in source
    assert "OMNIX_AGENT_POST_PLAN_INVESTIGATION_LIMIT" in source
    assert '|| "10"' in source
    assert "post-plan progress guard blocked further broad investigation after ${postPlanInvestigationLimit}" in source
    assert "consecutive read/search calls under approved plan ${approvedPlanRevisionId}" in source


def test_post_plan_progress_guard_resets_on_execution_progress() -> None:
    source = _guard_source()

    assert '["edit", "write", "omnix_change_set", "omnix_capability"].includes(toolName)' in source
    assert "isValidationCommand(input.command)" in source
    assert "resetPostPlanProgress();" in source
    assert "Additional reads/searches are allowed again after " in source
    assert "meaningful execution progress or an approved plan revision." in source


def test_post_plan_progress_guard_runs_before_tool_budget_charge() -> None:
    source = _guard_source()

    progress_gate = source.index("const progressRejection = await postPlanProgressRejection")
    budget_gate = source.index("const budgetError = await authorizeTool")
    assert progress_gate < budget_gate
    assert "if (progressRejection) return { block: true, reason: progressRejection };" in source


def test_pi_plan_guidance_transitions_from_approval_to_execution() -> None:
    source = _broker_source()

    assert "Once submit/amend returns approved:true, transition from discovery to execution." in source
    assert "Additional reads/searches should answer a specific unresolved implementation question" in source
    assert "repeated broad inspection that does not change the target, plan, or validation strategy is not progress" in source
