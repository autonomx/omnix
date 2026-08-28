"""Omnix-authoritative acceptance checks for agent completion."""
from __future__ import annotations

from pathlib import Path
import shlex
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from .contracts import AcceptancePlan, AgentArtifact, AgentEvent, AgentRunSpec, EvidenceSet, TaskRevision
from .workspace import WorkspaceAuthority


class AcceptanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    modified_paths: list[str] = Field(default_factory=list)


def compile_acceptance_plan(spec: AgentRunSpec, *, task_revision: TaskRevision | None = None) -> AcceptancePlan:
    if spec.acceptance_plan is not None and task_revision is None:
        return spec.acceptance_plan
    checks: list[str] = []
    criteria = task_revision.effective_success_criteria if task_revision is not None else spec.success_criteria
    descriptions = " ".join(
        item.description.casefold()
        for item in criteria
        if item.required
    )
    expected_artifacts = (
        list(task_revision.expected_artifacts)
        if task_revision is not None
        else list(spec.expected_artifacts)
    )
    mutating_code = spec.profile == "coding" and "diff" in expected_artifacts
    if "test" in descriptions or mutating_code:
        checks.append("successful_test_command")
    if "typecheck" in descriptions or "type check" in descriptions:
        checks.append("successful_typecheck_command")
    if "lint" in descriptions:
        checks.append("successful_lint_command")
    if task_revision is not None:
        checks.extend(value for value in task_revision.acceptance_checks if value not in checks)
    return AcceptancePlan(
        allowed_modified_paths=list(spec.workspace.allowed_paths if spec.workspace else ["**"]),
        forbidden_modified_paths=list(spec.workspace.forbidden_paths if spec.workspace else []),
        required_artifacts=expected_artifacts,
        require_diff="diff" in expected_artifacts,
        checks=checks,
    )


def evaluate_acceptance(
    spec: AgentRunSpec,
    *,
    events: Iterable[AgentEvent],
    artifacts: Iterable[AgentArtifact],
    task_revision: TaskRevision | None = None,
    evidence_set: EvidenceSet | None = None,
) -> AcceptanceResult:
    plan = compile_acceptance_plan(spec, task_revision=task_revision)
    event_rows = list(events)
    artifact_rows = list(artifacts)
    checks: dict[str, bool] = {}
    failures: list[str] = []
    modified_paths = _modified_paths(spec)

    effective_policy = (
        task_revision.evidence_decision.policy
        if task_revision is not None
        else spec.evidence_policy
    )
    if effective_policy.requirement == "required":
        evidence_ok = evidence_set is not None and evidence_set.passed
        checks["required_evidence"] = evidence_ok
        if not evidence_ok:
            failures.append("evidence_requirements_unsatisfied")

    checks["modified_paths_in_scope"] = _paths_allowed(
        modified_paths,
        allowed=plan.allowed_modified_paths,
        forbidden=plan.forbidden_modified_paths,
    )
    if not checks["modified_paths_in_scope"]:
        failures.append("modified_paths_outside_scope")

    if plan.require_diff:
        checks["diff_artifact"] = any(item.kind == "diff" for item in artifact_rows)
        if not checks["diff_artifact"]:
            failures.append("missing_diff_artifact")

    for kind in plan.required_artifacts:
        key = f"artifact:{kind}"
        checks[key] = any(item.kind == kind for item in artifact_rows)
        if not checks[key]:
            failures.append(f"missing_artifact:{kind}")

    tool_calls = _completed_commands(event_rows)
    for index, required_command in enumerate(plan.required_commands, start=1):
        key = f"required_command:{index}"
        ok = any(
            success and _command_matches(command, required_command)
            for command, success in tool_calls
        )
        checks[key] = ok
        if not ok:
            failures.append(key)

    for requirement in plan.checks:
        if requirement == "successful_test_command":
            ok = any(_is_test(command) and success for command, success in tool_calls)
        elif requirement == "successful_typecheck_command":
            ok = any(_is_typecheck(command) and success for command, success in tool_calls)
        elif requirement == "successful_lint_command":
            ok = any(_is_lint(command) and success for command, success in tool_calls)
        else:
            ok = False
        checks[requirement] = ok
        if not ok:
            failures.append(requirement)

    return AcceptanceResult(
        passed=not failures,
        checks=checks,
        failures=failures,
        modified_paths=modified_paths,
    )


def _modified_paths(spec: AgentRunSpec) -> list[str]:
    if spec.workspace is None:
        return []
    root = spec.workspace.worktree or spec.workspace.root
    try:
        status = WorkspaceAuthority(root).git_status()
    except Exception:
        return []
    rows: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        value = line[3:].strip()
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        rows.append(value.replace("\\", "/"))
    return sorted(set(rows))


def _paths_allowed(paths: list[str], *, allowed: list[str], forbidden: list[str]) -> bool:
    for value in paths:
        path = Path(value)
        if any(path.match(pattern) for pattern in forbidden):
            return False
        if allowed and not any(pattern == "**" or path.match(pattern) for pattern in allowed):
            return False
    return True


def _completed_commands(events: list[AgentEvent]) -> list[tuple[str, bool]]:
    starts: dict[str, str] = {}
    results: list[tuple[str, bool]] = []
    for event in events:
        if event.event_type == "tool.started":
            tool = str(event.payload.get("tool") or "")
            if tool not in {"bash", "powershell"}:
                continue
            call_id = str(event.payload.get("tool_call_id") or "")
            args = event.payload.get("args") if isinstance(event.payload.get("args"), dict) else {}
            command = str(args.get("command") or "")
            if call_id and command:
                starts[call_id] = command
        elif event.event_type == "tool.completed":
            call_id = str(event.payload.get("tool_call_id") or "")
            if call_id in starts:
                success = not bool(event.payload.get("is_error"))
                result = event.payload.get("result")
                if isinstance(result, dict):
                    details = result.get("details") if isinstance(result.get("details"), dict) else result
                    exit_code = details.get("exitCode", details.get("exit_code"))
                    if exit_code is not None:
                        try:
                            success = success and int(exit_code) == 0
                        except (TypeError, ValueError):
                            success = False
                results.append((starts[call_id], success))
    return results


def _is_test(command: str) -> bool:
    value = command.casefold()
    return "pytest" in value or "vitest" in value or "npm test" in value or "npm run test" in value


def _is_typecheck(command: str) -> bool:
    value = command.casefold()
    return "typecheck" in value or "tsc" in value


def _is_lint(command: str) -> bool:
    value = command.casefold()
    return "ruff" in value or " lint" in value


def _command_matches(command: str, required: list[str]) -> bool:
    expected = [str(part) for part in required]
    if not expected:
        return False
    try:
        observed = shlex.split(command, posix=True)
    except ValueError:
        observed = command.split()
    return observed == expected
