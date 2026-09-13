from __future__ import annotations

from app.agent_runtime.contracts import TaskRevision
from app.agent_runtime.planning import classify_operation_effect, operation_plan_failures
from app.agent_runtime.planning_api import (
    _merge_plan_delta,
    _planning_state_should_stale,
    _planning_state_status_after_submission,
)
from app.agent_runtime.planning_contracts import (
    ImplementationPlanRevision,
    ImplementationPlanSubmission,
    PlanAuthority,
    PlanImpactDisposition,
    PlanItem,
    PlanValidationIntent,
    RequirementPlanCoverage,
)


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="revision-plan",
        run_id="run-plan",
        sequence=1,
        user_instruction="Update the implementation",
        effective_objective="Update the implementation",
    )


def test_read_and_validation_do_not_require_an_approved_plan() -> None:
    revision = _revision()

    assert operation_plan_failures(None, revision, effect="read") == []
    assert operation_plan_failures(None, revision, effect="validate") == []
    assert operation_plan_failures(None, revision, effect="mutate", target_path="src/example.py") == []
    assert operation_plan_failures(None, revision, effect="mutate", target_path="package-lock.json") == ["approved_plan_missing"]
    assert operation_plan_failures(None, revision, effect="unknown") == ["approved_plan_missing"]


def test_npm_prefix_dependency_commands_are_mutations_not_validation() -> None:
    assert classify_operation_effect(
        "bash",
        command="npm --prefix src/apps/web install",
    ) == "mutate"
    assert classify_operation_effect(
        "powershell",
        command="npm.cmd --prefix src/apps/web update react",
    ) == "mutate"
    assert classify_operation_effect(
        "bash",
        command="npm --prefix src/apps/web uninstall react",
    ) == "mutate"


def test_npm_prefix_known_checks_remain_validation_and_unknown_scripts_fail_closed() -> None:
    assert classify_operation_effect(
        "bash",
        command="npm --prefix src/apps/web run test -- --runInBand",
    ) == "validate"
    assert classify_operation_effect(
        "bash",
        command="npm --prefix src/apps/web run test:e2e -- --project chromium",
    ) == "validate"
    assert classify_operation_effect(
        "bash",
        command="npm run test:unit",
    ) == "validate"
    assert classify_operation_effect(
        "bash",
        command="npm --prefix src/apps/web run build:ci",
    ) == "validate"
    assert classify_operation_effect(
        "powershell",
        command="npm.cmd --prefix src/apps/web run typecheck:strict",
    ) == "validate"
    assert classify_operation_effect(
        "bash",
        command="npm --prefix src/apps/web run generate-client",
    ) == "mutate"
    assert classify_operation_effect(
        "bash",
        command="npm --prefix src/apps/web run custom-script",
    ) == "unknown"


def test_attempted_off_plan_mutation_does_not_stale_valid_plan_authority() -> None:
    assert not _planning_state_should_stale([
        "mutation_not_in_plan:src/unplanned.py",
        "mutate_command_not_in_plan",
    ])
    assert not _planning_state_should_stale(["repair_requires_plan_delta"])


def test_actual_authority_drift_stales_plan_state() -> None:
    for reason in (
        "plan_task_revision_stale",
        "plan_engineering_contract_stale",
        "plan_inspection_evidence_stale",
        "plan_repository_guidance_stale",
        "planning_state_task_revision_stale",
        "planning_active_plan_identity_mismatch",
        "planning_base_commit_changed",
        "preexisting_dirty_path_modified:src/preexisting.py",
    ):
        assert _planning_state_should_stale([reason])


def test_rejected_amendment_does_not_revoke_existing_active_plan() -> None:
    assert _planning_state_status_after_submission("rejected", "approved-plan-1") == "approved"
    assert _planning_state_status_after_submission("rejected", None) == "rejected"
    assert _planning_state_status_after_submission("approved", "approved-plan-2") == "approved"


def test_plan_delta_preserves_prior_authority_and_refines_shared_items() -> None:
    previous = ImplementationPlanRevision(
        plan_revision_id="plan-1",
        run_id="run-plan",
        task_revision_id="revision-plan",
        sequence=1,
        status="approved",
        mode="enforce",
        authority=PlanAuthority(
            engineering_contract_digest="engineering",
            planning_baseline_id="baseline",
            inspection_evidence_digest="evidence",
        ),
        planning_lenses=["regression"],
        requirement_coverage=[
            RequirementPlanCoverage(
                requirement_id="R1",
                plan_item_ids=["change"],
                validation_ids=["V1"],
            )
        ],
        impacts=[
            PlanImpactDisposition(
                candidate_id="C1",
                disposition="verify",
                invariant="Verify the original surface.",
            )
        ],
        changes=[
            PlanItem(
                id="change",
                intent="Initial implementation",
                paths=["src/a.py"],
                requirement_ids=["R1"],
                candidate_ids=["C1"],
                validation_ids=["V1"],
                allowed_effects=["mutate"],
                command_hints=["python old-tool"],
            )
        ],
        validations=[
            PlanValidationIntent(
                id="V1",
                kind="test",
                requirement_ids=["R1"],
                command_hint="pytest tests/test_a.py",
            )
        ],
        assumptions=["original assumption"],
    )
    delta = ImplementationPlanSubmission(
        planning_lenses=["api_contract"],
        requirement_coverage=[
            RequirementPlanCoverage(
                requirement_id="R1",
                plan_item_ids=["change"],
                validation_ids=["V2"],
            )
        ],
        impacts=[
            PlanImpactDisposition(candidate_id="C1", disposition="modify"),
            PlanImpactDisposition(candidate_id="C2", disposition="modify"),
        ],
        changes=[
            PlanItem(
                id="change",
                intent="Repair newly discovered impact",
                paths=["src/b.py"],
                candidate_ids=["C2"],
                validation_ids=["V2"],
                allowed_effects=["unknown"],
                command_hints=["custom-generator"],
            )
        ],
        validations=[
            PlanValidationIntent(
                id="V2",
                kind="repository_invariant",
                requirement_ids=["R1"],
                invariant="No residual references remain.",
            )
        ],
        assumptions=["repair assumption"],
    )

    merged = _merge_plan_delta(previous, delta)

    assert merged.previous_plan_revision_id == "plan-1"
    assert merged.planning_lenses == ["regression", "api_contract"]
    assert merged.assumptions == ["original assumption", "repair assumption"]
    assert [(item.candidate_id, item.disposition) for item in merged.impacts] == [
        ("C1", "modify"),
        ("C2", "modify"),
    ]
    assert len(merged.changes) == 1
    assert merged.changes[0].paths == ["src/a.py", "src/b.py"]
    assert merged.changes[0].candidate_ids == ["C1", "C2"]
    assert merged.changes[0].validation_ids == ["V1", "V2"]
    assert merged.changes[0].allowed_effects == ["mutate", "unknown"]
    assert merged.changes[0].command_hints == ["python old-tool", "custom-generator"]
    assert merged.requirement_coverage[0].validation_ids == ["V1", "V2"]
    assert [item.id for item in merged.validations] == ["V1", "V2"]
