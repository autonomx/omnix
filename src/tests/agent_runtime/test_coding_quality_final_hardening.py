from __future__ import annotations

from pathlib import Path
import json
import subprocess

import pytest

from app.agent_runtime.budget import AgentBudgetManager
from app.agent_runtime.coding_quality import capture_workspace_state, compile_task_engineering_contract, materialize_review_workspace, missing_final_validations, parse_self_review_result, quality_failure_reasons, self_review_is_acceptable
from app.agent_runtime.contracts import AgentRunSnapshot, AgentRunSpec, ModelRef, SuccessCriterion, TaskRevision, ValidationResult, ValidationSpec, WorkspaceSpec
from app.agent_runtime.workspace import WorkspacePolicyError


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"; root.mkdir(); _git(root, "init"); _git(root, "config", "user.email", "quality@example.com"); _git(root, "config", "user.name", "Quality Tests"); (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8"); _git(root, "add", "."); _git(root, "commit", "-m", "baseline"); return root


def _spec(root: Path) -> AgentRunSpec:
    return AgentRunSpec(run_id="hardening-run", task="Change behavior and validate it", objective="Change behavior and validate it", profile="coding", model=ModelRef(provider_id="test", model_id="model", reasoning_effort="high"), capabilities=["workspace.read","workspace.list","workspace.search","workspace.git_status","workspace.git_diff","workspace.edit","workspace.write","workspace.command","workspace.test"], workspace=WorkspaceSpec(root=str(root), repository=str(root), worktree=str(root)), expected_artifacts=["diff"], quality_policy="strict")


def _revision(spec: AgentRunSpec) -> TaskRevision:
    requirements, constraints, validations = compile_task_engineering_contract(spec.objective, [SuccessCriterion(id="behavior", description="Behavior is correct")], profile="coding", mutating=True)
    return TaskRevision(revision_id="revision-hardening", run_id=spec.run_id, sequence=1, user_instruction=spec.task, effective_objective=spec.objective, effective_success_criteria=[SuccessCriterion(id="behavior", description="Behavior is correct")], requirements=requirements, constraints=constraints, validation_plan=validations, expected_artifacts=["diff"])


def test_same_validation_kind_cannot_substitute_for_named_identity(tmp_path: Path) -> None:
    root = _repo(tmp_path); spec = _spec(root); revision = _revision(spec)
    extra = ValidationSpec(id="special-regression", kind="test", description="special", covers=["user-objective"], required=True)
    revision = revision.model_copy(update={"validation_plan": [*revision.validation_plan, extra]}); (root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    state = capture_workspace_state(spec, task_revision_id=revision.revision_id); assert state is not None
    observed = ValidationResult(run_id=spec.run_id, validation_id="final-state-tests", kind="test", task_revision_id=revision.revision_id, workspace_state_id=state.state_id, command="python -m pytest -q", success=True, output_digest="x", covers_requirement_ids=[item.id for item in revision.requirements if item.required])
    assert "special-regression" in {item.id for item in missing_final_validations(revision, [observed], workspace_state_id=state.state_id)}


def test_structured_self_review_is_required_and_state_bound(tmp_path: Path) -> None:
    root = _repo(tmp_path); spec = _spec(root); revision = _revision(spec); (root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    state = capture_workspace_state(spec, task_revision_id=revision.revision_id); assert state is not None
    payload = {"verdict":"approve","requirements":[{"requirement_id":item.id,"status":"satisfied","evidence":"checked"} for item in revision.requirements if item.required],"findings":[],"missing_tests":[],"residual_risks":[]}
    self_review = parse_self_review_result(json.dumps(payload), run_id=spec.run_id, revision=revision, workspace_state_id=state.state_id); assert self_review_is_acceptable(self_review, revision)
    snapshot = AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    assert "quality_self_review_stale_or_missing" not in quality_failure_reasons(snapshot, revision, state, [], [], [self_review])
    assert "quality_self_review_stale_or_missing" in quality_failure_reasons(snapshot, revision, state, [], [], [self_review.model_copy(update={"workspace_state_id":"old"})])


def test_reused_review_snapshot_is_reverified(tmp_path: Path) -> None:
    root = _repo(tmp_path); spec = _spec(root); revision = _revision(spec); (root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    state = capture_workspace_state(spec, task_revision_id=revision.revision_id); assert state is not None
    workspace = materialize_review_workspace(spec, state, review_root=tmp_path / "reviews"); review_root = Path(workspace.worktree or workspace.root); (review_root / "module.py").write_text("VALUE = 999\n", encoding="utf-8")
    with pytest.raises(WorkspacePolicyError, match="no longer reproduces"): materialize_review_workspace(spec, state, review_root=tmp_path / "reviews")


class _Result:
    def __init__(self, row): self.row = row
    def fetchone(self): return self.row
class _Connection:
    def __init__(self, stage, attempt): self.stage, self.attempt = stage, attempt
    def execute(self, *_a, **_k): return _Result((self.stage, self.attempt))
class _Repo:
    def __init__(self, stage, attempt): self.context = type("C", (), {"workspace_id":"w"})(); self.connection = _Connection(stage, attempt)
    @staticmethod
    def list_children(_run_id): return []


def test_budget_protects_review_and_first_repair_envelopes(tmp_path: Path) -> None:
    spec = _spec(_repo(tmp_path)); snapshot = AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    initial = AgentBudgetManager._effective_limits(_Repo("implementing", 1), snapshot); assert initial["max_steps"] == 130; assert initial["max_tool_calls"] == 325
    repair = AgentBudgetManager._effective_limits(_Repo("repairing", 2), snapshot); assert repair["max_steps"] == 150; assert repair["max_tool_calls"] == 375
