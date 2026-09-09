from __future__ import annotations

from pathlib import Path

from app.agent_runtime.contracts import AgentRunSpec, ModelRef, TaskRevision, WorkspaceSpec
from app.agent_runtime.pi_runtime import pi_rpc_argv
from app.agent_runtime.planning import (
    build_inspection_bundle,
    operation_plan_failures,
    planning_requirement_for_operation,
)
from app.agent_runtime.planning_acceptance import PlanningAcceptanceAssessment


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="revision-1",
        run_id="run-1",
        sequence=1,
        user_instruction="Fix the dropdown",
        effective_objective="Fix the dropdown",
    )


def test_normal_in_scope_edits_are_advisory_not_plan_authority() -> None:
    revision = _revision()
    assert planning_requirement_for_operation("mutate", target_path="src/app/service.py") == "advisory"
    assert planning_requirement_for_operation("mutate", target_path="tests/test_service.py") == "advisory"
    assert operation_plan_failures(None, revision, effect="mutate", target_path="src/app/service.py") == []


def test_consequential_mutations_remain_hard_gated() -> None:
    revision = _revision()
    for path in (
        "src/app/persistence/migrations/0066_change.sql",
        "package-lock.json",
        "src/apps/web/src/api/generated/types.ts",
    ):
        assert planning_requirement_for_operation("mutate", target_path=path) == "hard"
        assert operation_plan_failures(None, revision, effect="mutate", target_path=path) == ["approved_plan_missing"]
    assert planning_requirement_for_operation("mutate", command="npm --prefix src/apps/web install react") == "hard"
    assert planning_requirement_for_operation("unknown", command="custom-generator --output src/generated.py") == "hard"


def test_advisory_planning_failures_cannot_block_acceptance() -> None:
    assessment = PlanningAcceptanceAssessment(
        mode="enforce",
        plan_revision_id="plan-1",
        failures=("plan_inspection_evidence_stale",),
        hard_gate_required=False,
    )
    assert assessment.would_block
    assert not assessment.blocks_acceptance
    assert not assessment.fail_closed


def test_explicit_trusted_pi_skill_is_loaded_while_discovery_stays_disabled(tmp_path: Path) -> None:
    spec = AgentRunSpec(
        run_id="run-skill",
        task="Fix code",
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
        workspace=WorkspaceSpec(root=str(tmp_path)),
        capabilities=["workspace.read", "workspace.edit"],
        expected_artifacts=["diff"],
    )
    argv = pi_rpc_argv(spec)
    assert "--no-skills" in argv
    assert "--no-prompt-templates" in argv
    assert "--no-context-files" in argv
    assert "--skill" in argv
    skill = Path(argv[argv.index("--skill") + 1])
    assert skill.name == "SKILL.md"
    assert skill.parent.name == "engineering"
    assert skill.exists()


def test_omnix_no_longer_infers_semantic_inspection_from_user_language(tmp_path: Path) -> None:
    # No workspace is enough to prove Omnix no longer invents task lenses or
    # quoted-literal searches merely from the objective.
    spec = AgentRunSpec(
        run_id="run-inspect",
        task='Rename "Old" to "New" in the UI',
        objective='Rename "Old" to "New" in the UI',
        profile="coding",
        model=ModelRef(provider_id="test", model_id="model"),
    )
    revision = TaskRevision(
        revision_id="revision-inspect",
        run_id=spec.run_id,
        sequence=1,
        user_instruction=spec.task,
        effective_objective=spec.objective,
    )
    evidence, candidates, lenses = build_inspection_bundle(spec, revision)
    assert evidence == []
    assert candidates == []
    assert lenses == []
