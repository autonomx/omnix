"""Opt-in live baseline/candidate matrix for coding-agent completion quality.

This is the Phase 0 + Phase 31 benchmark harness. It executes the *real* Pi
AgentRunService twice for each scenario against independently-created copies of
the same tiny repository:

* baseline: ``quality_policy=off``
* candidate: ``quality_policy=strict``

The test uses GPT-5.6 Luna with high reasoning and the authenticated ChatGPT Codex
provider. It does not require the Omnix HTTP server, but it does require the
normal PostgreSQL Agent Runtime database and local Pi/Codex authentication.

PowerShell:

    $env:OMNIX_RUN_LIVE_CODING_QUALITY_TESTS="1"
    $env:OMNIX_TEST_DATABASE_URL="postgresql://..."
    python -m pytest src/tests/agent_runtime/test_live_coding_quality_matrix.py -q -s --tb=short

Optional:

    $env:OMNIX_LIVE_CODEX_PATH="codex"
    $env:OMNIX_PI_PATH="pi"
    $env:OMNIX_LIVE_CODING_QUALITY_SCENARIO="python_behavior_and_regression"
    $env:OMNIX_LIVE_CODING_QUALITY_REPORT="artifacts/coding-quality-report.json"
    $env:OMNIX_LIVE_CODING_QUALITY_ROLLOUT_POLICY="strict"
    $env:OMNIX_ENFORCE_LIVE_CODING_QUALITY_ROLLOUT="1"

Hosted CI intentionally collects the contract test while skipping live execution
when the opt-in flag is absent. A rollout decision is based on independent repo
oracles plus durable Omnix quality evidence; model claims alone do not score a
scenario as correct. Rollout enforcement is separately opt-in because reviewer
catch/repair rates are only meaningful when the selected corpus actually
produces reviewer findings and repairs.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import time
from typing import Literal
import uuid

import pytest

from app.agent_runtime.contracts import (
    AcceptancePlan,
    AgentRunSpec,
    ModelRef,
    SuccessCriterion,
    WorkspaceSpec,
)
from app.agent_runtime.quality_evaluation import (
    CodingQualitySample,
    compare_quality_baseline,
    evaluate_rollout_policy,
    write_evaluation_report,
)
from app.agent_runtime.service import AgentRunService


_TRUE = {"1", "true", "yes", "on"}
_MODEL = "gpt-5.6-luna"
_REASONING_EFFORT = "high"
_PROVIDER = "chatgpt_codex"
_TERMINAL = {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class Oracle:
    id: str
    command: tuple[str, ...] | None = None
    path: str | None = None
    contains: str | None = None


@dataclass(frozen=True)
class LiveCodingScenario:
    id: str
    files: dict[str, str]
    task: str
    success_criteria: tuple[str, ...]
    oracles: tuple[Oracle, ...]
    reviewer_probe: bool = False


SCENARIOS: tuple[LiveCodingScenario, ...] = (
    LiveCodingScenario(
        id="python_behavior_and_regression",
        files={
            "calculator.py": "def add(a: int, b: int) -> int:\n    return a + b + 1\n",
            "tests/test_calculator.py": (
                "from calculator import add\n\n"
                "def test_add():\n"
                "    assert add(2, 3) == 5\n"
            ),
        },
        task=(
            "Fix calculator.add so normal integer addition is correct. Preserve "
            "the public function signature, add or improve a focused regression "
            "test if useful, inspect the complete diff, and run the smallest "
            "relevant pytest command against the final code."
        ),
        success_criteria=(
            "calculator.add(2, 3) returns 5 without changing its public signature.",
            "The focused pytest regression passes on the final workspace state.",
        ),
        oracles=(
            Oracle("pytest", command=("python", "-m", "pytest", "-q")),
            Oracle("implementation", path="calculator.py", contains="return a + b"),
        ),
    ),
    LiveCodingScenario(
        id="multi_file_caller_contract",
        files={
            "slug.py": (
                "def slugify(value: str) -> str:\n"
                "    return value.strip().replace(' ', '-')\n"
            ),
            "consumer.py": (
                "from slug import slugify\n\n"
                "def profile_url(name: str) -> str:\n"
                "    return '/u/' + slugify(name)\n"
            ),
            "tests/test_slug.py": (
                "from consumer import profile_url\n"
                "from slug import slugify\n\n"
                "def test_slugify_is_canonical_lowercase():\n"
                "    assert slugify(' Ada Lovelace ') == 'ada-lovelace'\n\n"
                "def test_consumer_uses_canonical_slug():\n"
                "    assert profile_url(' Grace Hopper ') == '/u/grace-hopper'\n"
            ),
        },
        task=(
            "Make slugify return canonical lowercase hyphenated slugs while "
            "preserving its signature. Inspect its callers before editing, keep "
            "consumer.profile_url compatible, and run the focused tests after "
            "the final mutation."
        ),
        success_criteria=(
            "slugify trims, lowercases, and hyphenates names.",
            "Existing callers continue to produce canonical URLs.",
            "Focused tests pass on the final workspace state.",
        ),
        oracles=(
            Oracle("pytest", command=("python", "-m", "pytest", "-q")),
            Oracle("lowercase", path="slug.py", contains="lower"),
        ),
    ),
    LiveCodingScenario(
        id="reviewer_hidden_requirement_probe",
        files={
            "names.py": (
                "def normalize_name(value: str) -> str:\n"
                "    return value.strip().lower()\n"
            ),
            "tests/test_names.py": (
                "from names import normalize_name\n\n"
                "def test_normalize_name():\n"
                "    assert normalize_name('  Ada  ') == 'ada'\n"
            ),
        },
        task=(
            "Extend normalize_name so it still trims and lowercases ordinary "
            "names, but also collapses every run of internal whitespace to one "
            "space and returns an empty string for whitespace-only input. Add "
            "regression coverage for both edge cases, search for callers, and "
            "validate the final state."
        ),
        success_criteria=(
            "Internal whitespace runs collapse to one space.",
            "Whitespace-only input returns an empty string.",
            "Ordinary trim/lowercase behavior remains compatible.",
            "Regression tests cover both requested edge cases.",
        ),
        oracles=(
            Oracle("pytest", command=("python", "-m", "pytest", "-q")),
            Oracle("whitespace-logic", path="names.py", contains="split"),
        ),
        reviewer_probe=True,
    ),
)


def _enabled() -> bool:
    return str(os.environ.get("OMNIX_RUN_LIVE_CODING_QUALITY_TESTS", "")).strip().casefold() in _TRUE


def _enforce_rollout() -> bool:
    return str(os.environ.get("OMNIX_ENFORCE_LIVE_CODING_QUALITY_ROLLOUT", "")).strip().casefold() in _TRUE


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _make_repository(root: Path, scenario: LiveCodingScenario) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "quality-matrix@example.com")
    _git(root, "config", "user.name", "Omnix Quality Matrix")
    for relative, content in scenario.files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "quality matrix fixture")
    return root


def _run_oracles(root: Path, scenario: LiveCodingScenario) -> tuple[int, int]:
    satisfied = 0
    for oracle in scenario.oracles:
        if oracle.command is not None:
            result = subprocess.run(
                list(oracle.command),
                cwd=root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            satisfied += int(result.returncode == 0)
            continue
        if oracle.path and oracle.contains is not None:
            path = root / oracle.path
            satisfied += int(path.is_file() and oracle.contains in path.read_text(encoding="utf-8"))
    return len(scenario.oracles), satisfied


def _wait_for_terminal(service: AgentRunService, run_id: str, timeout_seconds: float = 900.0):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        snapshot = service.get(run_id)
        if snapshot is not None and snapshot.status in _TERMINAL:
            return snapshot
        time.sleep(1.0)
    raise AssertionError(f"live coding quality run did not reach terminal state: {run_id}")


def _numeric_usage(events, key: str) -> float:
    total = 0.0
    for event in events:
        usage = event.payload.get("usage")
        if isinstance(usage, dict):
            try:
                total += float(usage.get(key) or 0)
            except (TypeError, ValueError):
                pass
    return total


def _sample_from_run(
    service: AgentRunService,
    scenario: LiveCodingScenario,
    *,
    variant: Literal["baseline", "candidate"],
    snapshot,
) -> CodingQualitySample:
    events = service.events(snapshot.run_id, after_sequence=0)
    revisions = service.task_revisions(snapshot.run_id)
    revision = revisions[-1] if revisions else None
    validations = service.validation_results(snapshot.run_id)
    reviews = service.review_results(snapshot.run_id)
    workspace = snapshot.spec.workspace
    root = Path((workspace.worktree or workspace.root) if workspace else ".")
    requirements_total, requirements_satisfied = _run_oracles(root, scenario)
    final_state_id = snapshot.workspace_state_id
    current_validations = [
        item for item in validations
        if final_state_id and item.workspace_state_id == final_state_id and item.success
    ]
    current_reviews = [
        item for item in reviews
        if final_state_id and item.workspace_state_id == final_state_id
    ]
    reviewer_changes = [item for item in reviews if item.verdict == "changes_required"]
    repair_events = [item for item in events if item.event_type == "quality.repair_requested"]
    completed = snapshot.status == "completed"
    stale_validation_accepted = bool(
        variant == "candidate" and completed and not current_validations
    )
    stale_review_accepted = bool(
        variant == "candidate"
        and completed
        and snapshot.spec.quality_policy in {"strict", "critical"}
        and not any(item.verdict == "approve" for item in current_reviews)
    )
    started_at = snapshot.started_at or snapshot.created_at
    finished_at = snapshot.completed_at or snapshot.updated_at
    wall_time = max(0.0, (finished_at - started_at).total_seconds())
    return CodingQualitySample(
        scenario_id=scenario.id,
        variant=variant,
        quality_policy=snapshot.spec.quality_policy,
        completed=completed,
        requirements_total=requirements_total,
        requirements_satisfied=requirements_satisfied,
        final_state_validated=bool(current_validations) if variant == "candidate" else False,
        stale_validation_accepted=stale_validation_accepted,
        stale_review_accepted=stale_review_accepted,
        reviewer_required=variant == "candidate",
        reviewer_approved=(
            any(item.verdict == "approve" for item in current_reviews)
            if variant == "candidate"
            else None
        ),
        # This scenario stresses requirement coverage but does not claim a
        # deterministic injected defect. A reviewer catch is measurable only if
        # the implementer actually leaves something for the reviewer to find.
        injected_defect=bool(scenario.reviewer_probe and reviewer_changes),
        reviewer_caught_defect=(
            True if scenario.reviewer_probe and reviewer_changes and variant == "candidate" else None
        ),
        repair_attempts=len(repair_events),
        repair_succeeded=(completed if repair_events else None),
        output_tokens=int(_numeric_usage(events, "output_tokens")),
        tool_calls=sum(item.event_type == "tool.completed" for item in events),
        wall_time_seconds=wall_time,
        cost=_numeric_usage(events, "cost"),
        metadata={
            "run_id": snapshot.run_id,
            "task_revision_id": revision.revision_id if revision is not None else None,
            "workspace_state_id": final_state_id,
            "review_count": len(reviews),
            "validation_count": len(validations),
            "reviewer_changes_required_count": len(reviewer_changes),
        },
    )


def _run_variant(
    service: AgentRunService,
    scenario: LiveCodingScenario,
    root: Path,
    *,
    variant: Literal["baseline", "candidate"],
) -> CodingQualitySample:
    repository = _make_repository(root, scenario)
    run_id = f"quality-live-{variant}-{scenario.id}-{uuid.uuid4().hex}"
    spec = AgentRunSpec(
        run_id=run_id,
        task=scenario.task,
        objective=scenario.task,
        profile="coding",
        model=ModelRef(
            provider_id=_PROVIDER,
            model_id=_MODEL,
            reasoning_effort=_REASONING_EFFORT,
        ),
        capabilities=[
            "workspace.read",
            "workspace.list",
            "workspace.search",
            "workspace.git_status",
            "workspace.git_diff",
            "workspace.edit",
            "workspace.write",
            "workspace.command",
            "workspace.test",
        ],
        workspace=WorkspaceSpec(
            root=str(repository),
            repository=str(repository),
            base_ref="main",
            isolation_policy="supervised_worktree",
        ),
        success_criteria=[
            SuccessCriterion(id=f"R{index + 1}", description=value)
            for index, value in enumerate(scenario.success_criteria)
        ],
        expected_artifacts=["diff"],
        acceptance_plan=AcceptancePlan(
            required_artifacts=["diff"],
            require_diff=True,
            checks=["successful_test_command"],
        ),
        quality_policy="off" if variant == "baseline" else "strict",
        quality_reserve_fraction=0.25,
    )
    started = service.start(spec)
    terminal = _wait_for_terminal(service, started.run_id)
    return _sample_from_run(
        service,
        scenario,
        variant=variant,
        snapshot=terminal,
    )


def _shutdown_service(service: AgentRunService) -> None:
    """Best-effort local test cleanup without inventing a service close API."""

    service._supervisor_stop.set()
    for run_id in list(service.runtime.active_run_ids()):
        try:
            service.runtime.close_run(run_id)
        except Exception:
            pass


def test_live_coding_quality_matrix_contract() -> None:
    assert {scenario.id for scenario in SCENARIOS} == {
        "python_behavior_and_regression",
        "multi_file_caller_contract",
        "reviewer_hidden_requirement_probe",
    }
    assert all(scenario.success_criteria for scenario in SCENARIOS)
    assert all(len(scenario.oracles) >= 2 for scenario in SCENARIOS)
    assert any(scenario.reviewer_probe for scenario in SCENARIOS)


@pytest.mark.skipif(not _enabled(), reason="live coding quality matrix is opt-in")
def test_live_coding_quality_baseline_candidate_matrix(tmp_path: Path) -> None:
    if not os.environ.get("OMNIX_TEST_DATABASE_URL") and not os.environ.get("OMNIX_DATABASE_URL"):
        pytest.skip("PostgreSQL Agent Runtime database is required")

    selected = str(os.environ.get("OMNIX_LIVE_CODING_QUALITY_SCENARIO", "")).strip()
    scenarios = [scenario for scenario in SCENARIOS if not selected or scenario.id == selected]
    assert scenarios, f"unknown live coding quality scenario: {selected}"

    pi_path = str(os.environ.get("OMNIX_PI_PATH", "pi") or "pi")
    service = AgentRunService(pi_path=pi_path, worker_id=f"quality-matrix:{uuid.uuid4().hex}")
    baseline: list[CodingQualitySample] = []
    candidate: list[CodingQualitySample] = []
    try:
        for scenario in scenarios:
            baseline.append(
                _run_variant(
                    service,
                    scenario,
                    tmp_path / scenario.id / "baseline",
                    variant="baseline",
                )
            )
            candidate.append(
                _run_variant(
                    service,
                    scenario,
                    tmp_path / scenario.id / "candidate",
                    variant="candidate",
                )
            )
    finally:
        _shutdown_service(service)

    comparison = compare_quality_baseline(baseline, candidate)
    policy = str(
        os.environ.get("OMNIX_LIVE_CODING_QUALITY_ROLLOUT_POLICY", "strict")
    ).strip().casefold()
    if policy not in {"standard", "strict", "critical"}:
        raise AssertionError(f"invalid rollout policy: {policy}")
    decision = evaluate_rollout_policy(comparison, policy=policy)  # type: ignore[arg-type]
    report_path = Path(
        os.environ.get(
            "OMNIX_LIVE_CODING_QUALITY_REPORT",
            str(tmp_path / "coding-quality-report.json"),
        )
    )
    write_evaluation_report(report_path, comparison, decision)
    print(report_path.read_text(encoding="utf-8"))

    # Measurement itself always has hard safety/correctness invariants. Rollout
    # policy enforcement is a separate switch because strict/critical policy is
    # designed to fail closed when the selected corpus did not exercise repair.
    assert all(sample.requirements_satisfied == sample.requirements_total for sample in candidate)
    assert not any(sample.stale_validation_accepted for sample in candidate)
    assert not any(sample.stale_review_accepted for sample in candidate)
    if _enforce_rollout():
        assert decision.allowed, "coding quality rollout gate failed: " + ", ".join(decision.reasons)
