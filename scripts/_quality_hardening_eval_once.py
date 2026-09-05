from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()


def f(name: str) -> Path:
    return ROOT / name


def rep(name: str, old: str, new: str, count: int = 1) -> None:
    p = f(name)
    text = p.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"{name}: expected {count} matches, found {actual}: {old[:100]!r}")
    p.write_text(text.replace(old, new), encoding="utf-8")


# Phase 0/31: seeded ground truth replaces circular reviewer scoring.
rep(
    "src/app/agent_runtime/quality_evaluation.py",
    "class CodingQualityAggregate(BaseModel):\n",
    '''class SeededQualityProbe(BaseModel):
    """Ground-truth defect probe defined independently of model output."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    probe_id: str = Field(min_length=1)
    defect_id: str = Field(min_length=1)
    reviewer_caught_defect: bool
    repair_succeeded: bool
    metadata: dict[str, object] = Field(default_factory=dict)


class CodingQualityAggregate(BaseModel):
''',
)
rep(
    "src/app/agent_runtime/quality_evaluation.py",
    "    cost_delta: float\n    matched_scenarios: list[str] = Field(default_factory=list)\n",
    "    cost_delta: float\n    seeded_reviewer_catch_rate: float | None = Field(default=None, ge=0.0, le=1.0)\n    seeded_repair_success_rate: float | None = Field(default=None, ge=0.0, le=1.0)\n    matched_scenarios: list[str] = Field(default_factory=list)\n",
)
rep(
    "src/app/agent_runtime/quality_evaluation.py",
    '''def compare_quality_baseline(
    baseline_samples: list[CodingQualitySample],
    candidate_samples: list[CodingQualitySample],
) -> CodingQualityComparison:
''',
    '''def compare_quality_baseline(
    baseline_samples: list[CodingQualitySample],
    candidate_samples: list[CodingQualitySample],
    *,
    seeded_probes: list[SeededQualityProbe] | None = None,
) -> CodingQualityComparison:
''',
)
rep(
    "src/app/agent_runtime/quality_evaluation.py",
    "    candidate_ids = {sample.scenario_id for sample in candidate_samples}\n    return CodingQualityComparison(\n",
    '''    candidate_ids = {sample.scenario_id for sample in candidate_samples}
    probes = list(seeded_probes or [])
    seeded_reviewer_catch_rate = _rate([probe.reviewer_caught_defect for probe in probes])
    seeded_repair_success_rate = _rate([probe.repair_succeeded for probe in probes])
    return CodingQualityComparison(
''',
)
rep(
    "src/app/agent_runtime/quality_evaluation.py",
    "        cost_delta=candidate.average_cost - baseline.average_cost,\n",
    "        cost_delta=candidate.average_cost - baseline.average_cost,\n        seeded_reviewer_catch_rate=seeded_reviewer_catch_rate,\n        seeded_repair_success_rate=seeded_repair_success_rate,\n",
)
rep(
    "src/app/agent_runtime/quality_evaluation.py",
    '''    if (
        thresholds.min_reviewer_catch_rate is not None
        and candidate.reviewer_catch_rate is not None
        and candidate.reviewer_catch_rate < thresholds.min_reviewer_catch_rate
    ):
        reasons.append("reviewer_catch_rate_below_threshold")
    if (
        thresholds.min_repair_success_rate is not None
        and candidate.repair_success_rate is not None
        and candidate.repair_success_rate < thresholds.min_repair_success_rate
    ):
        reasons.append("repair_success_rate_below_threshold")
''',
    '''    reviewer_catch_rate = comparison.seeded_reviewer_catch_rate if comparison.seeded_reviewer_catch_rate is not None else candidate.reviewer_catch_rate
    repair_success_rate = comparison.seeded_repair_success_rate if comparison.seeded_repair_success_rate is not None else candidate.repair_success_rate
    if thresholds.min_reviewer_catch_rate is not None and reviewer_catch_rate is not None and reviewer_catch_rate < thresholds.min_reviewer_catch_rate:
        reasons.append("reviewer_catch_rate_below_threshold")
    if thresholds.min_repair_success_rate is not None and repair_success_rate is not None and repair_success_rate < thresholds.min_repair_success_rate:
        reasons.append("repair_success_rate_below_threshold")
''',
)
rep(
    "src/app/agent_runtime/quality_evaluation.py",
    '''    if policy in {"strict", "critical"}:
        if candidate.reviewer_catch_rate is None:
            reasons.append("reviewer_catch_rate_unmeasured")
        if candidate.repair_success_rate is None:
            reasons.append("repair_success_rate_unmeasured")
''',
    '''    if policy in {"strict", "critical"}:
        if reviewer_catch_rate is None:
            reasons.append("reviewer_catch_rate_unmeasured")
        if repair_success_rate is None:
            reasons.append("repair_success_rate_unmeasured")
''',
)

# The normal candidate result never declares that a defect existed merely because
# the reviewer emitted changes_required.
rep("src/tests/agent_runtime/test_live_coding_quality_matrix.py", "    CodingQualitySample,\n", "    CodingQualitySample,\n    SeededQualityProbe,\n")
rep(
    "src/tests/agent_runtime/test_live_coding_quality_matrix.py",
    '''        # This scenario stresses requirement coverage but does not claim a
        # deterministic injected defect. A reviewer catch is measurable only if
        # the implementer actually leaves something for the reviewer to find.
        injected_defect=bool(scenario.reviewer_probe and reviewer_changes),
        reviewer_caught_defect=(
            True if scenario.reviewer_probe and reviewer_changes and variant == "candidate" else None
        ),
''',
    '''        # Ground truth is supplied only by seeded probes below; reviewer
        # output can never manufacture its own successful catch measurement.
        injected_defect=False,
        reviewer_caught_defect=None,
''',
)
rep(
    "src/tests/agent_runtime/test_live_coding_quality_matrix.py",
    "def _shutdown_service(service: AgentRunService) -> None:\n",
    '''def _run_seeded_quality_probe(service: AgentRunService, root: Path) -> SeededQualityProbe:
    fixture = LiveCodingScenario(
        id="seeded-reviewer-probe",
        files={
            "names.py": "def normalize_name(value: str) -> str:\\n    return value.strip().lower()\\n",
            "tests/test_names.py": "from names import normalize_name\\n\\ndef test_internal_whitespace():\\n    assert normalize_name(' Ada   Lovelace ') == 'ada lovelace'\\n",
        },
        task="",
        success_criteria=(),
        oracles=(),
    )
    reviewer_repo = _make_repository(root / "reviewer", fixture)
    review_task = (
        "Independent read-only review. Requirement: normalize_name must trim, lowercase, and collapse every run of internal whitespace to one space. "
        "Inspect names.py and tests. Return ONLY JSON with verdict approve|changes_required|blocked, requirements, findings, missing_tests, residual_risks. "
        "The defect is known to exist before this reviewer starts; do not modify files."
    )
    reviewer_spec = AgentRunSpec(
        run_id=f"quality-seeded-review-{uuid.uuid4().hex}", task=review_task, objective=review_task,
        profile="coding-reviewer", model=ModelRef(provider_id=_PROVIDER, model_id=_MODEL, reasoning_effort=_REASONING_EFFORT),
        capabilities=["workspace.read", "workspace.list", "workspace.search", "workspace.git_status", "workspace.git_diff"],
        workspace=WorkspaceSpec(root=str(reviewer_repo), repository=str(reviewer_repo), base_ref="main", worktree=str(reviewer_repo), isolation_policy="immutable_review_snapshot"),
        approval_policy="disabled", quality_policy="off",
    )
    reviewer_terminal = _wait_for_terminal(service, service.start(reviewer_spec).run_id)
    events = service.events(reviewer_terminal.run_id, after_sequence=0)
    text = next((str(event.payload.get("text") or "").strip() for event in reversed(events) if event.event_type == "model.message" and str(event.payload.get("text") or "").strip()), "")
    lowered = text.casefold()
    caught = reviewer_terminal.status == "completed" and "changes_required" in lowered and "names.py" in lowered and ("whitespace" in lowered or "split" in lowered)

    repair = LiveCodingScenario(
        id="seeded-repair-probe", files=dict(fixture.files),
        task="Repair the confirmed names.py defect: normalize_name must trim, lowercase, and collapse internal whitespace runs to one space. Preserve the signature, run focused pytest after the final edit, inspect the final diff, and complete the normal quality pipeline.",
        success_criteria=("Internal whitespace collapses to one space.", "Focused regression passes on the final state."),
        oracles=(Oracle("pytest", command=("python", "-m", "pytest", "-q")), Oracle("implementation", path="names.py", contains="split")),
    )
    repaired = _run_variant(service, repair, root / "repair", variant="candidate")
    repaired_ok = repaired.completed and repaired.requirements_satisfied == repaired.requirements_total
    return SeededQualityProbe(
        probe_id="seeded-whitespace-review-repair", defect_id="internal-whitespace-not-collapsed",
        reviewer_caught_defect=bool(caught), repair_succeeded=bool(repaired_ok),
        metadata={"reviewer_run_id": reviewer_terminal.run_id, "repair_run_id": repaired.metadata.get("run_id")},
    )


def _shutdown_service(service: AgentRunService) -> None:
''',
)
rep("src/tests/agent_runtime/test_live_coding_quality_matrix.py", "    candidate: list[CodingQualitySample] = []\n    try:\n", "    candidate: list[CodingQualitySample] = []\n    seeded_probes: list[SeededQualityProbe] = []\n    try:\n")
rep(
    "src/tests/agent_runtime/test_live_coding_quality_matrix.py",
    '''            candidate.append(
                _run_variant(
                    service,
                    scenario,
                    tmp_path / scenario.id / "candidate",
                    variant="candidate",
                )
            )
    finally:
''',
    '''            candidate.append(
                _run_variant(
                    service,
                    scenario,
                    tmp_path / scenario.id / "candidate",
                    variant="candidate",
                )
            )
        seeded_probes.append(_run_seeded_quality_probe(service, tmp_path / "seeded-quality-probe"))
    finally:
''',
)
rep("src/tests/agent_runtime/test_live_coding_quality_matrix.py", "    comparison = compare_quality_baseline(baseline, candidate)\n", "    comparison = compare_quality_baseline(baseline, candidate, seeded_probes=seeded_probes)\n")

# Unit rollout regression.
rep("src/tests/agent_runtime/test_quality_evaluation.py", "    CodingQualitySample,\n", "    CodingQualitySample,\n    SeededQualityProbe,\n")
with f("src/tests/agent_runtime/test_quality_evaluation.py").open("a", encoding="utf-8") as out:
    out.write('''\n\ndef test_strict_rollout_uses_seeded_ground_truth_probe_metrics() -> None:\n    baseline = [_sample("a", "baseline", injected_defect=False)]\n    candidate = [_sample("a", "candidate", injected_defect=False, reviewer_caught_defect=None, repair_attempts=0, repair_succeeded=None)]\n    probes = [SeededQualityProbe(probe_id="seeded", defect_id="known-defect", reviewer_caught_defect=True, repair_succeeded=True)]\n    comparison = compare_quality_baseline(baseline, candidate, seeded_probes=probes)\n    decision = evaluate_rollout_policy(comparison, policy="strict")\n    assert comparison.seeded_reviewer_catch_rate == 1.0\n    assert comparison.seeded_repair_success_rate == 1.0\n    assert "reviewer_catch_rate_unmeasured" not in decision.reasons\n    assert "repair_success_rate_unmeasured" not in decision.reasons\n''')

# Deterministic invariant tests for the final hardening pass.
f("src/tests/agent_runtime/test_coding_quality_final_hardening.py").write_text('''from __future__ import annotations

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
    root = tmp_path / "repo"; root.mkdir(); _git(root, "init"); _git(root, "config", "user.email", "quality@example.com"); _git(root, "config", "user.name", "Quality Tests"); (root / "module.py").write_text("VALUE = 1\\n", encoding="utf-8"); _git(root, "add", "."); _git(root, "commit", "-m", "baseline"); return root


def _spec(root: Path) -> AgentRunSpec:
    return AgentRunSpec(run_id="hardening-run", task="Change behavior and validate it", objective="Change behavior and validate it", profile="coding", model=ModelRef(provider_id="test", model_id="model", reasoning_effort="high"), capabilities=["workspace.read","workspace.list","workspace.search","workspace.git_status","workspace.git_diff","workspace.edit","workspace.write","workspace.command","workspace.test"], workspace=WorkspaceSpec(root=str(root), repository=str(root), worktree=str(root)), expected_artifacts=["diff"], quality_policy="strict")


def _revision(spec: AgentRunSpec) -> TaskRevision:
    requirements, constraints, validations = compile_task_engineering_contract(spec.objective, [SuccessCriterion(id="behavior", description="Behavior is correct")], profile="coding", mutating=True)
    return TaskRevision(revision_id="revision-hardening", run_id=spec.run_id, sequence=1, user_instruction=spec.task, effective_objective=spec.objective, effective_success_criteria=[SuccessCriterion(id="behavior", description="Behavior is correct")], requirements=requirements, constraints=constraints, validation_plan=validations, expected_artifacts=["diff"])


def test_same_validation_kind_cannot_substitute_for_named_identity(tmp_path: Path) -> None:
    root = _repo(tmp_path); spec = _spec(root); revision = _revision(spec)
    extra = ValidationSpec(id="special-regression", kind="test", description="special", covers=["user-objective"], required=True)
    revision = revision.model_copy(update={"validation_plan": [*revision.validation_plan, extra]}); (root / "module.py").write_text("VALUE = 2\\n", encoding="utf-8")
    state = capture_workspace_state(spec, task_revision_id=revision.revision_id); assert state is not None
    observed = ValidationResult(run_id=spec.run_id, validation_id="final-state-tests", kind="test", task_revision_id=revision.revision_id, workspace_state_id=state.state_id, command="python -m pytest -q", success=True, output_digest="x", covers_requirement_ids=[item.id for item in revision.requirements if item.required])
    assert "special-regression" in {item.id for item in missing_final_validations(revision, [observed], workspace_state_id=state.state_id)}


def test_structured_self_review_is_required_and_state_bound(tmp_path: Path) -> None:
    root = _repo(tmp_path); spec = _spec(root); revision = _revision(spec); (root / "module.py").write_text("VALUE = 2\\n", encoding="utf-8")
    state = capture_workspace_state(spec, task_revision_id=revision.revision_id); assert state is not None
    payload = {"verdict":"approve","requirements":[{"requirement_id":item.id,"status":"satisfied","evidence":"checked"} for item in revision.requirements if item.required],"findings":[],"missing_tests":[],"residual_risks":[]}
    self_review = parse_self_review_result(json.dumps(payload), run_id=spec.run_id, revision=revision, workspace_state_id=state.state_id); assert self_review_is_acceptable(self_review, revision)
    snapshot = AgentRunSnapshot(run_id=spec.run_id, spec=spec, status="running")
    assert "quality_self_review_stale_or_missing" not in quality_failure_reasons(snapshot, revision, state, [], [], [self_review])
    assert "quality_self_review_stale_or_missing" in quality_failure_reasons(snapshot, revision, state, [], [], [self_review.model_copy(update={"workspace_state_id":"old"})])


def test_reused_review_snapshot_is_reverified(tmp_path: Path) -> None:
    root = _repo(tmp_path); spec = _spec(root); revision = _revision(spec); (root / "module.py").write_text("VALUE = 2\\n", encoding="utf-8")
    state = capture_workspace_state(spec, task_revision_id=revision.revision_id); assert state is not None
    workspace = materialize_review_workspace(spec, state, review_root=tmp_path / "reviews"); review_root = Path(workspace.worktree or workspace.root); (review_root / "module.py").write_text("VALUE = 999\\n", encoding="utf-8")
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
''', encoding="utf-8")

# PostgreSQL round-trip now covers self-review and validation coverage identity.
rep("src/tests/persistence/test_agent_coding_quality_integration.py", "    ReviewSnapshot,\n", "    ReviewSnapshot,\n    SelfReviewResult,\n")
rep("src/tests/persistence/test_agent_coding_quality_integration.py", '            output_digest="d" * 64,\n        )\n', '            output_digest="d" * 64,\n            covers_requirement_ids=["R1"],\n        )\n')
rep("src/tests/persistence/test_agent_coding_quality_integration.py", "        review_snapshot = ReviewSnapshot(\n", '''        self_review = SelfReviewResult(run_id=run_id, task_revision_id=revision_id, workspace_state_id=state.state_id, verdict="approve", requirements=[ReviewRequirementResult(requirement_id="R1", status="satisfied", evidence="Exact state checked")])
        review_snapshot = ReviewSnapshot(
''')
rep("src/tests/persistence/test_agent_coding_quality_integration.py", "            quality.add_validation_result(validation)\n            quality.add_review_snapshot(review_snapshot)\n", "            quality.add_validation_result(validation)\n            quality.add_self_review_result(self_review)\n            quality.add_review_snapshot(review_snapshot)\n")
rep("src/tests/persistence/test_agent_coding_quality_integration.py", "            validations = quality.list_validation_results(run_id)\n            snapshot = quality.get_review_snapshot(run_id, review_snapshot.snapshot_id)\n", "            validations = quality.list_validation_results(run_id)\n            self_reviews = quality.list_self_review_results(run_id)\n            snapshot = quality.get_review_snapshot(run_id, review_snapshot.snapshot_id)\n")
rep("src/tests/persistence/test_agent_coding_quality_integration.py", "        assert [item.result_id for item in validations] == [validation.result_id]\n        assert snapshot == review_snapshot\n", "        assert validations == [validation]\n        assert validations[0].covers_requirement_ids == [\"R1\"]\n        assert self_reviews == [self_review]\n        assert snapshot == review_snapshot\n")

# Reasoning propagation/audit regressions.
with f("src/tests/agent_runtime/test_model_fidelity.py").open("a", encoding="utf-8") as out:
    out.write('''\n\ndef test_chat_agent_reasoning_reads_selected_provider_setting(monkeypatch) -> None:\n    from types import SimpleNamespace\n    from app import shared\n    from app.agent_runtime import chat_bridge\n    monkeypatch.delenv("OMNIX_AGENT_REASONING_EFFORT", raising=False)\n    monkeypatch.setattr(shared, "get_provider", lambda _provider_id: SimpleNamespace(reasoning_effort="max"))\n    assert chat_bridge._agent_reasoning_effort("chatgpt_codex") == "max"\n\n\ndef test_model_fidelity_records_full_model_audit(monkeypatch) -> None:\n    monkeypatch.delenv("OMNIX_AGENT_REASONING_EFFORT", raising=False)\n    resolved = resolve_model_ref(ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-luna", reasoning_effort="max"))\n    assert resolved.parameters["requested_provider_id"] == "chatgpt_codex"\n    assert resolved.parameters["resolved_provider_id"] == "chatgpt_codex"\n    assert resolved.parameters["requested_model_id"] == "gpt-5.6-luna"\n    assert resolved.parameters["resolved_model_id"] == "gpt-5.6-luna"\n    assert resolved.parameters["requested_reasoning_effort"] == "max"\n    assert resolved.parameters["resolved_reasoning_effort"] == "max"\n''')

print("evaluation/test hardening applied")
