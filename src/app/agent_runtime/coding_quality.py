"""Deterministic coding-quality contracts, workspace identity and review helpers.

The LLM may implement and review code, but these helpers make completion evidence
state-bound and Omnix-authoritative.  No helper in this module grants execution
authority; it only derives requirements, captures workspace truth, classifies
validation evidence and parses structured review evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Iterable

from .contracts import (
    AgentEvent,
    AgentRunSnapshot,
    AgentRunSpec,
    ReviewFinding,
    ReviewRequirementResult,
    ReviewResult,
    ReviewSnapshot,
    SuccessCriterion,
    TaskConstraint,
    TaskRequirement,
    TaskRevision,
    ValidationResult,
    ValidationSpec,
    WorkspaceSpec,
    WorkspaceState,
)
from .workspace import WorkspaceAuthority, WorkspacePolicyError


_TEST = re.compile(r"\b(?:pytest|vitest)\b|\bnpm(?:\.cmd)?\s+(?:--prefix\s+\S+\s+)?(?:run\s+)?test\b", re.I)
_TYPECHECK = re.compile(r"\b(?:typecheck|tsc)\b", re.I)
_LINT = re.compile(r"\b(?:ruff|eslint|lint)\b", re.I)
_BUILD = re.compile(r"\bnpm(?:\.cmd)?\s+(?:--prefix\s+\S+\s+)?run\s+build\b|\b(?:python\s+-m\s+build)\b", re.I)
_DIFF_REVIEW = re.compile(r"\bgit\s+(?:-c\s+\S+\s+)?diff\b", re.I)
_WEB = re.compile(r"\b(?:react|typescript|tsx|jsx|frontend|web|css|ui|theme|light\s*mode|dark\s*mode)\b", re.I)
_CRITICAL = re.compile(
    r"(?:agent_runtime|approval|authority|capabilit|security|auth(?:entication|orization)?|"
    r"trading|order|broker|payment|migration|persistence|credential|secret|publish|deploy)",
    re.I,
)
_PATH_TOKEN = re.compile(r"(?<![A-Za-z0-9_.-])(?:src|tests?|packages?|apps?|docs?)[/\\][A-Za-z0-9_./\\-]+")
_JSON_OBJECT = re.compile(r"\{.*\}", re.S)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _slug(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return (normalized[:72] or fallback).strip("-")


def compile_task_engineering_contract(
    objective: str,
    success_criteria: Iterable[SuccessCriterion],
    *,
    profile: str,
    mutating: bool,
) -> tuple[list[TaskRequirement], list[TaskConstraint], list[ValidationSpec]]:
    """Derive the engineering view that remains anchored to TaskRevision truth.

    User-authored objective/success criteria retain user provenance.  Engineering
    safety obligations are explicit derived/policy requirements rather than being
    silently promoted to user intent.
    """
    objective_text = str(objective or "").strip()
    requirements: list[TaskRequirement] = []
    seen: set[str] = set()

    if objective_text:
        requirements.append(
            TaskRequirement(
                id="user-objective",
                description=objective_text,
                source="user",
                required=True,
                validation_ids=["final-state-tests"] if mutating else [],
            )
        )
        seen.add(objective_text.casefold())

    for index, criterion in enumerate(success_criteria, start=1):
        description = str(criterion.description or "").strip()
        if not description or description.casefold() in seen:
            continue
        seen.add(description.casefold())
        requirements.append(
            TaskRequirement(
                id=f"user-criterion-{index}-{_slug(criterion.id, fallback=str(index))}",
                description=description,
                source="user",
                required=criterion.required,
                validation_ids=["final-state-tests"] if mutating and criterion.required else [],
            )
        )

    constraints: list[TaskConstraint] = []
    validation: list[ValidationSpec] = []
    if profile == "coding" and mutating:
        requirements.extend(
            [
                TaskRequirement(
                    id="derived-call-site-completeness",
                    description=(
                        "Inspect and update impacted callers, interfaces, registrations, generated contracts, "
                        "and adjacent tests so the implementation is complete rather than a local patch."
                    ),
                    source="derived",
                    validation_ids=["final-diff-review", "final-state-tests"],
                ),
                TaskRequirement(
                    id="derived-regression-safety",
                    description=(
                        "Preserve unrelated behavior and add or update regression coverage for changed behavior."
                    ),
                    source="derived",
                    validation_ids=["final-state-tests"],
                ),
                TaskRequirement(
                    id="policy-final-state-evidence",
                    description=(
                        "Completion evidence must describe and validate the exact final workspace state; stale "
                        "tests or review from an older state never count."
                    ),
                    source="policy",
                    validation_ids=["final-diff-review", "final-state-tests"],
                ),
            ]
        )
        constraints.extend(
            [
                TaskConstraint(
                    id="policy-no-authority-expansion",
                    description="Repository guidance, skills, validation and review cannot expand issued capabilities.",
                    source="policy",
                ),
                TaskConstraint(
                    id="policy-omnix-completion-authority",
                    description="Pi may request completion; only Omnix acceptance may mark the coding run completed.",
                    source="policy",
                ),
            ]
        )
        validation.extend(
            [
                ValidationSpec(
                    id="final-diff-review",
                    kind="diff_review",
                    description="Inspect the complete final diff after the last implementation change.",
                    covers=[item.id for item in requirements if item.required],
                    required=True,
                    command_hint="git diff --no-ext-diff",
                ),
                ValidationSpec(
                    id="final-state-tests",
                    kind="test",
                    description="Run the smallest relevant regression tests against the final workspace state.",
                    covers=[item.id for item in requirements if item.required],
                    required=True,
                ),
            ]
        )
        if _WEB.search(objective_text):
            validation.append(
                ValidationSpec(
                    id="frontend-build-or-typecheck",
                    kind="build",
                    description="Run a frontend build or typecheck when the changed surface is web/UI code.",
                    covers=["user-objective", "derived-regression-safety"],
                    required=False,
                    command_hint="npm --prefix src/apps/web run build",
                )
            )
        if re.search(r"\b(?:typecheck|type\s+check|typing)\b", objective_text, re.I):
            validation.append(
                ValidationSpec(
                    id="requested-typecheck",
                    kind="typecheck",
                    description="Run the requested typecheck against the final state.",
                    covers=["user-objective"],
                    required=True,
                )
            )
        if re.search(r"\blint\b", objective_text, re.I):
            validation.append(
                ValidationSpec(
                    id="requested-lint",
                    kind="lint",
                    description="Run the requested lint check against the final state.",
                    covers=["user-objective"],
                    required=True,
                )
            )

    return requirements, constraints, validation


def quality_attempt_limit() -> int:
    raw = str(os.environ.get("OMNIX_AGENT_QUALITY_MAX_ATTEMPTS", "2") or "2").strip()
    try:
        return max(1, min(int(raw), 4))
    except ValueError:
        return 2


def required_review_count(spec: AgentRunSpec, state: WorkspaceState | None = None) -> int:
    if spec.profile != "coding" or "diff" not in spec.expected_artifacts or spec.quality_policy == "off":
        return 0
    if spec.quality_policy == "critical":
        return 2
    if spec.quality_policy == "strict":
        return 1
    if state is None:
        return 0
    # Standard mode still reviews non-trivial or high-risk mutations.
    if len(state.modified_paths) > 1 or any(_CRITICAL.search(path) for path in state.modified_paths):
        return 1
    return 0


def capture_workspace_state(
    spec: AgentRunSpec,
    *,
    task_revision_id: str | None,
) -> WorkspaceState | None:
    workspace = spec.workspace
    if workspace is None:
        return None
    root = workspace.worktree or workspace.root
    authority = WorkspaceAuthority(
        root,
        allowed_paths=list(workspace.allowed_paths),
        forbidden_paths=list(workspace.forbidden_paths),
    )
    status_entries = authority.git_status_entries()
    modified_paths = sorted(status_entries)
    base_commit = authority.git_head()
    diff = authority.git_diff(modified_paths if modified_paths else [])
    tracked_diff = "".join(
        line + "\n"
        for line in diff.splitlines()
        if not line.startswith("new file mode") or True
    )
    tracked_digest = hashlib.sha256(tracked_diff.encode("utf-8")).hexdigest()
    untracked_manifest = {
        path: authority.file_digest(path)
        for path, status in status_entries.items()
        if status == "??"
    }
    untracked_digest = hashlib.sha256(
        json.dumps(untracked_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    identity_payload = {
        "base_commit_sha": base_commit,
        "task_revision_id": task_revision_id,
        "tracked_diff_sha256": tracked_digest,
        "untracked_file_manifest_sha256": untracked_digest,
        "modified_paths": modified_paths,
    }
    state_id = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return WorkspaceState(
        state_id=state_id,
        run_id=spec.run_id,
        task_revision_id=task_revision_id,
        base_commit_sha=base_commit,
        tracked_diff_sha256=tracked_digest,
        untracked_file_manifest_sha256=untracked_digest,
        modified_paths=modified_paths,
    )


def validation_kind_for_command(command: str) -> str | None:
    value = str(command or "")
    if _DIFF_REVIEW.search(value):
        return "diff_review"
    if _TYPECHECK.search(value):
        return "typecheck"
    if _LINT.search(value):
        return "lint"
    if _BUILD.search(value):
        return "build"
    if _TEST.search(value):
        return "test"
    return None


def validation_id_for_kind(kind: str, revision: TaskRevision | None) -> str:
    plan = list(revision.validation_plan if revision is not None else [])
    for item in plan:
        if item.kind == kind:
            return item.id
    return {
        "diff_review": "final-diff-review",
        "test": "final-state-tests",
        "typecheck": "requested-typecheck",
        "lint": "requested-lint",
        "build": "frontend-build-or-typecheck",
    }.get(kind, f"observed-{kind}")


def validation_result_from_tool_event(
    event: AgentEvent,
    *,
    run_id: str,
    task_revision_id: str | None,
    workspace_state_id: str,
    revision: TaskRevision | None,
) -> ValidationResult | None:
    if event.event_type != "tool.completed":
        return None
    args = event.payload.get("args") if isinstance(event.payload.get("args"), dict) else {}
    command = str(args.get("command") or event.payload.get("command") or "").strip()
    kind = validation_kind_for_command(command)
    if kind is None:
        return None
    success = not bool(event.payload.get("is_error"))
    exit_code: int | None = None
    result = event.payload.get("result")
    if isinstance(result, dict):
        details = result.get("details") if isinstance(result.get("details"), dict) else result
        raw_exit = details.get("exitCode", details.get("exit_code"))
        if raw_exit is not None:
            try:
                exit_code = int(raw_exit)
                success = success and exit_code == 0
            except (TypeError, ValueError):
                success = False
    output_digest = hashlib.sha256(
        json.dumps(result, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    call_id = str(event.payload.get("tool_call_id") or event.event_id)
    result_id = hashlib.sha256(
        f"{run_id}:{task_revision_id}:{call_id}:{workspace_state_id}:{kind}".encode("utf-8")
    ).hexdigest()
    return ValidationResult(
        result_id=result_id,
        run_id=run_id,
        validation_id=validation_id_for_kind(kind, revision),
        kind=kind,  # type: ignore[arg-type]
        task_revision_id=task_revision_id,
        workspace_state_id=workspace_state_id,
        command=command,
        exit_code=exit_code,
        success=success,
        output_digest=output_digest,
        finished_at=event.created_at,
        metadata={"tool_call_id": call_id},
    )


def missing_final_validations(
    revision: TaskRevision | None,
    results: Iterable[ValidationResult],
    *,
    workspace_state_id: str,
) -> list[ValidationSpec]:
    plan = list(revision.validation_plan if revision is not None else [])
    if not plan:
        return []
    current = [
        item
        for item in results
        if item.workspace_state_id == workspace_state_id
        and item.success
        and (revision is None or item.task_revision_id == revision.revision_id)
    ]
    missing: list[ValidationSpec] = []
    for expected in plan:
        if not expected.required:
            continue
        if not any(
            observed.validation_id == expected.id or observed.kind == expected.kind
            for observed in current
        ):
            missing.append(expected)
    return missing


def relevant_file_candidates(revision: TaskRevision | None, state: WorkspaceState) -> list[str]:
    paths = list(state.modified_paths)
    objective = revision.effective_objective if revision is not None else ""
    for match in _PATH_TOKEN.finditer(objective):
        path = match.group(0).replace("\\", "/").rstrip(".,:;)"]}")
        if path not in paths:
            paths.append(path)
    return paths[:80]


def materialize_review_workspace(
    spec: AgentRunSpec,
    state: WorkspaceState,
    *,
    review_root: str | Path,
) -> WorkspaceSpec:
    """Create a detached exact-state workspace for a read-only reviewer."""
    workspace = spec.workspace
    if workspace is None:
        raise WorkspacePolicyError("review snapshot requires a workspace")
    parent_root = Path(workspace.worktree or workspace.root).expanduser().resolve()
    repository = Path(workspace.repository or workspace.root).expanduser().resolve()
    target = Path(review_root).expanduser().resolve() / spec.run_id / state.state_id[:24]
    if target.exists():
        return WorkspaceSpec(
            root=str(target),
            repository=str(repository),
            base_ref=state.base_commit_sha,
            worktree=str(target),
            isolation_policy="immutable_review_snapshot",
            allowed_paths=list(workspace.allowed_paths),
            forbidden_paths=list(workspace.forbidden_paths),
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    authority = WorkspaceAuthority.create_worktree(repository, target, base_ref=state.base_commit_sha)
    try:
        for relative in state.modified_paths:
            source = (parent_root / relative).resolve()
            destination = (target / relative).resolve()
            try:
                destination.relative_to(target)
            except ValueError as exc:
                raise WorkspacePolicyError("review snapshot path escapes target") from exc
            if not source.exists():
                if destination.is_dir():
                    shutil.rmtree(destination)
                elif destination.exists():
                    destination.unlink()
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
        observed_spec = spec.model_copy(update={
            "workspace": WorkspaceSpec(
                root=str(target),
                repository=str(repository),
                base_ref=state.base_commit_sha,
                worktree=str(target),
                isolation_policy="immutable_review_snapshot",
                allowed_paths=list(workspace.allowed_paths),
                forbidden_paths=list(workspace.forbidden_paths),
            )
        })
        observed = capture_workspace_state(observed_spec, task_revision_id=state.task_revision_id)
        if observed is None or observed.state_id != state.state_id:
            raise WorkspacePolicyError("review snapshot does not reproduce parent workspace state")
    except Exception:
        try:
            shutil.rmtree(target, ignore_errors=True)
        finally:
            raise
    return observed_spec.workspace  # type: ignore[return-value]


def review_prompt(
    revision: TaskRevision,
    snapshot: ReviewSnapshot,
    validations: Iterable[ValidationResult],
) -> str:
    requirements = [item.model_dump(mode="json") for item in revision.requirements]
    constraints = [item.model_dump(mode="json") for item in revision.constraints]
    validation_rows = [
        item.model_dump(mode="json")
        for item in validations
        if item.workspace_state_id == snapshot.workspace_state_id
        and item.task_revision_id == revision.revision_id
    ]
    return (
        "You are the independent Omnix coding reviewer. You are reviewing an immutable snapshot, not helping the "
        "implementer. Be adversarial about correctness, completeness, missed call sites, API compatibility, edge "
        "cases, regressions and missing tests. Do not modify files. Do not infer correctness from the implementer's "
        "claims. Inspect the diff and relevant source/callers using read-only tools.\n\n"
        f"Task revision: {revision.revision_id}\n"
        f"Objective: {revision.effective_objective}\n"
        f"Workspace state: {snapshot.workspace_state_id}\n"
        f"Requirements JSON: {json.dumps(requirements, ensure_ascii=False)}\n"
        f"Constraints JSON: {json.dumps(constraints, ensure_ascii=False)}\n"
        f"Validation results JSON: {json.dumps(validation_rows, ensure_ascii=False, default=str)}\n\n"
        "Return ONLY one JSON object with this schema:\n"
        "{\"verdict\":\"approve|changes_required|blocked\","
        "\"requirements\":[{\"requirement_id\":\"R\",\"status\":\"satisfied|partial|missing|not_applicable\",\"evidence\":\"...\"}],"
        "\"findings\":[{\"severity\":\"blocker|high|medium|low\",\"category\":\"correctness\",\"file\":null,\"location\":null,\"problem\":\"...\",\"recommended_fix\":null}],"
        "\"missing_tests\":[\"...\"],\"residual_risks\":[\"...\"]}.\n"
        "Approve only when every required task requirement is satisfied and there is no blocker/high correctness "
        "finding or material missing regression coverage."
    )


def parse_review_result(
    text: str,
    *,
    parent_run_id: str,
    reviewer_run_id: str,
    snapshot: ReviewSnapshot,
) -> ReviewResult:
    raw = str(text or "").strip()
    match = _JSON_OBJECT.search(raw)
    if match is None:
        return ReviewResult(
            run_id=parent_run_id,
            reviewer_run_id=reviewer_run_id,
            review_snapshot_id=snapshot.snapshot_id,
            task_revision_id=snapshot.task_revision_id,
            workspace_state_id=snapshot.workspace_state_id,
            verdict="blocked",
            findings=[
                ReviewFinding(
                    severity="high",
                    category="review_protocol",
                    problem="Reviewer did not return the required structured JSON verdict.",
                    recommended_fix="Re-run the independent review against the same immutable snapshot.",
                )
            ],
        )
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        payload = {}
    verdict = str(payload.get("verdict") or "blocked")
    if verdict not in {"approve", "changes_required", "blocked"}:
        verdict = "blocked"
    requirements: list[ReviewRequirementResult] = []
    for row in payload.get("requirements") or []:
        if not isinstance(row, dict):
            continue
        try:
            requirements.append(ReviewRequirementResult.model_validate(row))
        except Exception:
            continue
    findings: list[ReviewFinding] = []
    for row in payload.get("findings") or []:
        if not isinstance(row, dict):
            continue
        try:
            findings.append(ReviewFinding.model_validate(row))
        except Exception:
            continue
    return ReviewResult(
        run_id=parent_run_id,
        reviewer_run_id=reviewer_run_id,
        review_snapshot_id=snapshot.snapshot_id,
        task_revision_id=snapshot.task_revision_id,
        workspace_state_id=snapshot.workspace_state_id,
        verdict=verdict,  # type: ignore[arg-type]
        requirements=requirements,
        findings=findings,
        missing_tests=[str(item) for item in payload.get("missing_tests") or [] if str(item).strip()],
        residual_risks=[str(item) for item in payload.get("residual_risks") or [] if str(item).strip()],
    )


def review_is_acceptable(result: ReviewResult, revision: TaskRevision) -> bool:
    if result.verdict != "approve":
        return False
    required_ids = {item.id for item in revision.requirements if item.required}
    statuses = {item.requirement_id: item.status for item in result.requirements}
    if required_ids and any(statuses.get(requirement_id) != "satisfied" for requirement_id in required_ids):
        return False
    if any(item.severity in {"blocker", "high"} for item in result.findings):
        return False
    return not result.missing_tests


def quality_failure_reasons(
    snapshot: AgentRunSnapshot,
    revision: TaskRevision | None,
    workspace_state: WorkspaceState | None,
    validations: Iterable[ValidationResult],
    reviews: Iterable[ReviewResult],
    events: Iterable[AgentEvent],
) -> list[str]:
    if snapshot.spec.profile != "coding" or "diff" not in snapshot.spec.expected_artifacts:
        return []
    if snapshot.spec.quality_policy == "off":
        return []
    if workspace_state is None:
        return ["quality_workspace_state_unavailable"]
    failures: list[str] = []
    revision_id = revision.revision_id if revision is not None else None
    if workspace_state.task_revision_id != revision_id:
        failures.append("quality_workspace_state_stale_revision")

    missing = missing_final_validations(
        revision,
        validations,
        workspace_state_id=workspace_state.state_id,
    )
    failures.extend(f"quality_missing_validation:{item.id}" for item in missing)

    self_review_ok = any(
        event.event_type == "quality.self_review_completed"
        and event.payload.get("workspace_state_id") == workspace_state.state_id
        and event.payload.get("task_revision_id") == revision_id
        for event in events
    )
    if not self_review_ok:
        failures.append("quality_self_review_stale_or_missing")

    required_reviews = required_review_count(snapshot.spec, workspace_state)
    current_reviews = [
        item
        for item in reviews
        if item.workspace_state_id == workspace_state.state_id
        and item.task_revision_id == revision_id
    ]
    approved = [
        item
        for item in current_reviews
        if revision is not None and review_is_acceptable(item, revision)
    ]
    if len(approved) < required_reviews:
        failures.append("quality_independent_review_missing_or_not_approved")
    return failures


def repair_prompt(
    revision: TaskRevision,
    review: ReviewResult | None,
    missing_validation: Iterable[ValidationSpec],
    *,
    attempt: int,
) -> str:
    findings = [] if review is None else [item.model_dump(mode="json") for item in review.findings]
    missing_tests = [] if review is None else list(review.missing_tests)
    missing = [item.model_dump(mode="json") for item in missing_validation]
    return (
        f"Omnix coding quality attempt {attempt} requires repair before completion. Re-read the authoritative task "
        f"revision and stay within its scope. Objective: {revision.effective_objective}\n"
        f"Independent review findings JSON: {json.dumps(findings, ensure_ascii=False)}\n"
        f"Reviewer missing tests JSON: {json.dumps(missing_tests, ensure_ascii=False)}\n"
        f"Missing/stale final-state validation JSON: {json.dumps(missing, ensure_ascii=False)}\n"
        "Repair the implementation, inspect every impacted caller and the complete final diff, then rerun all required "
        "validation against the new final workspace state. Any previous validation/review is stale after a mutation. "
        "Do not merely explain the finding; fix it or report a concrete blocker."
    )


def self_review_prompt(revision: TaskRevision, *, attempt: int) -> str:
    requirements = [item.model_dump(mode="json") for item in revision.requirements]
    return (
        f"Mandatory engineering self-review for quality attempt {attempt}. Do not declare completion yet.\n"
        f"Authoritative requirements JSON: {json.dumps(requirements, ensure_ascii=False)}\n"
        "1. Re-read the original objective and every requirement.\n"
        "2. Inspect the COMPLETE current diff after the last edit.\n"
        "3. Search impacted callers, registrations, interfaces, generated contracts and adjacent tests.\n"
        "4. Look for missing requirements, incorrect assumptions, API incompatibilities, edge cases, regressions, "
        "temporary/debug code, duplication and scope creep.\n"
        "5. Fix every material issue you find.\n"
        "6. After the final edit, rerun the required validation. Validation from an older workspace state does not count.\n"
        "Only settle again after this self-review is actually complete."
    )


def validation_prompt(revision: TaskRevision, missing: Iterable[ValidationSpec]) -> str:
    rows = [item.model_dump(mode="json") for item in missing]
    return (
        "Final-state validation is incomplete or stale. Do not declare completion. "
        f"Required validation JSON: {json.dumps(rows, ensure_ascii=False)}\n"
        "Inspect the complete current diff and run the smallest task-relevant commands that satisfy these validation "
        "requirements against the CURRENT code. If a command fails, diagnose the implementation, fix it, and rerun. "
        "Do not substitute an unrelated passing test."
    )
