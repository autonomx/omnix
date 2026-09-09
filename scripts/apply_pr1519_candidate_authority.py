from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"replacement anchor missing in {path}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


def replace_regex(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count == 0:
        # Idempotent reruns see the replacement marker.
        if replacement[:80] in text:
            return
        raise RuntimeError(f"regex anchor missing in {path}: {pattern[:120]!r}")
    write(path, updated)


# ---------------------------------------------------------------------------
# Contracts: exact candidate != authoritative run-owned subject.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/contracts.py",
    'ValidationKind = Literal["test", "typecheck", "lint", "build", "diff_review", "browser", "custom"]\n',
    'ValidationKind = Literal["test", "typecheck", "lint", "build", "diff_review", "browser", "custom"]\n'
    'ValidationOutcome = Literal[\n'
    '    "passed",\n'
    '    "substantive_failure",\n'
    '    "infrastructure_failure",\n'
    '    "protocol_failure",\n'
    '    "blocked",\n'
    ']\n'
    'ReviewFindingAttribution = Literal[\n'
    '    "run_owned",\n'
    '    "run_owned_dependency",\n'
    '    "baseline_context",\n'
    '    "unattributed",\n'
    ']\n',
)
replace_once(
    "src/app/agent_runtime/contracts.py",
    '    "quality.validation_recorded",\n',
    '    "quality.validation_recorded",\n'
    '    "quality.validation_requested",\n'
    '    "quality.validation_retry_requested",\n'
    '    "quality.validation_retry_exhausted",\n'
    '    "quality.validation_repair_requested",\n',
)
replace_once(
    "src/app/agent_runtime/contracts.py",
    '''class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
''',
    '''class RunChangeSet(BaseModel):
    """Canonical run-owned change subject bound to one exact candidate state.

    WorkspaceState intentionally contains the entire exact checkout, including
    dirties that predated the run. RunChangeSet is the smaller authoritative
    subject Omnix attributes to the run and presents to validation/review.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    change_set_id: str
    run_id: str
    task_revision_id: str | None = None
    baseline_id: str
    baseline_head_sha: str
    candidate_workspace_state_id: str
    run_owned_paths: list[str] = Field(default_factory=list)
    baseline_context_paths: list[str] = Field(default_factory=list)
    tracked_patch_sha256: str
    patch_checksum: str
    patch_storage_ref: str
    untracked_manifest: dict[str, dict[str, Any]] = Field(default_factory=dict)
    deletions: list[str] = Field(default_factory=list)
    renames: list[dict[str, str]] = Field(default_factory=list)
    mode_changes: list[str] = Field(default_factory=list)
    baseline_conflicts: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
''',
)
replace_once(
    "src/app/agent_runtime/contracts.py",
    '''    success: bool
    output_digest: str
''',
    '''    success: bool
    outcome: ValidationOutcome = "passed"
    output_digest: str
''',
)
replace_once(
    "src/app/agent_runtime/contracts.py",
    '''class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["blocker", "high", "medium", "low"] = "medium"
    category: str = "correctness"
    file: str | None = None
    location: str | None = None
    problem: str
    recommended_fix: str | None = None
''',
    '''class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["blocker", "high", "medium", "low"] = "medium"
    category: str = "correctness"
    file: str | None = None
    location: str | None = None
    problem: str
    recommended_fix: str | None = None
    # The reviewer supplies path claims only. Attribution/blocking are rewritten
    # by Omnix against the authoritative RunChangeSet before persistence.
    subject_paths: list[str] = Field(default_factory=list)
    context_paths: list[str] = Field(default_factory=list)
    attribution: ReviewFindingAttribution = "unattributed"
    blocking: bool = False
''',
)
replace_once(
    "src/app/agent_runtime/contracts.py",
    '''    patch_storage_ref: str | None = None
    workspace_root: str
    relevant_files: list[str] = Field(default_factory=list)
''',
    '''    patch_storage_ref: str | None = None
    run_change_set_id: str | None = None
    workspace_root: str
    subject_paths: list[str] = Field(default_factory=list)
    context_paths: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
''',
)
replace_once(
    "src/app/agent_runtime/contracts.py",
    '''class AgentRunUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
''',
    '''class AgentRunUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    input_tokens_reported: bool = False
    output_tokens_reported: bool = False
''',
)

# ---------------------------------------------------------------------------
# Canonical RunChangeSet helpers.
# ---------------------------------------------------------------------------
write(
    "src/app/agent_runtime/run_change_set.py",
    '''"""Canonical run-owned change-set identity and artifact hydration."""
from __future__ import annotations

import hashlib
import json
import re

from .contracts import AgentArtifact, RunChangeSet


def baseline_identity(head: str, dirty_paths: list[str], dirty_digests: dict[str, str]) -> str:
    payload = {
        "head": str(head or ""),
        "dirty_paths": sorted(str(path).replace("\\\\", "/") for path in dirty_paths),
        "dirty_digests": {
            str(path).replace("\\\\", "/"): str(value)
            for path, value in sorted(dirty_digests.items())
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def patch_structure(patch: str) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """Extract deletion/rename/mode metadata from the authoritative tracked patch."""
    deletions: set[str] = set()
    renames: list[dict[str, str]] = []
    mode_changes: set[str] = set()
    current = ""
    rename_from: str | None = None
    old_mode = False
    for line in str(patch or "").splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            current = parts[3][2:] if len(parts) >= 4 and parts[3].startswith("b/") else ""
            rename_from = None
            old_mode = False
        elif line.startswith("deleted file mode ") and current:
            deletions.add(current)
        elif line.startswith("rename from "):
            rename_from = line[len("rename from "):].strip()
        elif line.startswith("rename to "):
            target = line[len("rename to "):].strip()
            if rename_from:
                renames.append({"from": rename_from, "to": target})
            rename_from = None
        elif line.startswith("old mode "):
            old_mode = True
        elif line.startswith("new mode ") and current and old_mode:
            mode_changes.add(current)
            old_mode = False
    return sorted(deletions), renames, sorted(mode_changes)


def run_change_set_from_artifact(artifact: AgentArtifact | None) -> RunChangeSet | None:
    if artifact is None or artifact.kind != "diff":
        return None
    payload = artifact.metadata.get("run_change_set")
    if not isinstance(payload, dict):
        return None
    try:
        return RunChangeSet.model_validate(payload)
    except Exception:
        return None
''',
)

# ---------------------------------------------------------------------------
# Workspace tracked/untracked separation. Exact WorkspaceState remains unchanged.
# ---------------------------------------------------------------------------
replace_regex(
    "src/app/agent_runtime/workspace.py",
    r'''    def git_diff\(self, paths: list\[str\] \| None = None\) -> str:\n.*?\n    def _untracked_file_diff''',
    '''    def git_tracked_diff(self, paths: list[str] | None = None) -> str:
        scoped_paths = [
            str(path).replace("\\\\", "/")
            for path in (paths or [])
            if str(path).strip()
        ]
        if paths is not None and not scoped_paths:
            return ""
        argv = ["git", "diff", "--no-ext-diff", "--find-renames", "--"]
        if paths is not None:
            argv.extend(scoped_paths)
        result = self.run_command(argv)
        if result.returncode != 0:
            raise WorkspacePolicyError(result.stderr or "git diff failed")
        return result.stdout

    def git_diff(self, paths: list[str] | None = None) -> str:
        scoped_paths = [
            str(path).replace("\\\\", "/")
            for path in (paths or [])
            if str(path).strip()
        ]
        if paths is not None and not scoped_paths:
            return ""
        diff = self.git_tracked_diff(paths)
        if paths is None:
            return diff
        entries = self.git_status_entries()
        for relative in scoped_paths:
            if entries.get(relative) == "??":
                diff += self._untracked_file_diff(relative)
        return diff

    def _untracked_file_diff''',
)

# ---------------------------------------------------------------------------
# Core service: immutable baseline id + one canonical RunChangeSet artifact.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/service_core.py",
    '    TaskRevision,\n    WorkspaceSpec,\n)',
    '    TaskRevision,\n    RunChangeSet,\n    WorkspaceSpec,\n)',
)
replace_once(
    "src/app/agent_runtime/service_core.py",
    'from .workspace import WorkspaceAuthority\n',
    'from .workspace import WorkspaceAuthority\nfrom .run_change_set import baseline_identity, patch_structure, run_change_set_from_artifact\n',
)
replace_regex(
    "src/app/agent_runtime/service_core.py",
    r'''    def _capture_workspace_baseline\(\n.*?\n    def _capture_diff\(''',
    '''    def _capture_workspace_baseline(
        self,
        repository: PostgresAgentRunRepository,
        spec: AgentRunSpec,
    ) -> None:
        if spec.workspace is None or "diff" not in spec.expected_artifacts:
            return
        root = spec.workspace.worktree or spec.workspace.root
        baseline = WorkspaceAuthority(root).provenance_snapshot()
        dirty_paths = list(baseline["dirty_paths"])
        dirty_digests = {str(key): str(value) for key, value in dict(baseline["dirty_digests"]).items()}
        baseline_id = baseline_identity(str(baseline["head"]), dirty_paths, dirty_digests)
        repository.add_artifact(
            AgentArtifact(
                artifact_id=f"baseline-{baseline_id}",
                run_id=spec.run_id,
                kind="other",
                name="workspace-baseline.json",
                metadata={
                    "baseline_id": baseline_id,
                    "head": baseline["head"],
                    "dirty_paths": dirty_paths,
                    "dirty_digests": dirty_digests,
                },
            )
        )

    def _capture_diff(''',
)
replace_regex(
    "src/app/agent_runtime/service_core.py",
    r'''    def _capture_diff\(\n.*?\n    def recover_orphaned_runs''',
    '''    def _capture_diff(
        self,
        repository: PostgresAgentRunRepository,
        spec: AgentRunSpec,
        *,
        task_revision_id: str | None = None,
        workspace_state_id: str | None = None,
    ) -> RunChangeSet | None:
        """Capture/reuse the canonical baseline-relative RunChangeSet.

        The exact checkout remains represented by WorkspaceState. This artifact
        contains only run-owned paths; baseline-dirty paths are context and any
        attempted mutation of them is reported separately as a baseline conflict.
        """
        if spec.workspace is None:
            return None
        root = spec.workspace.worktree or spec.workspace.root
        try:
            authority = WorkspaceAuthority(root)
            baseline_artifact = next(
                (
                    artifact
                    for artifact in repository.list_artifacts(spec.run_id)
                    if artifact.name == "workspace-baseline.json"
                ),
                None,
            )
            if baseline_artifact is None:
                log_agent_activity(
                    "service.diff_capture.skipped_no_baseline",
                    category="quality",
                    level="warning",
                    run_id=spec.run_id,
                    fields={"workspace": str(root), "task_revision_id": task_revision_id},
                )
                return None
            baseline_metadata = baseline_artifact.metadata
            dirty_paths = [
                str(path).replace("\\\\", "/")
                for path in (
                    baseline_metadata.get("dirty_paths")
                    if isinstance(baseline_metadata.get("dirty_paths"), list)
                    else []
                )
            ]
            dirty_digests = {
                str(key).replace("\\\\", "/"): str(value)
                for key, value in (
                    baseline_metadata.get("dirty_digests")
                    if isinstance(baseline_metadata.get("dirty_digests"), dict)
                    else {}
                ).items()
            }
            head = str(baseline_metadata.get("head") or authority.git_head())
            baseline_id = str(baseline_metadata.get("baseline_id") or baseline_identity(head, dirty_paths, dirty_digests))
            status_entries = authority.git_status_entries()
            modified_paths = authority.run_owned_paths(dirty_paths)
            baseline_conflicts = authority.baseline_conflicts(dirty_digests)
            tracked_patch = authority.git_tracked_diff(modified_paths)
            untracked_paths = [path for path in modified_paths if status_entries.get(path) == "??"]
            untracked_patch = authority.git_diff(untracked_paths) if untracked_paths else ""
            patch = tracked_patch + untracked_patch
            tracked_digest = hashlib.sha256(tracked_patch.encode("utf-8")).hexdigest()
            untracked_digests = {path: authority.file_digest(path) for path in untracked_paths}
            candidate_id = str(workspace_state_id or hashlib.sha256(
                f"{authority.git_head()}:{hashlib.sha256(patch.encode('utf-8')).hexdigest()}".encode("utf-8")
            ).hexdigest())
            identity_payload = {
                "run_id": spec.run_id,
                "task_revision_id": task_revision_id,
                "baseline_id": baseline_id,
                "candidate_workspace_state_id": candidate_id,
                "run_owned_paths": modified_paths,
                "tracked_patch_sha256": tracked_digest,
                "untracked_digests": untracked_digests,
                "baseline_conflicts": baseline_conflicts,
            }
            change_set_id = hashlib.sha256(
                json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            for artifact in reversed(repository.list_artifacts(spec.run_id)):
                existing = run_change_set_from_artifact(artifact)
                if existing is not None and existing.change_set_id == change_set_id:
                    return existing
        except Exception as exc:
            log_agent_activity(
                "service.diff_capture.failed",
                category="quality",
                level="error",
                run_id=spec.run_id,
                fields={"workspace": str(root)},
                error=exc,
                include_traceback=True,
            )
            return None

        workspace_key = hashlib.sha256(self.context.workspace_id.encode("utf-8")).hexdigest()[:16]
        run_key = hashlib.sha256(spec.run_id.encode("utf-8")).hexdigest()
        base_key = f"agent/runs/{workspace_key}/{run_key}/changesets/{change_set_id}"
        untracked_manifest: dict[str, dict[str, object]] = {}
        for relative, digest in untracked_digests.items():
            entry: dict[str, object] = {"sha256": digest, "content_storage_ref": None}
            try:
                source = authority.resolve_path(relative)
                if source.is_file():
                    content_blob = self.blob_store.put_bytes(
                        f"{base_key}/untracked/{hashlib.sha256(relative.encode('utf-8')).hexdigest()}.bin",
                        source.read_bytes(),
                    )
                    entry["content_storage_ref"] = str(content_blob["storage_key"])
            except Exception:
                entry["content_storage_ref"] = None
            untracked_manifest[relative] = entry

        patch_blob = self.blob_store.put_bytes(f"{base_key}/run-owned.patch", patch.encode("utf-8"))
        deletions, renames, mode_changes = patch_structure(tracked_patch)
        change_set = RunChangeSet(
            change_set_id=change_set_id,
            run_id=spec.run_id,
            task_revision_id=task_revision_id,
            baseline_id=baseline_id,
            baseline_head_sha=head,
            candidate_workspace_state_id=candidate_id,
            run_owned_paths=modified_paths,
            baseline_context_paths=dirty_paths,
            tracked_patch_sha256=tracked_digest,
            patch_checksum=str(patch_blob["checksum_sha256"]),
            patch_storage_ref=str(patch_blob["storage_key"]),
            untracked_manifest=untracked_manifest,
            deletions=deletions,
            renames=renames,
            mode_changes=mode_changes,
            baseline_conflicts=baseline_conflicts,
        )
        preview_limit = 16_000
        file_stats = _diff_file_stats(patch, modified_paths)
        repository.add_artifact(
            AgentArtifact(
                artifact_id=change_set_id,
                run_id=spec.run_id,
                kind="diff",
                name="run-change-set.patch",
                storage_ref=change_set.patch_storage_ref,
                checksum=change_set.patch_checksum,
                metadata={
                    "task_revision_id": task_revision_id,
                    "workspace_state_id": candidate_id,
                    "run_change_set_id": change_set_id,
                    "run_change_set": change_set.model_dump(mode="json"),
                    "storage_provider": str(patch_blob["storage_provider"]),
                    "byte_size": int(patch_blob["byte_size"]),
                    "preview": patch[:preview_limit],
                    "truncated": len(patch) > preview_limit,
                    "modified_paths": modified_paths,
                    "file_stats": file_stats,
                    "additions": sum(item["additions"] for item in file_stats),
                    "deletions": sum(item["deletions"] for item in file_stats),
                    "baseline_conflicts": baseline_conflicts,
                    "baseline_id": baseline_id,
                },
            )
        )
        return change_set

    def recover_orphaned_runs''',
)

# ---------------------------------------------------------------------------
# Quality helpers: canonical change-set inspection, structural outcomes, and
# server-derived finding attribution.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '    ReviewResult,\n    ReviewSnapshot,\n',
    '    ReviewResult,\n    ReviewSnapshot,\n    RunChangeSet,\n',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''                ValidationSpec(
                    id="final-diff-review",
                    kind="diff_review",
                    description="Inspect the complete final diff after the last implementation change.",
                    covers=[item.id for item in requirements if item.required],
                    required=True,
                    command_hint="git diff --no-ext-diff",
                ),
''',
    '''                ValidationSpec(
                    id="final-diff-review",
                    kind="diff_review",
                    description=(
                        "Inspect the complete authoritative run-owned RunChangeSet after the last implementation change."
                    ),
                    covers=[item.id for item in requirements if item.required],
                    required=True,
                    command_hint="Use the Omnix Run Change Set tool",
                ),
''',
)
replace_regex(
    "src/app/agent_runtime/coding_quality.py",
    r'''def diff_review_command_is_complete\(command: str\) -> bool:\n.*?\n\ndef validation_kind_for_command''',
    '''def diff_review_command_is_complete(command: str) -> bool:
    """Shell git diff is never authoritative final-diff evidence.

    It cannot encode the start-of-run baseline contract and ordinary git diff
    omits untracked contents. Final-diff validation is satisfied only by the
    Omnix RunChangeSet tool bound to the exact candidate state.
    """
    del command
    return False


def validation_kind_for_command''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''    if _DIFF_REVIEW.search(value):
        return "diff_review"
    if _TYPECHECK.search(value):
''',
    '''    # git diff remains useful inspection, but it is not validation authority.
    if _TYPECHECK.search(value):
''',
)
replace_regex(
    "src/app/agent_runtime/coding_quality.py",
    r'''def validation_result_from_tool_event\(\n.*?\n\ndef missing_final_validations''',
    '''def _validation_outcome_from_error_text(text: str) -> str:
    folded = str(text or "").casefold()
    if any(token in folded for token in ("timeout", "timed out", "spawn", "enoent", "connection", "unavailable", "broker", "transport")):
        return "infrastructure_failure"
    if any(token in folded for token in ("permission", "approval", "blocked", "outside_run", "not_issued")):
        return "blocked"
    return "protocol_failure"


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
    tool_name = str(event.payload.get("tool") or "").strip()
    capability_id = str(args.get("capability_id") or event.payload.get("capability_id") or "").strip()
    command = str(args.get("command") or event.payload.get("command") or "").strip()
    if tool_name == "omnix_change_set":
        kind = "diff_review"
        command = "omnix_change_set"
    elif validation_kind_for_capability(capability_id) == "browser":
        kind = "browser"
        command = f"omnix_capability {capability_id}"
    else:
        kind = validation_kind_for_command(command)
    if kind is None:
        return None

    result = event.payload.get("result")
    details = result.get("details") if isinstance(result, dict) and isinstance(result.get("details"), dict) else result
    details = details if isinstance(details, dict) else {}
    raw_exit = details.get("exitCode", details.get("exit_code"))
    exit_code: int | None = None
    if raw_exit is not None:
        try:
            exit_code = int(raw_exit)
        except (TypeError, ValueError):
            exit_code = None

    error_text = str(event.payload.get("error") or "")
    if isinstance(result, dict):
        error_text = error_text or str(result.get("error") or "")
    outcome = "passed"
    failure_class: str | None = None

    if kind == "diff_review":
        change_set = details.get("change_set") if isinstance(details.get("change_set"), dict) else {}
        candidate = str(change_set.get("candidate_workspace_state_id") or details.get("candidate_workspace_state_id") or "")
        if event.payload.get("is_error") or error_text:
            outcome = _validation_outcome_from_error_text(error_text)
        elif not change_set or candidate != workspace_state_id:
            outcome = "protocol_failure"
        else:
            outcome = "passed"
    elif kind == "browser":
        broker = details if "executed" in details else details.get("result")
        broker = broker if isinstance(broker, dict) else {}
        nested = broker.get("result") if isinstance(broker.get("result"), dict) else {}
        browser_error = str(broker.get("error") or nested.get("error") or error_text or "")
        if not browser_error and broker.get("executed") is not False and not event.payload.get("is_error"):
            outcome = "passed"
        elif browser_error.startswith("browser_policy_rejected:"):
            outcome, failure_class = "protocol_failure", "input_contract"
        elif browser_error in {"browser_runtime_unavailable", "browser_command_failed"} or browser_error.startswith("browser_runtime_error:"):
            outcome, failure_class = "infrastructure_failure", "infrastructure"
        elif browser_error == "browser_assertion_failed":
            outcome, failure_class = "substantive_failure", "assertion"
        else:
            outcome, failure_class = "blocked", "blocked"
    else:
        # A normally executed command returning nonzero is substantive evidence
        # against this exact candidate. Unknown nonzero results fail closed as
        # substantive rather than being endlessly retried as infrastructure.
        if exit_code is not None:
            outcome = "passed" if exit_code == 0 else "substantive_failure"
            if exit_code != 0:
                failure_class = "command_failed"
        elif event.payload.get("is_error") or error_text:
            outcome = _validation_outcome_from_error_text(error_text or json.dumps(result, default=str))
            failure_class = outcome
        else:
            outcome = "protocol_failure"
            failure_class = "missing_exit_status"

    success = outcome == "passed"
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
    metadata: dict[str, object] = {
        "tool_call_id": call_id,
        "capability_id": capability_id or None,
        "outcome": outcome,
    }
    if failure_class:
        metadata["failure_class"] = failure_class
    if kind == "diff_review":
        change_set = details.get("change_set") if isinstance(details.get("change_set"), dict) else {}
        if change_set:
            metadata["run_change_set_id"] = change_set.get("change_set_id")
    if kind == "browser":
        capability_input = args.get("input") if isinstance(args.get("input"), dict) else {}
        expected = capability_input.get("expected")
        if expected is not None and expected != "":
            metadata["assertion_expected"] = str(expected)
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
        outcome=outcome,
        output_digest=output_digest,
        covers_requirement_ids=covers_requirement_ids,
        finished_at=event.created_at,
        metadata=metadata,
    )


def candidate_validation_gate(
    revision: TaskRevision | None,
    results: Iterable[ValidationResult],
    *,
    workspace_state_id: str,
) -> tuple[str, list[ValidationResult | ValidationSpec]]:
    """Classify required validation for one candidate, independent of quality attempt."""
    plan = [item for item in _validation_plan(revision) if item.required]
    rows = [
        item for item in results
        if item.workspace_state_id == workspace_state_id
        and (revision is None or item.task_revision_id == revision.revision_id)
    ]
    substantive: list[ValidationResult] = []
    retryable: list[ValidationResult] = []
    missing: list[ValidationSpec] = []
    for expected in plan:
        matching = [item for item in rows if item.validation_id == expected.id]
        if any(item.outcome == "passed" and item.success for item in matching):
            continue
        if not matching:
            missing.append(expected)
            continue
        latest = max(matching, key=lambda item: (item.finished_at, item.result_id))
        if latest.outcome in {"infrastructure_failure", "protocol_failure"}:
            retryable.append(latest)
        else:
            substantive.append(latest)
    if substantive:
        return "validation_repair", substantive
    if retryable:
        return "validation_retry", retryable
    if missing:
        return "validation_missing", missing
    return "passed", []


def missing_final_validations''',
)
# Let the existing helper continue to represent only missing passing evidence.

# Normalize reviewer findings against authoritative subject/context paths.
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''def parse_review_result(
    text: str,
    *,
    parent_run_id: str,
    reviewer_run_id: str,
    snapshot: ReviewSnapshot,
) -> ReviewResult:
''',
    '''def _normalized_review_path(value: object) -> str:
    return str(value or "").strip().replace("\\\\", "/").lstrip("./")


def _authoritative_review_finding(finding: ReviewFinding, snapshot: ReviewSnapshot) -> ReviewFinding:
    subject = {_normalized_review_path(path) for path in snapshot.subject_paths if _normalized_review_path(path)}
    context = {_normalized_review_path(path) for path in snapshot.context_paths if _normalized_review_path(path)}
    references = {
        _normalized_review_path(value)
        for value in [finding.file, *finding.subject_paths, *finding.context_paths]
        if _normalized_review_path(value)
    }
    subject_refs = sorted(references & subject)
    context_refs = sorted(references & context)
    if subject_refs:
        attribution = "run_owned_dependency" if context_refs else "run_owned"
        blocking = finding.severity in {"blocker", "high"}
    elif context_refs:
        attribution = "baseline_context"
        blocking = False
    else:
        attribution = "unattributed"
        blocking = False
    return finding.model_copy(update={
        "subject_paths": subject_refs,
        "context_paths": context_refs,
        "attribution": attribution,
        "blocking": blocking,
    })


def parse_review_result(
    text: str,
    *,
    parent_run_id: str,
    reviewer_run_id: str,
    snapshot: ReviewSnapshot,
) -> ReviewResult:
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''            findings.append(ReviewFinding.model_validate(row))
        except Exception:
            continue
    return ReviewResult(
''',
    '''            parsed_finding = ReviewFinding.model_validate(row)
            findings.append(_authoritative_review_finding(parsed_finding, snapshot))
        except Exception:
            continue
    return ReviewResult(
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''    if any(item.severity in {"blocker", "high"} for item in result.findings):
        return False
    return not result.missing_tests


def quality_failure_reasons''',
    '''    if any(item.severity in {"blocker", "high"} and item.blocking for item in result.findings):
        return False
    return not result.missing_tests


def quality_failure_reasons''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''        "You are the independent Omnix coding reviewer. You are reviewing an immutable snapshot, not helping the "
        "implementer. Be adversarial about correctness, completeness, missed call sites, API compatibility, edge "
        "cases, regressions and missing tests. Do not modify files. Do not infer correctness from the implementer's "
        "claims. Inspect the diff and relevant source/callers using read-only tools.\\n\\n"
''',
    '''        "You are the independent Omnix coding reviewer. You are reviewing an immutable snapshot, not helping the "
        "implementer. Be adversarial about correctness, completeness, missed call sites, API compatibility, edge "
        "cases, regressions and missing tests. Do not modify files. Do not infer correctness from the implementer's "
        "claims. The exact workspace is CONTEXT; the authoritative review SUBJECT is the RunChangeSet. Call the "
        "Omnix Run Change Set tool first and review that complete run-owned subject. Baseline-only dirty paths may be "
        "read as context but are not attributable to this run unless you identify a run-owned subject path that causes "
        "a dependency problem.\\n\\n"
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''        f"Workspace state: {snapshot.workspace_state_id}\\n"
        f"Requirements JSON: {json.dumps(requirements, ensure_ascii=False)}\\n"
''',
    '''        f"Workspace state: {snapshot.workspace_state_id}\\n"
        f"Run change set: {snapshot.run_change_set_id}\\n"
        f"Authoritative subject paths JSON: {json.dumps(snapshot.subject_paths, ensure_ascii=False)}\\n"
        f"Baseline context paths JSON: {json.dumps(snapshot.context_paths, ensure_ascii=False)}\\n"
        f"Requirements JSON: {json.dumps(requirements, ensure_ascii=False)}\\n"
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''        "{\\"verdict\\":\\"approve|changes_required|blocked\\","
        "\\"requirements\\":[{\\"requirement_id\\":\\"R\\",\\"status\\":\\"satisfied|partial|missing|not_applicable\\",\\"evidence\\":\\"...\\"}],"
        "\\"findings\\":[{\\"severity\\":\\"blocker|high|medium|low\\",\\"category\\":\\"correctness\\",\\"file\\":null,\\"location\\":null,\\"problem\\":\\"...\\",\\"recommended_fix\\":null}],"
''',
    '''        "{\\"verdict\\":\\"approve|changes_required|blocked\\","
        "\\"requirements\\":[{\\"requirement_id\\":\\"R\\",\\"status\\":\\"satisfied|partial|missing|not_applicable\\",\\"evidence\\":\\"...\\"}],"
        "\\"findings\\":[{\\"severity\\":\\"blocker|high|medium|low\\",\\"category\\":\\"correctness\\",\\"file\\":null,\\"location\\":null,\\"problem\\":\\"...\\",\\"recommended_fix\\":null,\\"subject_paths\\":[\\"run/owned/path\\"],\\"context_paths\\":[\\"baseline/context/path\\"]}],"
''',
)

# ---------------------------------------------------------------------------
# Persistence: ValidationOutcome + ReviewSnapshot subject binding.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                success, output_digest, covers_requirement_ids, started_at, finished_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
''',
    '''                success, outcome, output_digest, covers_requirement_ids, started_at, finished_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                result.success,
                result.output_digest,
''',
    '''                result.success,
                result.outcome,
                result.output_digest,
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                       workspace_state_id, command, exit_code, success,
                       output_digest, covers_requirement_ids, started_at, finished_at, metadata
''',
    '''                       workspace_state_id, command, exit_code, success, outcome,
                       output_digest, covers_requirement_ids, started_at, finished_at, metadata
''',
)
# Second SELECT branch has the same text.
text = read("src/app/agent_runtime/coding_quality_repository.py")
text = text.replace(
    '''                       workspace_state_id, command, exit_code, success,
                       output_digest, covers_requirement_ids, started_at, finished_at, metadata
''',
    '''                       workspace_state_id, command, exit_code, success, outcome,
                       output_digest, covers_requirement_ids, started_at, finished_at, metadata
'''
)
write("src/app/agent_runtime/coding_quality_repository.py", text)
replace_once(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                success=bool(row[7]),
                output_digest=str(row[8]),
                covers_requirement_ids=list(row[9] or []),
                started_at=row[10],
                finished_at=row[11],
                metadata=dict(row[12] or {}),
''',
    '''                success=bool(row[7]),
                outcome=str(row[8]),
                output_digest=str(row[9]),
                covers_requirement_ids=list(row[10] or []),
                started_at=row[11],
                finished_at=row[12],
                metadata=dict(row[13] or {}),
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                patch_storage_ref, workspace_root, relevant_files,
                validation_result_ids, repository_guidance_digest, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
''',
    '''                patch_storage_ref, run_change_set_id, workspace_root, subject_paths, context_paths, relevant_files,
                validation_result_ids, repository_guidance_digest, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                snapshot.patch_storage_ref,
                snapshot.workspace_root,
                _json(snapshot.relevant_files),
''',
    '''                snapshot.patch_storage_ref,
                snapshot.run_change_set_id,
                snapshot.workspace_root,
                _json(snapshot.subject_paths),
                _json(snapshot.context_paths),
                _json(snapshot.relevant_files),
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                   patch_checksum, patch_storage_ref, workspace_root,
                   relevant_files, validation_result_ids,
                   repository_guidance_digest, created_at
''',
    '''                   patch_checksum, patch_storage_ref, run_change_set_id, workspace_root,
                   subject_paths, context_paths, relevant_files, validation_result_ids,
                   repository_guidance_digest, created_at
''',
)
replace_once(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''            patch_storage_ref=str(row[4]) if row[4] else None,
            workspace_root=str(row[5]),
            relevant_files=list(row[6] or []),
            validation_result_ids=list(row[7] or []),
            repository_guidance_digest=str(row[8]) if row[8] else None,
            created_at=row[9],
''',
    '''            patch_storage_ref=str(row[4]) if row[4] else None,
            run_change_set_id=str(row[5]) if row[5] else None,
            workspace_root=str(row[6]),
            subject_paths=list(row[7] or []),
            context_paths=list(row[8] or []),
            relevant_files=list(row[9] or []),
            validation_result_ids=list(row[10] or []),
            repository_guidance_digest=str(row[11]) if row[11] else None,
            created_at=row[12],
''',
)

# ---------------------------------------------------------------------------
# Profiles/capabilities/Pi: authoritative read-only RunChangeSet tool.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/capabilities.py",
    '''    _cap("workspace.git_diff", "Read local git diff", "Read the current isolated worktree diff.", zone="worker", effect="read", category="development"),
''',
    '''    _cap("workspace.git_diff", "Read local git diff", "Read the current isolated worktree diff as non-authoritative inspection context.", zone="worker", effect="read", category="development"),
    _cap("workspace.run_change_set", "Read authoritative run change set", "Read the canonical baseline-relative run-owned change subject bound to the exact candidate WorkspaceState.", zone="worker", effect="read", category="development"),
''',
)
replace_once(
    "src/app/agent_runtime/profiles.py",
    '_READ = ("workspace.read", "workspace.list", "workspace.search", "workspace.git_status", "workspace.git_diff")\n',
    '_READ = ("workspace.read", "workspace.list", "workspace.search", "workspace.git_status", "workspace.git_diff", "workspace.run_change_set")\n',
)
replace_once(
    "src/app/agent_runtime/pi_runtime_core.py",
    '''    if spec.external_capabilities:
        tools.add("omnix_capability")
''',
    '''    if spec.external_capabilities:
        tools.add("omnix_capability")
    if "workspace.run_change_set" in spec.capabilities:
        tools.add("omnix_change_set")
    if spec.profile == "coding":
        tools.add("omnix_plan")
''',
)
replace_once(
    "src/app/agent_runtime/pi_broker_extension.ts",
    '''  const allowed = new Set<string>(JSON.parse(process.env.OMNIX_AGENT_EXTERNAL_CAPABILITIES || "[]"));
  let usedManagedWorkspacePreview = false;
''',
    '''  const allowed = new Set<string>(JSON.parse(process.env.OMNIX_AGENT_EXTERNAL_CAPABILITIES || "[]"));
  const localAllowed = new Set<string>(JSON.parse(process.env.OMNIX_AGENT_LOCAL_CAPABILITIES || "[]"));
  let usedManagedWorkspacePreview = false;
''',
)
replace_once(
    "src/app/agent_runtime/pi_broker_extension.ts",
    '''  if (allowed.size === 0) return;

  pi.registerTool({
''',
    '''  if (localAllowed.has("workspace.run_change_set")) {
    pi.registerTool({
      name: "omnix_change_set",
      label: "Omnix Run Change Set",
      description: "Read the canonical complete run-owned change subject for the exact current candidate. This, not shell git diff, is final-diff authority.",
      promptSnippet: "Inspect the authoritative baseline-relative RunChangeSet",
      promptGuidelines: [
        "Use this tool for final-diff inspection. The returned subject is baseline-relative and includes run-added untracked content references.",
        "The exact workspace may contain baseline dirties; treat them as context, not run-owned subject paths.",
      ],
      parameters: Type.Object({}),
      async execute(_toolCallId, _params, signal) {
        const response = await fetch(`${baseUrl}/${encodeURIComponent(runId)}/run-change-set`, { signal });
        let payload: any = {};
        try { payload = await response.json(); } catch { payload = { detail: `HTTP ${response.status}` }; }
        if (!response.ok) {
          return { content: [{ type: "text", text: `Omnix change-set error: ${JSON.stringify(payload)}` }], details: { error: true, payload } };
        }
        return { content: [{ type: "text", text: JSON.stringify(payload) }], details: payload };
      },
    });
  }

  if (allowed.size === 0) return;

  pi.registerTool({
''',
)

# Broker route and response.
replace_once(
    "src/app/agent_runtime/broker_api.py",
    'from .contracts import AgentApproval, AgentEvent\n',
    'from .contracts import AgentApproval, AgentEvent, RunChangeSet\n',
)
replace_once(
    "src/app/agent_runtime/broker_api.py",
    '''class BrokerWorkspaceAuthorizationRequest(BaseModel):
    tool_name: Literal["edit", "write"]
    input: dict[str, Any] = Field(default_factory=dict)
    workspace_root: str | None = None


''',
    '''class BrokerWorkspaceAuthorizationRequest(BaseModel):
    tool_name: Literal["edit", "write"]
    input: dict[str, Any] = Field(default_factory=dict)
    workspace_root: str | None = None


class BrokerRunChangeSetResponse(BaseModel):
    change_set: RunChangeSet
    patch: str


''',
)
replace_once(
    "src/app/agent_runtime/broker_api.py",
    '''@router.post(
    "/{run_id}/budget/tool",
''',
    '''@router.get("/{run_id}/run-change-set", response_model=BrokerRunChangeSetResponse)
def read_agent_run_change_set(run_id: str) -> BrokerRunChangeSetResponse:
    service = default_agent_run_service()
    snapshot = service.get(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    if "workspace.run_change_set" not in snapshot.spec.capabilities:
        raise HTTPException(status_code=403, detail="workspace_run_change_set_not_issued")
    try:
        change_set, patch = service.run_change_set(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent_run_change_set_not_found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BrokerRunChangeSetResponse(change_set=change_set, patch=patch)


@router.post(
    "/{run_id}/budget/tool",
''',
)

# ---------------------------------------------------------------------------
# Review orchestration uses canonical subject, not generic git diff.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/review_orchestration.py",
    '''    "workspace.git_status",
    "workspace.git_diff",
]''',
    '''    "workspace.git_status",
    "workspace.run_change_set",
]''',
)
replace_once(
    "src/app/agent_runtime/review_orchestration.py",
    '''        "Pass A — blind correctness: inspect the immutable diff, changed source, callers/contracts, and raw "
''',
    '''        "Pass A — blind correctness: call the Omnix Run Change Set tool, inspect that authoritative run-owned "
        "subject plus changed source, callers/contracts, and raw "
''',
)
replace_once(
    "src/app/agent_runtime/review_runtime.py",
    '''    for finding in payload["findings"]:
        if not isinstance(finding, dict) or not str(finding.get("problem") or "").strip():
            return False
        if str(finding.get("severity") or "medium").strip() not in {
''',
    '''    for finding in payload["findings"]:
        if not isinstance(finding, dict) or not str(finding.get("problem") or "").strip():
            return False
        if not isinstance(finding.get("subject_paths"), list) or not isinstance(finding.get("context_paths"), list):
            return False
        if any(not isinstance(path, str) for path in finding.get("subject_paths", [])):
            return False
        if any(not isinstance(path, str) for path in finding.get("context_paths", [])):
            return False
        if str(finding.get("severity") or "medium").strip() not in {
''',
)

# ---------------------------------------------------------------------------
# API omission semantics: omitted/null => quality sizing; {} is explicit 200.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/api.py",
    '    limits: RunLimits = Field(default_factory=RunLimits)\n',
    '    limits: RunLimits | None = None\n',
)
replace_once(
    "src/app/agent_runtime/api.py",
    '''    spec = AgentRunSpec(
        task=request.task,
''',
    '''    limit_kwargs = {"limits": request.limits} if request.limits is not None else {}
    spec = AgentRunSpec(
        task=request.task,
''',
)
replace_once(
    "src/app/agent_runtime/api.py",
    '''        quality_reserve_fraction=request.quality_reserve_fraction,
        limits=request.limits,
        workspace=(
''',
    '''        quality_reserve_fraction=request.quality_reserve_fraction,
        **limit_kwargs,
        workspace=(
''',
)

# ---------------------------------------------------------------------------
# Durable token-report availability. Numeric counters remain budget authority.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/repository.py",
    '''                   run_usage.input_tokens,
                   run_usage.output_tokens,
                   omnix_agent_runs.started_at,
''',
    '''                   run_usage.input_tokens,
                   run_usage.output_tokens,
                   run_usage.input_tokens_reported,
                   run_usage.output_tokens_reported,
                   omnix_agent_runs.started_at,
''',
)
replace_once(
    "src/app/agent_runtime/repository.py",
    '''                input_tokens=int(row[7] or 0),
                output_tokens=int(row[8] or 0),
            ),
            started_at=row[9],
            completed_at=row[10],
            last_error=str(row[11]) if row[11] else None,
            created_at=row[12],
            updated_at=row[13],
''',
    '''                input_tokens=int(row[7] or 0),
                output_tokens=int(row[8] or 0),
                input_tokens_reported=bool(row[9]),
                output_tokens_reported=bool(row[10]),
            ),
            started_at=row[11],
            completed_at=row[12],
            last_error=str(row[13]) if row[13] else None,
            created_at=row[14],
            updated_at=row[15],
''',
)
replace_once(
    "src/app/agent_runtime/repository.py",
    '''            SELECT steps, tool_calls, model_calls, input_tokens, output_tokens, cost
''',
    '''            SELECT steps, tool_calls, model_calls, input_tokens, output_tokens, cost,
                   input_tokens_reported, output_tokens_reported
''',
)
replace_once(
    "src/app/agent_runtime/repository.py",
    '''            "cost": float(row[5]),
        }

    def consume_usage(
''',
    '''            "cost": float(row[5]),
            "input_tokens_reported": bool(row[6]),
            "output_tokens_reported": bool(row[7]),
        }

    def consume_usage(
''',
)
replace_once(
    "src/app/agent_runtime/repository.py",
    '''        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
''',
    '''        input_tokens: int = 0,
        output_tokens: int = 0,
        input_tokens_reported: bool = False,
        output_tokens_reported: bool = False,
        cost: float = 0.0,
''',
)
replace_once(
    "src/app/agent_runtime/repository.py",
    '''                   output_tokens = output_tokens + %s,
                   cost = cost + %s,
''',
    '''                   output_tokens = output_tokens + %s,
                   input_tokens_reported = input_tokens_reported OR %s,
                   output_tokens_reported = output_tokens_reported OR %s,
                   cost = cost + %s,
''',
)
replace_once(
    "src/app/agent_runtime/repository.py",
    '''                output_tokens,
                cost,
                self.context.workspace_id,
''',
    '''                output_tokens,
                input_tokens_reported,
                output_tokens_reported,
                cost,
                self.context.workspace_id,
''',
)
replace_once(
    "src/app/agent_runtime/repository.py",
    '''            RETURNING steps, tool_calls, model_calls, input_tokens, output_tokens, cost
''',
    '''            RETURNING steps, tool_calls, model_calls, input_tokens, output_tokens, cost,
                      input_tokens_reported, output_tokens_reported
''',
)
# RETURNING shape occurs once in consume_usage after the get_usage replacement.
replace_once(
    "src/app/agent_runtime/repository.py",
    '''            "cost": float(row[5]),
        }

    def acquire_lease''',
    '''            "cost": float(row[5]),
            "input_tokens_reported": bool(row[6]),
            "output_tokens_reported": bool(row[7]),
        }

    def acquire_lease''',
)
replace_regex(
    "src/app/agent_runtime/budget.py",
    r'''    def record_token_usage\(\n.*?\n    def record_output_tokens''',
    '''    def record_token_usage(
        self,
        run_id: str,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> dict[str, object]:
        if input_tokens is not None and input_tokens < 0:
            raise ValueError("token usage must be non-negative")
        if output_tokens is not None and output_tokens < 0:
            raise ValueError("token usage must be non-negative")
        if input_tokens is None and output_tokens is None:
            return self.usage(run_id)
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            self._lock_run(repository, run_id)
            snapshot = repository.get_run(run_id)
            if snapshot is None:
                raise KeyError(run_id)
            effective = self._effective_limits(repository, snapshot)
            usage = repository.consume_usage(
                run_id,
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
                input_tokens_reported=input_tokens is not None,
                output_tokens_reported=output_tokens is not None,
                max_output_tokens=(
                    int(effective["max_tokens"])
                    if effective["max_tokens"] is not None
                    else None
                ),
            )
            if usage is None:
                reason = "budget_max_output_tokens_exceeded"
                self._fail_locked(repository, snapshot, reason)
                work.commit()
                raise AgentBudgetError(reason)
            work.commit()
            return usage

    def record_output_tokens''',
)
replace_once(
    "src/app/agent_runtime/model_gateway.py",
    '''        if input_tokens or output_tokens:
            try:
                await asyncio.to_thread(
                    budget.record_token_usage,
                    x_omnix_agent_run_id,
                    input_tokens=input_tokens or 0,
                    output_tokens=output_tokens or 0,
                )
''',
    '''        if input_tokens is not None or output_tokens is not None:
            try:
                await asyncio.to_thread(
                    budget.record_token_usage,
                    x_omnix_agent_run_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
''',
)
replace_once(
    "src/app/agent_runtime/model_gateway.py",
    '''            if observed_input_tokens or observed_output_tokens:
                try:
                    await asyncio.to_thread(
                        budget.record_token_usage,
                        x_omnix_agent_run_id,
                        input_tokens=observed_input_tokens or 0,
                        output_tokens=observed_output_tokens or 0,
                    )
''',
    '''            if observed_input_tokens is not None or observed_output_tokens is not None:
                try:
                    await asyncio.to_thread(
                        budget.record_token_usage,
                        x_omnix_agent_run_id,
                        input_tokens=observed_input_tokens,
                        output_tokens=observed_output_tokens,
                    )
''',
)
replace_once(
    "src/apps/web/src/features/chatbot/OmnixRunCardCore.tsx",
    '''function formatTokenCount(value: unknown): string {
  const count = Number(value);
  return Number.isFinite(count) && count >= 0 ? Math.round(count).toLocaleString() : '0';
}
''',
    '''function formatTokenCount(value: unknown, reported: unknown): string {
  if (reported !== true) return '—';
  const count = Number(value);
  return Number.isFinite(count) && count >= 0 ? Math.round(count).toLocaleString() : '—';
}
''',
)
replace_once(
    "src/apps/web/src/features/chatbot/OmnixRunCardCore.tsx",
    '''      usage: { input_tokens: 0, output_tokens: 0 },
''',
    '''      usage: { input_tokens: 0, output_tokens: 0, input_tokens_reported: false, output_tokens_reported: false },
''',
)
replace_once(
    "src/apps/web/src/features/chatbot/OmnixRunCardCore.tsx",
    '''  const inputTokens = formatTokenCount(query.data.usage?.input_tokens);
  const outputTokens = formatTokenCount(query.data.usage?.output_tokens);
''',
    '''  const inputTokens = formatTokenCount(query.data.usage?.input_tokens, query.data.usage?.input_tokens_reported);
  const outputTokens = formatTokenCount(query.data.usage?.output_tokens, query.data.usage?.output_tokens_reported);
''',
)
replace_once(
    "src/apps/web/src/features/chatbot/OmnixRunCardCore.tsx",
    '''        <div><strong>Input tokens</strong><span>{inputTokens}</span></div>
        <div><strong>Output tokens</strong><span>{outputTokens}</span></div>
''',
    '''        <div><strong>Input tokens</strong><span title={query.data.usage?.input_tokens_reported ? undefined : 'Not reported'}>{inputTokens}</span></div>
        <div><strong>Output tokens</strong><span title={query.data.usage?.output_tokens_reported ? undefined : 'Not reported'}>{outputTokens}</span></div>
''',
)

# ---------------------------------------------------------------------------
# Service facade: expose canonical change set; bind review snapshot to it.
# ---------------------------------------------------------------------------
replace_once(
    "src/app/agent_runtime/service.py",
    '    ReviewSnapshot,\n    RunLimits,\n',
    '    ReviewSnapshot,\n    RunChangeSet,\n    RunLimits,\n',
)
replace_once(
    "src/app/agent_runtime/service.py",
    '    capture_workspace_state,\n    compile_task_engineering_contract,\n',
    '    candidate_validation_gate,\n    capture_workspace_state,\n    compile_task_engineering_contract,\n',
)
replace_once(
    "src/app/agent_runtime/service.py",
    'from .workspace import WorkspaceAuthority\n',
    'from .workspace import WorkspaceAuthority\nfrom .run_change_set import run_change_set_from_artifact\n',
)
# Insert public RunChangeSet accessor after review_attempts.
replace_once(
    "src/app/agent_runtime/service.py",
    '''    def command_with_context(
        self,
        command: AgentRunCommand,
''',
    '''    def run_change_set(self, run_id: str) -> tuple[RunChangeSet, str]:
        """Return the one authoritative run-owned subject for parent or reviewer."""
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            current = repository.get_run(run_id)
            if current is None:
                work.rollback()
                raise KeyError(run_id)
            change_set: RunChangeSet | None = None
            if current.spec.profile == "coding-reviewer" and current.spec.parent_run_id:
                snapshot_id = review_snapshot_id_from_child(current)
                if not snapshot_id:
                    work.rollback()
                    raise RuntimeError("review_run_change_set_snapshot_unavailable")
                quality = PostgresCodingQualityRepository(work.connection, self.context)
                review_snapshot = quality.get_review_snapshot(current.spec.parent_run_id, snapshot_id)
                if review_snapshot is None or not review_snapshot.run_change_set_id:
                    work.rollback()
                    raise RuntimeError("review_run_change_set_snapshot_unavailable")
                for artifact in reversed(repository.list_artifacts(current.spec.parent_run_id)):
                    candidate = run_change_set_from_artifact(artifact)
                    if candidate is not None and candidate.change_set_id == review_snapshot.run_change_set_id:
                        change_set = candidate
                        break
            else:
                if not self._quality_enabled(current.spec):
                    work.rollback()
                    raise RuntimeError("agent_run_change_set_not_applicable")
                revision = self._current_revision(repository, run_id)
                if revision is None:
                    work.rollback()
                    raise RuntimeError("agent_run_change_set_revision_unavailable")
                state = capture_workspace_state(current.spec, task_revision_id=revision.revision_id)
                if state is None:
                    work.rollback()
                    raise RuntimeError("agent_run_change_set_workspace_unavailable")
                PostgresCodingQualityRepository(work.connection, self.context).add_workspace_state(state)
                change_set = self._capture_diff(
                    repository,
                    current.spec,
                    task_revision_id=revision.revision_id,
                    workspace_state_id=state.state_id,
                )
            if change_set is None:
                work.rollback()
                raise RuntimeError("agent_run_change_set_unavailable")
            work.commit()
        patch = self.blob_store.read_bytes(
            change_set.patch_storage_ref,
            expected_checksum=change_set.patch_checksum,
        ).decode("utf-8", errors="replace")
        return change_set, patch

    def command_with_context(
        self,
        command: AgentRunCommand,
''',
)
# Bind quality-stage diff capture to exact state where the straightforward call appears.
text = read("src/app/agent_runtime/service.py")
text = text.replace(
    'self._capture_diff(repository, current.spec, task_revision_id=revision.revision_id)',
    'self._capture_diff(repository, current.spec, task_revision_id=revision.revision_id, workspace_state_id=state.state_id)'
)
write("src/app/agent_runtime/service.py", text)
# Review snapshot must use the canonical artifact for this exact state.
replace_once(
    "src/app/agent_runtime/service.py",
    '''        diff_artifact = next(
            (
                artifact
                for artifact in reversed(artifacts)
                if artifact.kind == "diff"
                and artifact.metadata.get("task_revision_id") == revision.revision_id
            ),
            None,
        )
        review_root = os.environ.get(
''',
    '''        diff_artifact = next(
            (
                artifact
                for artifact in reversed(artifacts)
                if artifact.kind == "diff"
                and artifact.metadata.get("task_revision_id") == revision.revision_id
                and artifact.metadata.get("workspace_state_id") == state.state_id
            ),
            None,
        )
        change_set = run_change_set_from_artifact(diff_artifact)
        if change_set is None:
            return self._quality_fail(repository, current, "quality_run_change_set_unavailable")
        review_root = os.environ.get(
''',
)
replace_once(
    "src/app/agent_runtime/service.py",
    '''            patch_checksum=state.state_id,
            patch_storage_ref=diff_artifact.storage_ref if diff_artifact else None,
            workspace_root=review_workspace.root,
            relevant_files=relevant_file_candidates(revision, state),
''',
    '''            patch_checksum=change_set.patch_checksum,
            patch_storage_ref=change_set.patch_storage_ref,
            run_change_set_id=change_set.change_set_id,
            workspace_root=review_workspace.root,
            subject_paths=list(change_set.run_owned_paths),
            context_paths=list(change_set.baseline_context_paths),
            relevant_files=relevant_file_candidates(revision, state),
''',
)

# ---------------------------------------------------------------------------
# Deterministic validation convergence in service.py.
# ---------------------------------------------------------------------------
insert_anchor = '''def _implementation_candidate_retry_limit() -> int:
'''
validation_helpers = '''def _validation_retry_limit() -> int:
    raw = str(os.environ.get("OMNIX_AGENT_VALIDATION_RETRIES", "2") or "2").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 2
    return max(0, min(value, 5))


def _quality_events(repository: PostgresAgentRunRepository, run_id: str) -> list[AgentEvent]:
    return repository.list_events(run_id, after_sequence=0, limit=5000)


def _validation_event_count(
    repository: PostgresAgentRunRepository,
    *,
    run_id: str,
    event_type: str,
    task_revision_id: str,
    workspace_state_id: str,
    fingerprint: str | None = None,
) -> int:
    count = 0
    for event in _quality_events(repository, run_id):
        if event.event_type != event_type:
            continue
        payload = event.payload
        if str(payload.get("task_revision_id") or "") != task_revision_id:
            continue
        if str(payload.get("workspace_state_id") or "") != workspace_state_id:
            continue
        if fingerprint is not None and str(payload.get("fingerprint") or "") != fingerprint:
            continue
        count += 1
    return count


def _validation_failure_fingerprint(rows) -> str:
    material = [
        {
            "validation_id": item.validation_id,
            "outcome": item.outcome,
            "output_digest": item.output_digest,
        }
        for item in sorted(rows, key=lambda row: (row.validation_id, row.result_id))
    ]
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


'''
replace_once("src/app/agent_runtime/service.py", insert_anchor, validation_helpers + insert_anchor)
# service.py needs json.
replace_once("src/app/agent_runtime/service.py", 'import hashlib\nimport os\n', 'import hashlib\nimport json\nimport os\n')

# Add request helpers before _advance_quality_on_settle.
advance_anchor = '''    def _advance_quality_on_settle(
        self,
        repository: PostgresAgentRunRepository,
'''
request_helpers = '''    def _request_validation_execution(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        revision: TaskRevision,
        *,
        attempt: int,
        workspace_state_id: str,
        missing,
    ) -> tuple | None:
        ids = sorted(item.id for item in missing)
        fingerprint = hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest()[:24]
        prior = _validation_event_count(
            repository,
            run_id=current.run_id,
            event_type="quality.validation_requested",
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
            fingerprint=fingerprint,
        )
        if prior:
            return self._quality_fail(repository, current, "quality_failed:validation_not_executed")
        repository.append_event(AgentEvent(
            run_id=current.run_id,
            event_type="quality.validation_requested",
            payload={
                "task_revision_id": revision.revision_id,
                "workspace_state_id": workspace_state_id,
                "validation_ids": ids,
                "fingerprint": fingerprint,
            },
        ))
        self._set_quality_stage(
            repository,
            run_id=current.run_id,
            stage="validating",
            attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
            reason="candidate_validation_required",
        )
        prompt = validation_prompt(revision, missing)
        return self._queue_quality_resume(
            repository,
            run_id=current.run_id,
            prompt=prompt,
            idempotency_key=f"quality-validation:{current.run_id}:{revision.revision_id}:{workspace_state_id}:{fingerprint}",
            quality_stage="validating",
            quality_attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
        )

    def _request_validation_retry(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        revision: TaskRevision,
        *,
        attempt: int,
        workspace_state_id: str,
        failures,
    ) -> tuple | None:
        fingerprint = _validation_failure_fingerprint(failures)
        retries = _validation_event_count(
            repository,
            run_id=current.run_id,
            event_type="quality.validation_retry_requested",
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
            fingerprint=fingerprint,
        )
        limit = _validation_retry_limit()
        if retries >= limit:
            repository.append_event(AgentEvent(
                run_id=current.run_id,
                event_type="quality.validation_retry_exhausted",
                payload={
                    "task_revision_id": revision.revision_id,
                    "workspace_state_id": workspace_state_id,
                    "fingerprint": fingerprint,
                    "retry_limit": limit,
                },
            ))
            return self._quality_fail(repository, current, "quality_failed:validation_retry_exhausted")
        retry = retries + 1
        repository.append_event(AgentEvent(
            run_id=current.run_id,
            event_type="quality.validation_retry_requested",
            payload={
                "task_revision_id": revision.revision_id,
                "workspace_state_id": workspace_state_id,
                "fingerprint": fingerprint,
                "retry": retry,
                "retry_limit": limit,
                "validation_ids": sorted({item.validation_id for item in failures}),
            },
        ))
        missing = [
            spec for spec in revision.validation_plan
            if spec.required and spec.id in {item.validation_id for item in failures}
        ]
        prompt = validation_prompt(revision, missing)
        prompt += "\\n\\nThis is a bounded same-candidate infrastructure/protocol validation retry. Do not claim completion until it executes normally."
        return self._queue_quality_resume(
            repository,
            run_id=current.run_id,
            prompt=prompt,
            idempotency_key=f"quality-validation-retry:{current.run_id}:{revision.revision_id}:{workspace_state_id}:{fingerprint}:{retry}",
            quality_stage="validating",
            quality_attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
        )

    def _request_validation_repair(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        revision: TaskRevision,
        *,
        attempt: int,
        workspace_state_id: str,
        failures,
    ) -> tuple | None:
        fingerprint = _validation_failure_fingerprint(failures)
        prior = _validation_event_count(
            repository,
            run_id=current.run_id,
            event_type="quality.validation_repair_requested",
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
            fingerprint=fingerprint,
        )
        if prior:
            return self._quality_fail(repository, current, "quality_failed:no_progress_after_validation_failure")
        repository.append_event(AgentEvent(
            run_id=current.run_id,
            event_type="quality.validation_repair_requested",
            payload={
                "task_revision_id": revision.revision_id,
                "workspace_state_id": workspace_state_id,
                "fingerprint": fingerprint,
                "validation_ids": sorted({item.validation_id for item in failures}),
                "outcomes": sorted({item.outcome for item in failures}),
            },
        ))
        self._set_quality_stage(
            repository,
            run_id=current.run_id,
            stage="repairing",
            attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
            reason="substantive_validation_failure",
        )
        failure_rows = [
            {
                "validation_id": item.validation_id,
                "outcome": item.outcome,
                "command": item.command,
                "exit_code": item.exit_code,
                "output_digest": item.output_digest,
            }
            for item in failures
        ]
        prompt = (
            "The exact candidate failed required validation. Treat this as implementation evidence, not a reason to "
            "rerun the same candidate indefinitely. Diagnose and repair the cause. The repair must produce a new "
            "WorkspaceState before Omnix will authorize fresh validation.\\n"
            f"Validation failures JSON: {json.dumps(failure_rows, ensure_ascii=False)}"
        )
        return self._queue_quality_resume(
            repository,
            run_id=current.run_id,
            prompt=prompt,
            idempotency_key=f"quality-validation-repair:{current.run_id}:{revision.revision_id}:{workspace_state_id}:{fingerprint}",
            quality_stage="repairing",
            quality_attempt=attempt,
            task_revision_id=revision.revision_id,
            workspace_state_id=workspace_state_id,
        )

'''
replace_once("src/app/agent_runtime/service.py", advance_anchor, request_helpers + advance_anchor)

# Replace first pre-review gate handling with candidate-bound validation outcomes.
replace_once(
    "src/app/agent_runtime/service.py",
    '''            gate, gate_details = _pre_review_gate(
                revision,
                validations,
                workspace_state_id=state.state_id,
                diff_artifact=diff_artifact,
            )
            if gate == "validating":
                self._set_quality_stage(
                    repository,
                    run_id=current.run_id,
                    stage="validating",
                    attempt=attempt,
                    task_revision_id=revision.revision_id,
                    workspace_state_id=state.state_id,
                    reason="implementation_candidate_requires_final_state_validation",
                )
                prompt = validation_prompt(revision, gate_details)
                validation_generation = len(current_validations)
                return self._queue_quality_resume(
                    repository,
                    run_id=current.run_id,
                    prompt=prompt,
                    idempotency_key=(
                        f"quality-validation:{current.run_id}:{state.state_id}:"
                        f"{attempt}:{validation_generation}"
                    ),
                    quality_stage="validating",
                    quality_attempt=attempt,
                    task_revision_id=revision.revision_id,
                    workspace_state_id=state.state_id,
                )
            if gate == "implementing":
''',
    '''            validation_gate, validation_details = candidate_validation_gate(
                revision,
                validations,
                workspace_state_id=state.state_id,
            )
            if validation_gate == "validation_repair":
                return self._request_validation_repair(
                    repository, current, revision, attempt=attempt,
                    workspace_state_id=state.state_id, failures=validation_details,
                )
            if validation_gate == "validation_retry":
                return self._request_validation_retry(
                    repository, current, revision, attempt=attempt,
                    workspace_state_id=state.state_id, failures=validation_details,
                )
            if validation_gate == "validation_missing":
                return self._request_validation_execution(
                    repository, current, revision, attempt=attempt,
                    workspace_state_id=state.state_id, missing=validation_details,
                )
            gate, gate_details = _pre_review_gate(
                revision,
                validations,
                workspace_state_id=state.state_id,
                diff_artifact=diff_artifact,
            )
            if gate == "implementing":
''',
)
# The later missing-only block after legacy self-review must use the same candidate gate.
replace_regex(
    "src/app/agent_runtime/service.py",
    r'''        missing = missing_final_validations\(\n            revision,\n            validations,\n            workspace_state_id=state.state_id,\n        \)\n        if missing:\n            self._set_quality_stage\(.*?\n            \)\n\n        review_count = required_review_count''',
    '''        validation_gate, validation_details = candidate_validation_gate(
            revision,
            validations,
            workspace_state_id=state.state_id,
        )
        if validation_gate == "validation_repair":
            return self._request_validation_repair(
                repository, current, revision, attempt=attempt,
                workspace_state_id=state.state_id, failures=validation_details,
            )
        if validation_gate == "validation_retry":
            return self._request_validation_retry(
                repository, current, revision, attempt=attempt,
                workspace_state_id=state.state_id, failures=validation_details,
            )
        if validation_gate == "validation_missing":
            return self._request_validation_execution(
                repository, current, revision, attempt=attempt,
                workspace_state_id=state.state_id, missing=validation_details,
            )

        review_count = required_review_count''',
)

# Acceptance in the quality facade captures canonical state before evaluating artifacts.
replace_once(
    "src/app/agent_runtime/service.py",
    '''        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="acceptance.started",
                payload={"source": "omnix", "task_revision_id": revision_id},
            )
        )
        self._capture_diff(repository, current.spec, task_revision_id=revision_id)
        all_events = repository.list_events(current.run_id, after_sequence=0, limit=5000)
''',
    '''        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="acceptance.started",
                payload={"source": "omnix", "task_revision_id": revision_id},
            )
        )
        quality = PostgresCodingQualityRepository(repository.connection, self.context)
        state = capture_workspace_state(current.spec, task_revision_id=revision_id)
        if state is not None:
            quality.add_workspace_state(state)
        self._capture_diff(
            repository,
            current.spec,
            task_revision_id=revision_id,
            workspace_state_id=state.state_id if state else None,
        )
        all_events = repository.list_events(current.run_id, after_sequence=0, limit=5000)
''',
)
replace_once(
    "src/app/agent_runtime/service.py",
    '''        quality = PostgresCodingQualityRepository(repository.connection, self.context)
        acceptance_stage = quality.get_stage(current.run_id) or {}
''',
    '''        acceptance_stage = quality.get_stage(current.run_id) or {}
''',
)
replace_once(
    "src/app/agent_runtime/service.py",
    '''        state = capture_workspace_state(current.spec, task_revision_id=revision_id)
        if state is not None:
            quality.add_workspace_state(state)
        workspace_changed_after_review = bool(
''',
    '''        workspace_changed_after_review = bool(
''',
)

# ---------------------------------------------------------------------------
# Migration 0067: structural outcomes, review subject binding, token presence.
# ---------------------------------------------------------------------------
write(
    "src/app/persistence/migrations/0067_agent_candidate_authority.sql",
    '''-- Candidate-bound validation, canonical review subject, and provider usage availability.

ALTER TABLE omnix_agent_validation_results
    ADD COLUMN IF NOT EXISTS outcome TEXT;

UPDATE omnix_agent_validation_results
   SET outcome = CASE
       WHEN success THEN 'passed'
       WHEN metadata ->> 'outcome' IN (
           'substantive_failure','infrastructure_failure','protocol_failure','blocked'
       ) THEN metadata ->> 'outcome'
       ELSE 'substantive_failure'
   END
 WHERE outcome IS NULL;

ALTER TABLE omnix_agent_validation_results
    ALTER COLUMN outcome SET DEFAULT 'substantive_failure',
    ALTER COLUMN outcome SET NOT NULL;

ALTER TABLE omnix_agent_validation_results
    DROP CONSTRAINT IF EXISTS omnix_agent_validation_results_outcome_check;
ALTER TABLE omnix_agent_validation_results
    ADD CONSTRAINT omnix_agent_validation_results_outcome_check
    CHECK (outcome IN ('passed','substantive_failure','infrastructure_failure','protocol_failure','blocked'));

ALTER TABLE omnix_agent_review_snapshots
    ADD COLUMN IF NOT EXISTS run_change_set_id TEXT,
    ADD COLUMN IF NOT EXISTS subject_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS context_paths JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE omnix_agent_run_usage
    ADD COLUMN IF NOT EXISTS input_tokens_reported BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS output_tokens_reported BOOLEAN NOT NULL DEFAULT FALSE;
''',
)

# ---------------------------------------------------------------------------
# Tests: authority, API intent, convergence, and usage availability.
# ---------------------------------------------------------------------------
write(
    "src/tests/agent_runtime/test_candidate_authority_convergence.py",
    '''from __future__ import annotations

from datetime import datetime, timezone

from app.agent_runtime.api import StartAgentRunRequest
from app.agent_runtime.coding_quality import (
    candidate_validation_gate,
    diff_review_command_is_complete,
    parse_review_result,
    review_is_acceptable,
    validation_result_from_tool_event,
)
from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunSpec,
    ModelRef,
    ReviewSnapshot,
    TaskRequirement,
    TaskRevision,
    ValidationResult,
    ValidationSpec,
)
from app.agent_runtime.service import _quality_sized_run_spec


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="rev-1",
        run_id="run-1",
        sequence=1,
        user_instruction="fix",
        effective_objective="fix",
        requirements=[TaskRequirement(id="R", description="fix", required=True)],
        validation_plan=[ValidationSpec(id="final-state-tests", kind="test", description="tests", covers=["R"])],
    )


def _validation(outcome: str, *, digest: str = "x") -> ValidationResult:
    return ValidationResult(
        result_id=f"result-{outcome}-{digest}",
        run_id="run-1",
        validation_id="final-state-tests",
        kind="test",
        task_revision_id="rev-1",
        workspace_state_id="state-1",
        command="pytest",
        exit_code=0 if outcome == "passed" else 1,
        success=outcome == "passed",
        outcome=outcome,
        output_digest=digest,
        covers_requirement_ids=["R"],
        finished_at=datetime.now(timezone.utc),
    )


def test_shell_git_diff_is_never_final_diff_authority() -> None:
    assert not diff_review_command_is_complete("git diff HEAD")
    assert not diff_review_command_is_complete("git diff --no-ext-diff")


def test_run_change_set_tool_is_bound_to_exact_candidate() -> None:
    revision = TaskRevision(
        revision_id="rev-1", run_id="run-1", sequence=1,
        user_instruction="fix", effective_objective="fix",
        validation_plan=[ValidationSpec(id="final-diff-review", kind="diff_review", description="diff")],
    )
    result = validation_result_from_tool_event(
        AgentEvent(
            run_id="run-1",
            event_type="tool.completed",
            payload={
                "tool": "omnix_change_set",
                "tool_call_id": "cs-1",
                "is_error": False,
                "result": {"details": {"change_set": {"change_set_id": "cs", "candidate_workspace_state_id": "state-1"}}},
            },
        ),
        run_id="run-1", task_revision_id="rev-1", workspace_state_id="state-1", revision=revision,
    )
    assert result is not None
    assert result.validation_id == "final-diff-review"
    assert result.outcome == "passed"


def test_candidate_validation_gate_does_not_use_quality_attempt_identity() -> None:
    revision = _revision()
    gate, rows = candidate_validation_gate(revision, [_validation("substantive_failure")], workspace_state_id="state-1")
    assert gate == "validation_repair"
    assert rows and rows[0].workspace_state_id == "state-1"
    gate, _ = candidate_validation_gate(revision, [_validation("infrastructure_failure")], workspace_state_id="state-1")
    assert gate == "validation_retry"
    gate, _ = candidate_validation_gate(revision, [_validation("passed")], workspace_state_id="state-1")
    assert gate == "passed"


def test_server_downgrades_baseline_only_high_finding_to_nonblocking_context() -> None:
    snapshot = ReviewSnapshot(
        run_id="run-1", task_revision_id="rev-1", workspace_state_id="state-1",
        base_commit_sha="abc", patch_checksum="def", run_change_set_id="cs-1",
        workspace_root="/tmp/review", subject_paths=["src/styles.css"], context_paths=["src/repository.py"],
    )
    revision = _revision()
    text = ''' + "'''" + '''{"verdict":"approve","requirements":[{"requirement_id":"R","status":"satisfied","evidence":"ok"}],"findings":[{"severity":"high","category":"correctness","file":"src/repository.py","location":null,"problem":"baseline issue","recommended_fix":null,"subject_paths":["src/repository.py"],"context_paths":[]}],"missing_tests":[],"residual_risks":[]}''' + "'''" + '''
    result = parse_review_result(text, parent_run_id="run-1", reviewer_run_id="reviewer", snapshot=snapshot)
    finding = result.findings[0]
    assert finding.attribution == "baseline_context"
    assert not finding.blocking
    assert review_is_acceptable(result, revision)


def test_dependency_finding_blocks_only_when_it_names_run_owned_subject() -> None:
    snapshot = ReviewSnapshot(
        run_id="run-1", task_revision_id="rev-1", workspace_state_id="state-1",
        base_commit_sha="abc", patch_checksum="def", run_change_set_id="cs-1",
        workspace_root="/tmp/review", subject_paths=["src/api.py"], context_paths=["src/repository.py"],
    )
    revision = _revision()
    text = ''' + "'''" + '''{"verdict":"changes_required","requirements":[{"requirement_id":"R","status":"satisfied","evidence":"ok"}],"findings":[{"severity":"high","category":"correctness","file":"src/repository.py","location":null,"problem":"API change breaks baseline caller","recommended_fix":null,"subject_paths":["src/api.py"],"context_paths":["src/repository.py"]}],"missing_tests":[],"residual_risks":[]}''' + "'''" + '''
    result = parse_review_result(text, parent_run_id="run-1", reviewer_run_id="reviewer", snapshot=snapshot)
    assert result.findings[0].attribution == "run_owned_dependency"
    assert result.findings[0].blocking
    assert not review_is_acceptable(result, revision)


def test_api_limits_omitted_and_null_are_not_explicit_but_empty_object_is() -> None:
    common = dict(task="fix", provider_id="chatgpt_codex", model_id="gpt-5.6-luna", profile="coding")
    omitted = StartAgentRunRequest(**common)
    explicit_null = StartAgentRunRequest(**common, limits=None)
    explicit_empty = StartAgentRunRequest(**common, limits={})
    assert omitted.limits is None
    assert explicit_null.limits is None
    assert explicit_empty.limits is not None and explicit_empty.limits.max_steps == 200

    implicit_spec = AgentRunSpec(
        task="fix", model=ModelRef(provider_id="chatgpt_codex", model_id="gpt-5.6-luna"),
        profile="coding", expected_artifacts=["diff"], quality_policy="strict",
    )
    explicit_spec = implicit_spec.model_copy(update={"limits": explicit_empty.limits})
    # model_copy does not change fields_set, so reconstruct to represent HTTP explicit intent.
    explicit_spec = AgentRunSpec(**{**implicit_spec.model_dump(), "limits": explicit_empty.limits.model_dump()})
    assert _quality_sized_run_spec(implicit_spec).limits.max_steps == 500
    assert _quality_sized_run_spec(explicit_spec).limits.max_steps == 200
''',
)

# Update the prior shell-diff test to the new authority contract.
write(
    "src/tests/agent_runtime/test_final_diff_validation_scope.py",
    '''from __future__ import annotations

from app.agent_runtime.coding_quality import diff_review_command_is_complete, validation_result_from_tool_event
from app.agent_runtime.contracts import AgentEvent, TaskRevision, ValidationSpec


def _revision() -> TaskRevision:
    return TaskRevision(
        revision_id="revision-1", run_id="run-1", sequence=1,
        user_instruction="Fix the UI", effective_objective="Fix the UI",
        validation_plan=[ValidationSpec(id="final-diff-review", kind="diff_review", description="Inspect authoritative run change set")],
    )


def test_shell_diff_is_inspection_context_not_completion_authority() -> None:
    for command in (
        "git diff --no-ext-diff", "git diff HEAD", "git diff -- src/apps/web/src/styles.css",
        "git diff --name-only", "git diff --stat",
    ):
        assert not diff_review_command_is_complete(command)
        result = validation_result_from_tool_event(
            AgentEvent(
                run_id="run-1", event_type="tool.completed",
                payload={"tool_call_id": "call", "args": {"command": command}, "result": {"details": {"exitCode": 0}}},
            ),
            run_id="run-1", task_revision_id="revision-1", workspace_state_id="state-1", revision=_revision(),
        )
        assert result is None


def test_authoritative_change_set_tool_must_match_candidate_state() -> None:
    good = validation_result_from_tool_event(
        AgentEvent(
            run_id="run-1", event_type="tool.completed",
            payload={"tool": "omnix_change_set", "tool_call_id": "cs", "result": {"details": {"change_set": {"change_set_id": "one", "candidate_workspace_state_id": "state-1"}}}},
        ),
        run_id="run-1", task_revision_id="revision-1", workspace_state_id="state-1", revision=_revision(),
    )
    assert good is not None and good.success and good.outcome == "passed"
    stale = validation_result_from_tool_event(
        AgentEvent(
            run_id="run-1", event_type="tool.completed",
            payload={"tool": "omnix_change_set", "tool_call_id": "cs2", "result": {"details": {"change_set": {"change_set_id": "old", "candidate_workspace_state_id": "state-old"}}}},
        ),
        run_id="run-1", task_revision_id="revision-1", workspace_state_id="state-1", revision=_revision(),
    )
    assert stale is not None and not stale.success and stale.outcome == "protocol_failure"
''',
)

# Token-reporting PostgreSQL regression appended to existing integration file.
path = "src/tests/persistence/test_agent_budget_integration.py"
text = read(path)
marker = "def test_token_reporting_distinguishes_missing_from_reported_zero()"
if marker not in text:
    text += '''\n\ndef test_token_reporting_distinguishes_missing_from_reported_zero() -> None:\n    database = _database()\n    try:\n        context = bootstrap_local_tenant(database)\n        run_id = _run(database, "reported-zero", RunLimits(max_steps=10, max_tool_calls=10))\n        manager = AgentBudgetManager(database, context=context)\n        before = manager.usage(run_id)\n        assert before["input_tokens"] == 0\n        assert before["output_tokens"] == 0\n        assert before["input_tokens_reported"] is False\n        assert before["output_tokens_reported"] is False\n\n        manager.record_token_usage(run_id, input_tokens=0, output_tokens=0)\n        after = manager.usage(run_id)\n        assert after["input_tokens"] == 0\n        assert after["output_tokens"] == 0\n        assert after["input_tokens_reported"] is True\n        assert after["output_tokens_reported"] is True\n        with unit_of_work(database) as work:\n            snapshot = PostgresAgentRunRepository(work.connection, context).get_run(run_id)\n            work.rollback()\n        assert snapshot is not None\n        assert snapshot.usage.input_tokens_reported is True\n        assert snapshot.usage.output_tokens_reported is True\n    finally:\n        database.close()\n'''
    write(path, text)

# Frontend source-level regression keeps missing != literal zero explicit even if UI refactors.
path = "src/tests/agent_runtime/test_candidate_authority_convergence.py"
text = read(path)
if "test_run_card_keeps_unreported_tokens_distinct_from_zero" not in text:
    text += '''\n\ndef test_run_card_keeps_unreported_tokens_distinct_from_zero() -> None:\n    from pathlib import Path\n    source = (Path(__file__).resolve().parents[2] / "apps/web/src/features/chatbot/OmnixRunCardCore.tsx").read_text(encoding="utf-8")\n    assert "if (reported !== true) return '—';" in source\n    assert "input_tokens_reported" in source\n    assert "output_tokens_reported" in source\n    assert "Not reported" in source\n'''
    write(path, text)

print("candidate authority patch applied")
