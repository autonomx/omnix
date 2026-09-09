from __future__ import annotations

from app.agent_runtime.contracts import (
    AgentRunSpec,
    ModelRef,
    TaskRequirement,
    TaskRevision,
    ValidationSpec,
)
from app.agent_runtime.planning import plan_gate_failures
from app.agent_runtime.planning_contracts import (
    ImpactCandidate,
    ImplementationPlanSubmission,
    InspectionEvidence,
    PlanImpactDisposition,
    PlanItem,
    PlanValidationIntent,
    RequirementPlanCoverage,
)


def _fixture():
    spec = AgentRunSpec(
        run_id="run-plan-gate",
        task="Update the affected source safely",
        objective="Update the affected source safely",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="test"),
        expected_artifacts=["diff"],
    )
    revision = TaskRevision(
        revision_id="revision-plan-gate",
        run_id=spec.run_id,
        sequence=1,
        user_instruction=spec.task,
        effective_objective=spec.objective,
        requirements=[
            TaskRequirement(id="R1", description="Update the affected source", required=True)
        ],
        validation_plan=[
            ValidationSpec(
                id="V1",
                kind="test",
                description="Run focused tests",
                covers=["R1"],
                required=True,
            )
        ],
        expected_artifacts=["diff"],
    )
    evidence = InspectionEvidence(
        evidence_id="E1",
        run_id=spec.run_id,
        task_revision_id=revision.revision_id,
        kind="exact_literal_match",
        path="src/affected.py",
        query="legacy value",
        observed_result_count=1,
        result_digest="digest",
    )
    candidate = ImpactCandidate(
        candidate_id="C1",
        run_id=spec.run_id,
        task_revision_id=revision.revision_id,
        path="src/affected.py",
        relation="exact_literal_in_source",
        query="legacy value",
        evidence_ids=[evidence.evidence_id],
        evidence_confidence="high",
        impact_likelihood="high",
        semantic_uncertainty="medium",
        relation_strength="high",
    )
    return spec, revision, evidence, candidate


def _submission(*, path: str = "src/affected.py") -> ImplementationPlanSubmission:
    return ImplementationPlanSubmission(
        requirement_coverage=[
            RequirementPlanCoverage(
                requirement_id="R1",
                plan_item_ids=["change-1"],
                validation_ids=["V1"],
            )
        ],
        impacts=[
            PlanImpactDisposition(
                candidate_id="C1",
                disposition="modify",
                evidence_ids=["E1"],
            )
        ],
        changes=[
            PlanItem(
                id="change-1",
                intent="Update the affected source",
                paths=[path],
                requirement_ids=["R1"],
                candidate_ids=["C1"],
                validation_ids=["V1"],
            )
        ],
    )


def test_valid_modify_plan_has_cross_object_closure() -> None:
    spec, revision, evidence, candidate = _fixture()
    assert plan_gate_failures(
        spec,
        revision,
        _submission(),
        [candidate],
        [evidence],
    ) == []


def test_modify_disposition_must_link_to_plan_item_and_candidate_path() -> None:
    spec, revision, evidence, candidate = _fixture()
    submission = _submission()
    unlinked = submission.model_copy(
        update={
            "changes": [submission.changes[0].model_copy(update={"candidate_ids": []})]
        }
    )
    failures = plan_gate_failures(spec, revision, unlinked, [candidate], [evidence])
    assert "impact_modify_not_linked_to_plan_item:C1" in failures

    wrong_path = _submission(path="src/other.py")
    failures = plan_gate_failures(spec, revision, wrong_path, [candidate], [evidence])
    assert "impact_modify_path_not_planned:C1:src/affected.py" in failures


def test_semantic_waiver_is_not_server_authored_execution_authority() -> None:
    spec, revision, evidence, candidate = _fixture()
    submission = _submission().model_copy(
        update={
            "impacts": [
                PlanImpactDisposition(
                    candidate_id="C1",
                    disposition="verify",
                    evidence_ids=["E1"],
                    invariant="Reviewer/Pi may reason about this invariant.",
                )
            ]
        }
    )
    failures = plan_gate_failures(spec, revision, submission, [candidate], [evidence])
    assert not [item for item in failures if "critic" in item or "waiver" in item]


def test_plan_gate_rejects_authoritative_validation_shadowing() -> None:
    spec, revision, evidence, candidate = _fixture()
    submission = _submission().model_copy(
        update={
            "validations": [
                PlanValidationIntent(
                    id="V1",
                    kind="repository_invariant",
                    requirement_ids=["R1"],
                    invariant="Replace the authoritative test contract.",
                )
            ]
        }
    )
    failures = plan_gate_failures(spec, revision, submission, [candidate], [evidence])
    assert "plan_validation_shadows_authoritative:V1" in failures


def test_plan_gate_rejects_blanket_workspace_mutation_paths() -> None:
    spec, revision, evidence, candidate = _fixture()
    failures = plan_gate_failures(
        spec,
        revision,
        _submission(path="**"),
        [candidate],
        [evidence],
    )
    assert "plan_path_too_broad:change-1:**" in failures
