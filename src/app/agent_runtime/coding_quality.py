"""Deterministic coding-quality contracts, workspace identity and review helpers.

The LLM may implement and review code, but these helpers make completion evidence
state-bound and Omnix-authoritative. No helper in this module grants execution
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
    SelfReviewResult,
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
_BUILD = re.compile(r"\bnpm(?:\.cmd)?\s+(?:--prefix\s+\S+\s+)?run\s+build\b|\bpython\s+-m\s+build\b", re.I)
_DIFF_REVIEW = re.compile(r"\bgit\s+(?:-c\s+\S+\s+)?diff\b", re.I)
_WEB = re.compile(
    r"\b(?:react|typescript|tsx|jsx|frontend|web|css|ui|ux|theme|light\s*mode|dark\s*mode|"
    r"button|form|modal|dialog|dropdown|menu|tab|side\s*bar|sidebar|tool\s*bar|toolbar|header|footer)\b",
    re.I,
)
_BROWSER_VALIDATION = re.compile(
    r"\b(?:agent[- ]browser|browser\s+(?:test|testing|validation|verify|verification)|"
    r"e2e|end[- ]to[- ]end|playwright|visual\s+(?:test|testing|validation|regression)|"
    r"click\s+through|interact\s+with\s+(?:the\s+)?(?:page|ui|app))\b",
    re.I,
)
_BROWSER_FORBIDDEN = re.compile(
    r"\b(?:do not|don't|never|without)\s+(?:use|open|run|launch)?\s*(?:the\s+)?"
    r"(?:browser|agent[- ]browser|playwright)\b",
    re.I,
)
_BROWSER_ASSERTIONS = {
    "browser.assert_text_contains",
    "browser.assert_text_not_contains",
    "browser.assert_attribute_contains",
    "browser.assert_url_contains",
}
_CRITICAL = re.compile(
    r"(?:agent_runtime|approval|authority|capabilit|security|auth(?:entication|orization)?|"
    r"trading|order|broker|payment|migration|persistence|credential|secret|publish|deploy)",
    re.I,
)
_PATH_TOKEN = re.compile(r"(?<![A-Za-z0-9_.-])(?:src|tests?|packages?|apps?|docs?)[/\\][A-Za-z0-9_./\\-]+")
_REVIEW_VERDICTS = {"approve", "changes_required", "blocked"}


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
    """Derive engineering obligations while retaining requirement provenance."""
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
                    description="Preserve unrelated behavior and add or update regression coverage for changed behavior.",
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
            validation.append(
                ValidationSpec(
                    id="browser-validation",
                    kind="browser",
                    description=(
                        "Exercise the changed UI through the governed browser and prove the exact requested final "
                        "state with a deterministic browser assertion. For removal/hiding work, use "
                        "browser.assert_text_not_contains on the stable containing surface; positive-state work "
                        "may use browser.assert_text_contains, browser.assert_attribute_contains, or "
                        "browser.assert_url_contains."
                    ),
                    covers=["user-objective", "derived-regression-safety"],
                    required=bool(
                        not _BROWSER_FORBIDDEN.search(objective_text)
                        and (_WEB.search(objective_text) or _BROWSER_VALIDATION.search(objective_text))
                    ),
                    command_hint="Use governed browser.* capabilities via omnix_capability",
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
    tracked_digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
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



def validation_kind_for_capability(capability_id: str) -> str | None:
    value = str(capability_id or "").strip()
    return "browser" if value in _BROWSER_ASSERTIONS else None

def _validation_plan(revision: TaskRevision | None) -> list[ValidationSpec]:
    if revision is None:
        return []
    return [
        item if isinstance(item, ValidationSpec) else ValidationSpec.model_validate(item)
        for item in revision.validation_plan
    ]


def validation_id_for_kind(kind: str, revision: TaskRevision | None) -> str:
    plan = _validation_plan(revision)
    for item in plan:
        if item.kind == kind:
            return item.id
    return {
        "diff_review": "final-diff-review",
        "test": "final-state-tests",
        "typecheck": "requested-typecheck",
        "lint": "requested-lint",
        "build": "frontend-build-or-typecheck",
        "browser": "browser-validation",
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
    capability_id = str(args.get("capability_id") or event.payload.get("capability_id") or "").strip()
    command = str(args.get("command") or event.payload.get("command") or "").strip()
    if validation_kind_for_capability(capability_id) == "browser":
        kind = "browser"
        command = f"omnix_capability {capability_id}"
    else:
        kind = validation_kind_for_command(command)
    if kind is None:
        return None
    success = not bool(event.payload.get("is_error")) and not bool(event.payload.get("error"))
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
        if kind == "browser":
            broker = details if "executed" in details else details.get("result")
            if isinstance(broker, dict):
                if broker.get("executed") is False or broker.get("error"):
                    success = False
                nested = broker.get("result")
                if isinstance(nested, dict) and nested.get("error"):
                    success = False
    output_digest = hashlib.sha256(
        json.dumps(result, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    call_id = str(event.payload.get("tool_call_id") or event.event_id)
    result_id = hashlib.sha256(
        f"{run_id}:{task_revision_id}:{call_id}:{workspace_state_id}:{kind}".encode("utf-8")
    ).hexdigest()
    validation_id = validation_id_for_kind(kind, revision)
    validation_spec = next((item for item in _validation_plan(revision) if item.id == validation_id), None)
    covers_requirement_ids = list(validation_spec.covers) if validation_spec is not None else []
    return ValidationResult(
        result_id=result_id,
        run_id=run_id,
        validation_id=validation_id,
        kind=kind,
        task_revision_id=task_revision_id,
        workspace_state_id=workspace_state_id,
        command=command,
        exit_code=exit_code,
        success=success,
        output_digest=output_digest,
        covers_requirement_ids=covers_requirement_ids,
        finished_at=event.created_at,
        metadata={"tool_call_id": call_id, "capability_id": capability_id or None},
    )


def missing_final_validations(
    revision: TaskRevision | None,
    results: Iterable[ValidationResult],
    *,
    workspace_state_id: str,
) -> list[ValidationSpec]:
    plan = _validation_plan(revision)
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
        expected_coverage = set(expected.covers)
        if not any(
            observed.validation_id == expected.id
            and expected_coverage.issubset(set(observed.covers_requirement_ids))
            for observed in current
        ):
            missing.append(expected)
    return missing


def relevant_file_candidates(revision: TaskRevision | None, state: WorkspaceState) -> list[str]:
    paths = list(state.modified_paths)
    objective = revision.effective_objective if revision is not None else ""
    for match in _PATH_TOKEN.finditer(objective):
        path = match.group(0).replace("\\", "/").rstrip(".,:;)]}")
        if path not in paths:
            paths.append(path)
    return paths[:80]


def _workspace_matches_state(spec: AgentRunSpec, state: WorkspaceState, workspace: WorkspaceSpec) -> bool:
    observed = capture_workspace_state(spec.model_copy(update={"workspace": workspace}), task_revision_id=state.task_revision_id)
    return bool(observed is not None and observed.state_id == state.state_id and observed.base_commit_sha == state.base_commit_sha)


def review_workspace_matches_snapshot(spec: AgentRunSpec, snapshot: ReviewSnapshot) -> bool:
    parent = spec.workspace
    if parent is None:
        return False
    workspace = WorkspaceSpec(
        root=snapshot.workspace_root,
        repository=parent.repository or parent.root,
        base_ref=snapshot.base_commit_sha,
        worktree=snapshot.workspace_root,
        isolation_policy="immutable_review_snapshot",
        allowed_paths=list(parent.allowed_paths),
        forbidden_paths=list(parent.forbidden_paths),
    )
    expected = WorkspaceState(
        state_id=snapshot.workspace_state_id,
        run_id=spec.run_id,
        task_revision_id=snapshot.task_revision_id,
        base_commit_sha=snapshot.base_commit_sha,
        tracked_diff_sha256="",
        untracked_file_manifest_sha256="",
    )
    return _workspace_matches_state(spec, expected, workspace)


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
        review_workspace = WorkspaceSpec(
            root=str(target), repository=str(repository), base_ref=state.base_commit_sha,
            worktree=str(target), isolation_policy="immutable_review_snapshot",
            allowed_paths=list(workspace.allowed_paths), forbidden_paths=list(workspace.forbidden_paths),
        )
        if _workspace_matches_state(spec, state, review_workspace):
            return review_workspace
        raise WorkspacePolicyError("existing review snapshot no longer reproduces the bound WorkspaceState")
    target.parent.mkdir(parents=True, exist_ok=True)
    WorkspaceAuthority.create_worktree(repository, target, base_ref=state.base_commit_sha)
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
        review_workspace = WorkspaceSpec(
            root=str(target),
            repository=str(repository),
            base_ref=state.base_commit_sha,
            worktree=str(target),
            isolation_policy="immutable_review_snapshot",
            allowed_paths=list(workspace.allowed_paths),
            forbidden_paths=list(workspace.forbidden_paths),
        )
        observed_spec = spec.model_copy(update={"workspace": review_workspace})
        observed = capture_workspace_state(observed_spec, task_revision_id=state.task_revision_id)
        if observed is None or observed.state_id != state.state_id:
            raise WorkspacePolicyError("review snapshot does not reproduce parent workspace state")
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return review_workspace


def review_payload_from_text(text: str) -> dict[str, object]:
    """Decode the first review object from plain or fenced model output.

    Providers do not all honor ``ONLY JSON`` consistently. Using the JSON
    decoder from each object boundary accepts a valid object surrounded by a
    short preamble or Markdown fence without letting unrelated prose become an
    approval. A verdict is required before the payload is considered review
    evidence.
    """

    raw = str(text or "").strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(raw):
        if character != "{":
            continue
        try:
            decoded, _end = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(decoded, dict):
            continue
        if str(decoded.get("verdict") or "") in _REVIEW_VERDICTS:
            return decoded
    return {}


def parse_self_review_result(text: str, *, run_id: str, revision: TaskRevision, workspace_state_id: str) -> SelfReviewResult:
    payload = review_payload_from_text(text)
    verdict = str(payload.get("verdict") or "blocked")
    if verdict not in _REVIEW_VERDICTS:
        verdict = "blocked"
    requirements: list[ReviewRequirementResult] = []
    for row in payload.get("requirements") or []:
        if isinstance(row, dict):
            try:
                requirements.append(ReviewRequirementResult.model_validate(row))
            except Exception:
                pass
    findings: list[ReviewFinding] = []
    for row in payload.get("findings") or []:
        if isinstance(row, dict):
            try:
                findings.append(ReviewFinding.model_validate(row))
            except Exception:
                pass
    if not payload:
        findings.append(ReviewFinding(severity="high", category="self_review_protocol", problem="Implementer did not return the required structured self-review JSON.", recommended_fix="Repeat the mandatory self-review against the same final state."))
    return SelfReviewResult(
        run_id=run_id, task_revision_id=revision.revision_id, workspace_state_id=workspace_state_id,
        verdict=verdict, requirements=requirements, findings=findings,
        missing_tests=[str(item) for item in payload.get("missing_tests") or [] if str(item).strip()],
        residual_risks=[str(item) for item in payload.get("residual_risks") or [] if str(item).strip()],
    )


def self_review_is_acceptable(result: SelfReviewResult, revision: TaskRevision) -> bool:
    if result.verdict != "approve":
        return False
    required_ids = {item.id for item in revision.requirements if item.required}
    statuses = {item.requirement_id: item.status for item in result.requirements}
    if required_ids and any(statuses.get(item) != "satisfied" for item in required_ids):
        return False
    if any(item.severity in {"blocker", "high"} for item in result.findings):
        return False
    return not result.missing_tests


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
    payload = review_payload_from_text(raw)
    if not payload:
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
    verdict = str(payload.get("verdict") or "blocked")
    if verdict not in _REVIEW_VERDICTS:
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
        verdict=verdict,
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
    self_reviews: Iterable[SelfReviewResult],
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
        isinstance(item, SelfReviewResult)
        and item.workspace_state_id == workspace_state.state_id
        and item.task_revision_id == revision_id
        and revision is not None
        and self_review_is_acceptable(item, revision)
        for item in self_reviews
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
    review: ReviewResult | SelfReviewResult | None,
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
        "Do not merely explain the finding; fix it or report a concrete blocker. Do not ask the user to restate the "
        "already-authoritative objective or wait for clarification."
    )


def self_review_prompt(
    revision: TaskRevision,
    *,
    attempt: int,
    validations: Iterable[ValidationResult] = (),
) -> str:
    requirements = [item.model_dump(mode="json") for item in revision.requirements]
    required_requirement_ids = [item.id for item in revision.requirements if item.required]
    required_validation_ids = {item.id for item in _validation_plan(revision) if item.required}
    latest_validations: dict[str, ValidationResult] = {}
    for item in validations:
        if item.validation_id not in required_validation_ids:
            continue
        previous = latest_validations.get(item.validation_id)
        if previous is None or item.finished_at >= previous.finished_at:
            latest_validations[item.validation_id] = item
    validation_rows = [
        {
            "validation_id": item.validation_id,
            "kind": item.kind,
            "command": item.command,
            "success": item.success,
            "workspace_state_id": item.workspace_state_id,
        }
        for item in sorted(latest_validations.values(), key=lambda row: row.validation_id)
    ]
    schema = {
        "verdict": "approve|changes_required|blocked",
        "requirements": [
            {
                "requirement_id": "R",
                "status": "satisfied|partial|missing|not_applicable",
                "evidence": "...",
            }
        ],
        "findings": [
            {
                "severity": "blocker|high|medium|low",
                "category": "correctness",
                "file": None,
                "location": None,
                "problem": "...",
                "recommended_fix": None,
            }
        ],
        "missing_tests": [],
        "residual_risks": [],
    }
    return (
        f"Mandatory engineering self-review for quality attempt {attempt}. Do not declare completion yet.\n"
        f"Authoritative implementation objective: {revision.effective_objective}\n"
        f"Authoritative requirements JSON: {json.dumps(requirements, ensure_ascii=False)}\n"
        f"Required requirement IDs JSON: {json.dumps(required_requirement_ids, ensure_ascii=False)}\n"
        f"Recorded required-validation evidence JSON: {json.dumps(validation_rows, ensure_ascii=False)}\n"
        "The implementation turn has ended. This is a read-only verdict turn: do not call tools, edit files, rerun "
        "commands, or send a progress update. Review the complete diff, callers, interfaces, edge cases, regression "
        "coverage, and recorded validation evidence already present in the conversation. If more work is needed, return "
        "changes_required and describe it; Omnix will open a separate repair turn. This internal quality turn must "
        "never ask the user a question or request a missing implementation brief. The requirements array must contain "
        "one result for every required requirement ID listed above. In the first response, return the verdict even if "
        "the result is blocked.\n"
        f"Return ONLY one JSON object matching this schema: {json.dumps(schema, ensure_ascii=False)}"
    )


def validation_prompt(revision: TaskRevision, missing: Iterable[ValidationSpec]) -> str:
    rows = [item.model_dump(mode="json") for item in missing]
    return (
        "Final-state validation is incomplete or stale. Do not declare completion. "
        f"Required validation JSON: {json.dumps(rows, ensure_ascii=False)}\n"
        "Inspect the complete current diff and run the smallest task-relevant commands that satisfy these validation "
        "requirements against the CURRENT code. If a command fails, diagnose the implementation, fix it, and rerun. "
        "Do not substitute an unrelated passing test. For browser validation, interact with the governed "
        "browser as needed and finish with a deterministic browser.assert_* capability that proves the exact "
        "requested final state; a screenshot or snapshot alone is not completion evidence. For remove/hide/absence "
        "requests, use browser.assert_text_not_contains against the stable containing UI surface so a generic "
        "passing test cannot substitute for proof that the control is actually gone."
    )
