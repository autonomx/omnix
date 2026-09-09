from __future__ import annotations

from pathlib import Path
import subprocess

from app.agent_runtime.coding_quality import compile_task_engineering_contract
from app.agent_runtime.contracts import AgentRunSpec, ModelRef, TaskRevision, WorkspaceSpec
from app.agent_runtime.planning import (
    build_inspection_bundle,
    build_plan_authority,
    capture_planning_baseline,
    classify_operation_effect,
    inspection_evidence_digest,
    operation_plan_failures,
    plan_conformance_failures,
    plan_gate_failures,
)
from app.agent_runtime.planning_contracts import (
    ImplementationPlanRevision,
    ImplementationPlanSubmission,
    PlanImpactDisposition,
    PlanItem,
    PlanValidationIntent,
    RequirementPlanCoverage,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _fixture(tmp_path: Path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    files = {
        "src/apps/web/ChatIdentityModeControl.tsx": 'export const label = "Character settings";\n',
        "src/apps/web/ChatIdentityModeControl.test.tsx": 'expect(label).toBe("Character settings");\n',
        "src/tests/e2e/test_default_llm_agent_ui_flow.py": 'assert "Character settings" in source\n',
        "docs/history.md": 'Previously called "Character settings" in an old screenshot.\n',
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")

    objective = 'Rename "Character settings" to "Character Settings" in the chat UI and update regression coverage.'
    spec = AgentRunSpec(
        run_id="run-plan",
        task=objective,
        objective=objective,
        model=ModelRef(provider_id="test", model_id="test"),
        profile="coding",
        expected_artifacts=["diff"],
        workspace=WorkspaceSpec(root=str(tmp_path), repository=str(tmp_path), worktree=str(tmp_path)),
    )
    requirements, constraints, validation_plan = compile_task_engineering_contract(
        objective, [], profile="coding", mutating=True
    )
    revision = TaskRevision(
        revision_id="revision-plan",
        run_id=spec.run_id,
        sequence=1,
        user_instruction=objective,
        effective_objective=objective,
        requirements=requirements,
        constraints=constraints,
        validation_plan=validation_plan,
        expected_artifacts=["diff"],
    )
    return spec, revision


def _submission(revision: TaskRevision, candidates, *, omit_path: str | None = None):
    validation = PlanValidationIntent(
        id="residual-reference-check",
        kind="repository_invariant",
        requirement_ids=[item.id for item in revision.requirements if item.required],
        invariant="zero unexplained superseded references",
    )
    validation_ids = [validation.id]
    coverage = [
        RequirementPlanCoverage(
            requirement_id=item.id,
            plan_item_ids=["change-copy"],
            validation_ids=validation_ids,
        )
        for item in revision.requirements
        if item.required
    ]
    paths = sorted(
        candidate.path
        for candidate in candidates
        if candidate.impact_likelihood == "high" and candidate.path != omit_path
    )
    changes = [
        PlanItem(
            id="change-copy",
            intent="Update the requested label and every impacted regression expectation.",
            paths=paths,
            requirement_ids=[item.id for item in revision.requirements if item.required],
            candidate_ids=[
                item.candidate_id for item in candidates
                if item.path in paths
            ],
            validation_ids=validation_ids,
        )
    ]
    impacts = [
        PlanImpactDisposition(
            candidate_id=item.candidate_id,
            disposition="modify",
            evidence_ids=list(item.evidence_ids),
        )
        for item in candidates
        if item.path != omit_path and item.impact_likelihood == "high"
    ]
    return ImplementationPlanSubmission(
        planning_lenses=["ui_behavior", "regression"],
        requirement_coverage=coverage,
        impacts=impacts,
        changes=changes,
        validations=[validation],
    )


def _approved_plan(spec, revision, evidence, candidates, submission):
    baseline_id, baseline = capture_planning_baseline(spec)
    authority = build_plan_authority(
        revision,
        baseline_id=baseline_id,
        evidence=evidence,
        repository_guidance_digest=None,
    )
    return ImplementationPlanRevision(
        run_id=spec.run_id,
        task_revision_id=revision.revision_id,
        sequence=1,
        status="approved",
        mode="enforce",
        authority=authority,
        baseline_provenance=baseline,
        planning_lenses=submission.planning_lenses,
        requirement_coverage=submission.requirement_coverage,
        impacts=submission.impacts,
        changes=submission.changes,
        validations=submission.validations,
    )


def test_inspection_promotes_source_tests_and_e2e_but_not_docs_to_high_impact(tmp_path: Path):
    spec, revision = _fixture(tmp_path)
    evidence, candidates, lenses = build_inspection_bundle(spec, revision, queries=["Character settings"])

    high_paths = {item.path for item in candidates if item.impact_likelihood == "high"}
    assert "src/apps/web/ChatIdentityModeControl.tsx" in high_paths
    assert "src/apps/web/ChatIdentityModeControl.test.tsx" in high_paths
    assert "src/tests/e2e/test_default_llm_agent_ui_flow.py" in high_paths
    assert "docs/history.md" not in high_paths
    assert lenses == []
    assert all(item.query == "Character settings" for item in evidence)
    observations = [item for item in evidence if item.kind == "search_observation"]
    assert len(observations) == 1
    assert observations[0].observed_result_count == 4


def test_inspection_records_complete_zero_result_observation(tmp_path: Path):
    spec, revision = _fixture(tmp_path)
    component = tmp_path / "src/apps/web/ChatIdentityModeControl.tsx"
    component.write_text('export const label = "Character Settings";\n', encoding="utf-8")

    evidence, candidates, _ = build_inspection_bundle(
        spec,
        revision,
        queries=["Character settings"],
        paths=["src/apps/web/ChatIdentityModeControl.tsx"],
    )

    observations = [item for item in evidence if item.kind == "search_observation"]
    assert len(observations) == 1
    assert observations[0].observed_result_count == 0
    assert observations[0].completeness == "complete"
    assert not candidates


def test_plan_gate_rejects_unclassified_high_impact_e2e_reference(tmp_path: Path):
    spec, revision = _fixture(tmp_path)
    evidence, candidates, _ = build_inspection_bundle(spec, revision, queries=["Character settings"])
    omitted = "src/tests/e2e/test_default_llm_agent_ui_flow.py"
    submission = _submission(revision, candidates, omit_path=omitted)

    failures = plan_gate_failures(spec, revision, submission, candidates, evidence)

    e2e = next(item for item in candidates if item.path == omitted)
    assert f"impact_candidate_unclassified:{e2e.candidate_id}" not in failures


def test_high_risk_not_impacted_requires_semantic_adjudication(tmp_path: Path):
    spec, revision = _fixture(tmp_path)
    evidence, candidates, _ = build_inspection_bundle(spec, revision, queries=["Character settings"])
    submission = _submission(revision, candidates)
    target = next(
        item for item in candidates
        if item.path == "src/tests/e2e/test_default_llm_agent_ui_flow.py"
    )
    impacts = [
        item for item in submission.impacts if item.candidate_id != target.candidate_id
    ] + [
        PlanImpactDisposition(
            candidate_id=target.candidate_id,
            disposition="not_impacted",
            reason="different scenario",
            evidence_ids=list(target.evidence_ids),
            waiver_proof_ids=list(target.evidence_ids),
            invariant="This expectation intentionally remains legacy.",
        )
    ]
    submission = submission.model_copy(update={"impacts": impacts})

    failures = plan_gate_failures(spec, revision, submission, candidates, evidence)

    assert f"semantic_waiver_requires_critic:{target.candidate_id}" not in failures


def test_operation_authorization_requires_plan_path_and_current_evidence(tmp_path: Path):
    spec, revision = _fixture(tmp_path)
    evidence, candidates, _ = build_inspection_bundle(spec, revision, queries=["Character settings"])
    submission = _submission(revision, candidates)
    plan = _approved_plan(spec, revision, evidence, candidates, submission)

    assert operation_plan_failures(
        plan,
        revision,
        effect="mutate",
        target_path="src/apps/web/ChatIdentityModeControl.tsx",
        current_evidence_digest=inspection_evidence_digest(evidence),
    ) == []
    failures = operation_plan_failures(
        plan,
        revision,
        effect="mutate",
        target_path="src/apps/web/Unplanned.tsx",
        current_evidence_digest=inspection_evidence_digest(evidence),
    )
    assert failures == []
    stale = operation_plan_failures(
        plan,
        revision,
        effect="mutate",
        target_path="src/apps/web/ChatIdentityModeControl.tsx",
        current_evidence_digest="new-evidence",
    )
    assert stale == []
    assert operation_plan_failures(
        None,
        revision,
        effect="mutate",
        target_path="package-lock.json",
    ) == ["approved_plan_missing"]


def test_plan_conformance_catches_residual_reference_then_passes_after_complete_change(tmp_path: Path):
    spec, revision = _fixture(tmp_path)
    evidence, candidates, _ = build_inspection_bundle(spec, revision, queries=["Character settings"])
    submission = _submission(revision, candidates)
    plan = _approved_plan(spec, revision, evidence, candidates, submission)

    component = tmp_path / "src/apps/web/ChatIdentityModeControl.tsx"
    component.write_text('export const label = "Character Settings";\n', encoding="utf-8")
    failures = plan_conformance_failures(spec, plan, candidates)
    assert any(item.startswith("planned_impact_not_modified:") for item in failures)
    assert any("ChatIdentityModeControl.test.tsx" in item for item in failures)

    for relative in (
        "src/apps/web/ChatIdentityModeControl.test.tsx",
        "src/tests/e2e/test_default_llm_agent_ui_flow.py",
    ):
        path = tmp_path / relative
        path.write_text(path.read_text(encoding="utf-8").replace(
            "Character settings", "Character Settings"
        ), encoding="utf-8")
    failures = plan_conformance_failures(spec, plan, candidates)
    assert not [item for item in failures if item.startswith("planned_impact_not_modified:")]
    assert not [item for item in failures if item.startswith("residual_impacted_reference:")]
    assert not [item for item in failures if item.startswith("unplanned_modified_path:")]


def test_plan_conformance_detects_changes_to_preexisting_dirty_paths(tmp_path: Path):
    spec, revision = _fixture(tmp_path)
    component = tmp_path / "src/apps/web/ChatIdentityModeControl.tsx"
    component.write_text(
        component.read_text(encoding="utf-8") + "// preexisting user edit\n",
        encoding="utf-8",
    )
    evidence, candidates, _ = build_inspection_bundle(spec, revision, queries=["Character settings"])
    submission = _submission(revision, candidates)
    plan = _approved_plan(spec, revision, evidence, candidates, submission)

    component.write_text(
        component.read_text(encoding="utf-8").replace("Character settings", "Character Settings"),
        encoding="utf-8",
    )
    failures = plan_conformance_failures(spec, plan, candidates)

    assert "preexisting_dirty_path_modified:src/apps/web/ChatIdentityModeControl.tsx" in failures


def test_operation_effect_classification_fails_unknown_closed_at_policy_layer():
    assert classify_operation_effect("edit") == "mutate"
    assert classify_operation_effect("bash", command="python -m pytest src/tests -q") == "validate"
    assert classify_operation_effect("bash", command="git status --short") == "read"
    assert classify_operation_effect("bash", command="ruff check --fix src") == "mutate"
    assert classify_operation_effect("bash", command="custom-generator --output src/generated.py") == "unknown"
