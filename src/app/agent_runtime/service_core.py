"""Durable orchestration service for generalized agent runs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import os
import re
import subprocess
from pathlib import Path
import tempfile
import threading
from typing import TypedDict

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work
from app.assistant_tools.repo_adapter import _github_repository_from_remote
from app.agent_runtime.capabilities import default_capability_registry

from .acceptance import evaluate_acceptance
from .active_objective import RoutingEnvironment, make_active_objective
from .evidence import (
    EvidenceCompilationError,
    compile_task_authority,
    evaluate_evidence_set,
    task_requires_workspace_mutation,
    validate_required_evidence_capabilities,
)
from .profiles import get_agent_profile, resolve_profile_capabilities
from .budget import AgentBudgetError, AgentBudgetManager
from .contracts import (
    AgentArtifact,
    AgentEvent,
    AgentRunCommand,
    AgentRunSnapshot,
    AgentRunSpec,
    EvidenceDecision,
    EvidencePolicy,
    EvidenceRequirement,
    ResourceScope,
    SubjectRef,
    SuccessCriterion,
    TaskRevision,
    WorkspaceSpec,
)
from .pi_runtime import PiAgentRuntime
from .repository import PostgresAgentRunRepository
from .semantic_task_parser import (
    classify_semantic_task_safely,
    default_semantic_task_parser,
)
from .turn_plan import TurnPlan, compile_turn_plan, derive_effective_objective
from .workspace import WorkspaceAuthority
from .workspace_dependencies import prepare_project_dependencies


_RETRYABLE_ACCEPTANCE_FAILURES = {
    "successful_test_command",
    "successful_typecheck_command",
    "successful_lint_command",
    "missing_diff_artifact",
    "missing_artifact:diff",
    "empty_diff_artifact",
    "modified_paths_not_task_relevant",
    "validation_not_task_relevant",
}

_CLARIFICATION_MARKER = re.compile(
    r"(?:^|\n)\s*(?:CLARIFICATION_REQUIRED|CLARIFY|NEED_CLARIFICATION)\s*[:\-]",
    re.I,
)
_CLARIFICATION_CUE = re.compile(
    r"(?:"
    r"\b(?:could|would|can)\s+you\s+(?:clarify|specify|tell|provide)\b|"
    r"\bplease\s+(?:clarify|specify|tell|provide)\b|"
    r"\b(?:i\s+)?need\s+(?:one\s+)?clarification\b|"
    r"\bno\s+specific\s+(?:implementation\s+)?request\b|"
    r"\bwhat\s+(?:behavior|change|visual\s+change|would\s+you\s+like)\b|"
    r"\bwhich\s+(?:one|option|behavior|change|file|target)\b"
    r")",
    re.I,
)


def _is_clarification_request(event: AgentEvent) -> bool:
    """Recognize a user-input request at the assistant turn boundary."""

    if event.event_type != "model.message" or event.payload.get("phase") != "message_end":
        return False
    if event.payload.get("clarification_suppressed") is True:
        return False
    if event.payload.get("requires_user_input") is True:
        return True
    text = str(event.payload.get("text") or "").strip()
    if not text:
        return False
    if _CLARIFICATION_MARKER.search(text):
        return True
    return bool(_CLARIFICATION_CUE.search(text)) and (
        "?" in text or bool(
            re.search(
                r"\b(?:no\s+specific\s+(?:implementation\s+)?request|need\s+(?:one\s+)?clarification)\b",
                text,
                re.I,
            )
        )
    )


class _DiffFileStat(TypedDict):
    path: str
    additions: int
    deletions: int


def _acceptance_retry_limit() -> int:
    raw = str(os.environ.get("OMNIX_AGENT_ACCEPTANCE_RETRY_LIMIT", "2") or "2").strip()
    try:
        return max(0, min(int(raw), 5))
    except ValueError:
        return 2


def _acceptance_failures_retryable(failures: list[str]) -> bool:
    if not failures:
        return False
    return all(
        failure in _RETRYABLE_ACCEPTANCE_FAILURES
        or failure.startswith("required_command:")
        for failure in failures
    )


def _progress_idle_timeout_seconds() -> int:
    # A live worker heartbeat is not agent progress. Keep the recovery window
    # short enough that a Pi turn which ended without a terminal event cannot
    # leave the run looking active for several minutes.
    raw = str(os.environ.get("OMNIX_AGENT_PROGRESS_IDLE_TIMEOUT_SECONDS", "120") or "120").strip()
    try:
        return max(60, min(int(raw), 86_400))
    except ValueError:
        return 120


def _stalled_recovery_limit() -> int:
    raw = str(os.environ.get("OMNIX_AGENT_STALLED_RECOVERY_LIMIT", "2") or "2").strip()
    try:
        return max(0, min(int(raw), 5))
    except ValueError:
        return 2


def _acceptance_retry_count(
    events: list[AgentEvent],
    task_revision_id: str | None,
) -> int:
    return sum(
        event.event_type == "acceptance.retry_requested"
        and event.payload.get("task_revision_id") == task_revision_id
        for event in events
    )


def _acceptance_retry_prompt(failures: list[str], *, attempt: int) -> str:
    joined = ", ".join(failures)
    return (
        f"Omnix acceptance did not pass ({joined}). Continue the same task; do not stop yet. "
        "Re-read the original user objective before making any repair: acceptance repair is not "
        "permission to change scope. Inspect the most recent failed or missing validation, correct "
        "the requested implementation or the relevant validation command as needed, and rerun the "
        "smallest task-relevant test/lint/typecheck until it exits successfully. For web UI work, "
        "the workspace command starts at the repository root, so use `npm --prefix src/apps/web "
        "run build` or `npm --prefix src/apps/web run test -- <focused-test>`; do not use "
        "Set-Location or shell directory changes. Do not substitute "
        "an unrelated passing test, unrelated diff, or pre-existing workspace change for completion. "
        f"This is automatic acceptance repair attempt {attempt}."
    )


def _diff_file_stats(diff: str, modified_paths: list[str]) -> list[_DiffFileStat]:
    stats: dict[str, _DiffFileStat] = {
        path: {"path": path, "additions": 0, "deletions": 0}
        for path in modified_paths
    }
    current_path = ""
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current_path = ""
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            candidate = line[4:].strip()
            if candidate != "/dev/null":
                if candidate.startswith(("a/", "b/")):
                    candidate = candidate[2:]
                current_path = candidate
                stats.setdefault(
                    current_path,
                    {"path": current_path, "additions": 0, "deletions": 0},
                )
            continue
        if not current_path:
            continue
        if line.startswith("+"):
            stats[current_path]["additions"] += 1
        elif line.startswith("-"):
            stats[current_path]["deletions"] += 1
    ordered_paths = [*modified_paths, *(path for path in stats if path not in modified_paths)]
    return [stats[path] for path in ordered_paths]


class AgentRunService:
    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        pi_path: str | None = None,
        worker_id: str | None = None,
        blob_store: LocalBlobStore | None = None,
    ) -> None:
        self.database = database or default_database()
        self.context = bootstrap_local_tenant(self.database)
        self.worker_id = worker_id or f"agent-worker:{os.getpid()}"
        self.blob_store = blob_store or LocalBlobStore()
        self.runtime = PiAgentRuntime(
            pi_path=pi_path or os.environ.get("OMNIX_PI_PATH", "pi"),
            event_sink=self._persist_runtime_event,
        )
        self.budgets = AgentBudgetManager(self.database, context=self.context)
        self._lock = threading.RLock()
        self._supervisor_lock = threading.Lock()
        self._supervisor_started = False
        self._supervisor_stop = threading.Event()

    def start(self, spec: AgentRunSpec) -> AgentRunSnapshot:
        return self.start_with_context(spec)

    def start_with_context(
        self,
        spec: AgentRunSpec,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
    ) -> AgentRunSnapshot:
        """Start a run with ephemeral Chat reference context and images.

        Reference context and image payloads are intentionally not written into
        AgentRunSpec or task revisions, so Chat retention and forget semantics
        remain owned by the Chat subsystem.
        """

        self._ensure_supervisor()
        self._validate_run_spec_authority(spec)
        self._validate_evidence_authority(spec)
        issued = self._prepare_workspace(self._bind_github_repository_authority(spec))
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = self._persist_starting_run(repository, issued)
            work.commit()
        if reference_context or reference_images:
            return self._launch_runtime(
                issued,
                snapshot,
                reference_context=reference_context,
                **({"reference_images": reference_images} if reference_images else {}),
            )
        return self._launch_runtime(issued, snapshot)

    def start_child(self, parent_run_id: str, request) -> AgentRunSnapshot:
        from .subagents import derive_child_spec, reserve_child_budget

        self._ensure_supervisor()
        initial_parent = self.get(parent_run_id)
        if initial_parent is None:
            raise KeyError(parent_run_id)
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            locked = work.connection.execute(
                """
                SELECT run_id
                  FROM omnix_agent_runs
                 WHERE workspace_id = %s AND run_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, parent_run_id),
            ).fetchone()
            if locked is None:
                raise KeyError(parent_run_id)
            parent = repository.get_run(parent_run_id)
            if parent is None:
                raise KeyError(parent_run_id)
            if parent.status in {"completed", "failed", "cancelled"}:
                raise ValueError("cannot start child from terminal parent")
            child_spec = derive_child_spec(parent, request)
            self._validate_run_spec_authority(child_spec)
            self._validate_evidence_authority(child_spec)
            existing = repository.list_children(parent_run_id)
            parent_usage = repository.get_usage(parent_run_id)
            reserve_child_budget(
                parent,
                existing,
                child_spec,
                parent_usage=parent_usage,
            )
            issued = self._prepare_workspace(
                self._bind_github_repository_authority(child_spec)
            )
            snapshot = self._persist_starting_run(repository, issued)
            work.commit()
        return self._launch_runtime(issued, snapshot)

    def _persist_starting_run(
        self,
        repository: PostgresAgentRunRepository,
        issued: AgentRunSpec,
    ) -> AgentRunSnapshot:
        snapshot = repository.create_run(issued)
        self._capture_workspace_baseline(repository, issued)
        repository.acquire_lease(issued.run_id, worker_id=self.worker_id, ttl_seconds=90)
        return repository.update_state(
            issued.run_id,
            expected_revision=snapshot.revision,
            status="starting",
            worker_id=self.worker_id,
        )

    def _launch_runtime(
        self,
        issued: AgentRunSpec,
        snapshot: AgentRunSnapshot,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
    ) -> AgentRunSnapshot:
        try:
            contextual_start = getattr(self.runtime, "start_with_context", None)
            if (reference_context or reference_images) and callable(contextual_start):
                contextual_start(
                    issued,
                    reference_context=reference_context,
                    **({"reference_images": reference_images} if reference_images else {}),
                )
            else:
                self.runtime.start(issued)
        except Exception as exc:
            self.runtime.close_run(issued.run_id)
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                current = repository.get_run(issued.run_id)
                if current is not None:
                    repository.update_state(
                        issued.run_id,
                        expected_revision=current.revision,
                        status="failed",
                        last_error=f"{type(exc).__name__}: {exc}"[:2000],
                    )
                self._maybe_finalize_parent_in_repository(repository, issued.run_id)
                work.commit()
            raise
        return self.get(issued.run_id) or snapshot

    def get(self, run_id: str) -> AgentRunSnapshot | None:
        self._ensure_supervisor()
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = repository.get_run(run_id)
            work.rollback()
            return snapshot

    def command(self, command: AgentRunCommand) -> AgentRunSnapshot:
        return self.command_with_context(command)

    def command_with_context(
        self,
        command: AgentRunCommand,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
        turn_plan: TurnPlan | None = None,
    ) -> AgentRunSnapshot:
        """Apply a command while keeping conversational context ephemeral."""

        self._ensure_supervisor()
        if command.command_type == "steer":
            current = self.get(command.run_id)
            if current is None:
                raise KeyError(command.run_id)
            steering = self._compile_steering(
                current,
                command,
                reference_context=reference_context,
                turn_plan=turn_plan,
            )
            if steering["superseding_spec"] is not None:
                return self._start_superseding_revision(
                    current,
                    command,
                    steering["revision"],
                    steering["superseding_spec"],
                    reference_context=reference_context,
                    **({"reference_images": reference_images} if reference_images else {}),
                )
            revision = steering["revision"]
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                repository.add_task_revision(revision)
                work.commit()
            command = command.model_copy(update={
                "payload": {
                    **command.payload,
                    "task_revision_id": revision.revision_id,
                    "effective_objective": revision.effective_objective,
                    "evidence_policy": revision.evidence_decision.policy.model_dump(mode="json"),
                }
            })
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            stored, status = repository.enqueue_command_with_status(command)
            current = repository.get_run(command.run_id)
            if current is None:
                raise KeyError(command.run_id)
            if current.status in {"completed", "failed", "cancelled"}:
                if status != "consumed" and repository.claim_command(
                    command.run_id,
                    stored.command_id,
                ):
                    repository.complete_command(
                        command.run_id,
                        stored.command_id,
                    )
                work.commit()
                return current
            if status == "consumed" or not repository.claim_command(command.run_id, stored.command_id):
                work.commit()
                return current
            work.commit()

        try:
            # Runtime callbacks persist status changes from the Pi reader
            # thread. Keep command-side desired-state changes and the
            # corresponding runtime transition in the same critical section
            # so a callback cannot advance the durable revision between our
            # read and optimistic update.
            with self._lock:
                current = self._apply_claimed_command(
                    stored,
                    reference_context=reference_context,
                    **({"reference_images": reference_images} if reference_images else {}),
                )
        except Exception as exc:
            self._mark_command_failed(stored, exc)
            raise
        else:
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                repository.complete_command(stored.run_id, stored.command_id)
                work.commit()

        if stored.command_type == "cancel":
            self._cancel_descendants(stored.run_id)
        if current.status in {"completed", "failed", "cancelled"}:
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                self._maybe_finalize_parent_in_repository(repository, stored.run_id)
                work.commit()
        return self.get(stored.run_id) or current

    @staticmethod
    def _validate_run_spec_authority(spec: AgentRunSpec) -> None:
        """Treat the durable service boundary as the final authority compiler."""
        profile = get_agent_profile(spec.profile)
        try:
            resolve_profile_capabilities(
                profile,
                requested=list(spec.capabilities),
                requested_external=list(spec.external_capabilities),
            )
        except ValueError as exc:
            raise EvidenceCompilationError(
                "run_spec_exceeds_profile_ceiling",
                str(exc),
            ) from exc
        if profile.requires_workspace and spec.workspace is None:
            raise EvidenceCompilationError(
                "required_workspace_unavailable",
                f"profile {profile.id} requires an explicitly issued workspace",
            )
        if not profile.requires_workspace and spec.workspace is not None:
            raise EvidenceCompilationError(
                "workspace_outside_profile_ceiling",
                f"profile {profile.id} does not permit local workspace authority",
            )

        registry = default_capability_registry()
        issued = set(spec.capabilities) | set(spec.external_capabilities)
        for scope in spec.resource_scopes:
            canonical = registry.canonical_id(scope.capability)
            if canonical is None:
                raise EvidenceCompilationError(
                    "unknown_resource_scope_capability",
                    f"resource scope references unknown capability {scope.capability}",
                )
            if canonical not in issued:
                raise EvidenceCompilationError(
                    "resource_scope_outside_run_authority",
                    f"resource scope {scope.capability} is not issued to this run",
                )

    def _validate_evidence_authority(self, spec: AgentRunSpec) -> None:
        if spec.evidence_policy.requirement != "required":
            return
        profile = get_agent_profile(spec.profile)
        decision = EvidenceDecision(
            policy=spec.evidence_policy,
            confidence=1.0,
            reason="run_spec_validation",
            classifier="deterministic",
        )
        compiled = compile_task_authority(profile, spec.objective or spec.task, decision)
        issued = set(spec.external_capabilities)
        missing_groups = [
            group
            for group in compiled.external_groups
            if not issued.intersection(group)
        ]
        if missing_groups:
            raise EvidenceCompilationError(
                "evidence_required_but_unavailable",
                "RunSpec does not issue any permitted capability for required evidence: "
                + "; ".join(",".join(group) for group in missing_groups),
            )
        issued_groups = tuple(
            tuple(cap for cap in group if cap in issued)
            for group in compiled.external_groups
            if issued.intersection(group)
        )
        grouped_evidence_caps = {
            cap
            for group in compiled.external_groups
            for cap in group
        }
        evidence_caps = tuple(
            cap
            for cap in compiled.required_external
            if cap in issued and cap in grouped_evidence_caps
        )
        validate_required_evidence_capabilities(
            evidence_caps,
            alternative_groups=issued_groups,
        )

    def _compile_steering(
        self,
        current: AgentRunSnapshot,
        command: AgentRunCommand,
        *,
        reference_context: str = "",
        turn_plan: TurnPlan | None = None,
    ) -> dict[str, object]:
        message = str(command.payload.get("message") or "").strip()
        reference_context = str(reference_context or "").strip()
        if not message:
            raise ValueError("steering message is required")
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            revisions = repository.list_task_revisions(current.run_id)
            work.rollback()
        latest = revisions[-1] if revisions else None
        previous_objective = (
            latest.effective_objective
            if latest is not None
            else (current.spec.objective or current.spec.task)
        )
        # Reconstruct the latest user instruction that actually changed
        # executable objective authority. Response-only and replay revisions
        # intentionally leave effective_objective unchanged and must not become
        # the replay target for a later direct/API steering command.
        prior_request = current.spec.task
        prior_effective = str(current.spec.objective or current.spec.task)
        for revision in revisions:
            if revision.effective_objective != prior_effective:
                prior_request = revision.user_instruction
            prior_effective = revision.effective_objective
        workspace_name = None
        if current.spec.workspace is not None:
            workspace_name = os.path.basename(
                str(current.spec.workspace.root or "").rstrip("\\/")
            ) or None
        routing_environment = RoutingEnvironment(
            active_workspace=workspace_name,
            workspace_source=("configured_default" if workspace_name else "none"),
            workspace_attached_this_turn=False,
        )

        if turn_plan is not None:
            # A TurnPlan passed through this keyword-only in-process boundary is
            # compiler output from Chat, not user command payload. Validate its
            # identity before using it, then compile authority again below.
            if turn_plan.latest_request != message:
                raise EvidenceCompilationError(
                    "turn_plan_message_mismatch",
                    "trusted TurnPlan does not match the steering message",
                )
            if turn_plan.active_run_id not in {None, current.run_id}:
                raise EvidenceCompilationError(
                    "turn_plan_run_mismatch",
                    "trusted TurnPlan targets a different Agent run",
                )
            if turn_plan.run_action != "steer_agent":
                raise EvidenceCompilationError(
                    "turn_plan_action_mismatch",
                    f"trusted TurnPlan cannot steer this run: {turn_plan.run_action}",
                )
            semantic_task = turn_plan.semantic_task
            semantic_compilation = turn_plan.compilation
        else:
            # Direct/non-Chat command callers have no trusted plan, so the
            # durable service performs the semantic parse exactly once here.
            active_objective = make_active_objective(
                canonical_request=prior_request,
                base_request=current.spec.task,
                profile=current.spec.profile,
                status="active",
                run_id=current.run_id,
            )
            semantic_task = classify_semantic_task_safely(
                default_semantic_task_parser(
                    provider_id=current.spec.model.provider_id,
                    model_id=current.spec.model.model_id,
                ),
                message,
                reference_context=reference_context,
                previous_objective=previous_objective,
                current_environment=routing_environment.model_dump(mode="json"),
            )
            if semantic_task is None:
                raise EvidenceCompilationError(
                    "semantic_parser_unavailable",
                    "steering requires semantic parsing; Omnix will not guess a stateful domain",
                )
            turn_plan = compile_turn_plan(
                message,
                semantic_task,
                active_objective=active_objective,
                routing_environment=routing_environment,
            )
            semantic_task = turn_plan.semantic_task
            semantic_compilation = turn_plan.compilation

        effective = derive_effective_objective(
            previous_objective,
            turn_plan,
        )
        # Compile policy from the TurnPlan's latest authoritative request only.
        # Previous objective remains reference-only and cannot widen authority.
        if semantic_compilation.requires_clarification:
            detail = "; ".join(
                anomaly.detail
                for anomaly in semantic_compilation.anomalies
            )
            raise EvidenceCompilationError(
                "semantic_clarification_required",
                detail or "steering has multiple plausible execution targets",
            )

        target_profile_id = semantic_compilation.profile_id or current.spec.profile
        target_profile = get_agent_profile(target_profile_id)
        decision = semantic_compilation.evidence_decision
        semantic_actions = list(semantic_compilation.action_intents)

        if (
            current.spec.workspace is not None
            and current.spec.workspace.repository
            and any(r.source_class in {"repo_ci_state", "repo_contents"} for r in decision.policy.requirements)
        ):
            repository_name = self._github_origin_repository(current.spec.workspace.repository)
            decision = decision.model_copy(update={
                "policy": self._bind_repository_evidence_policy(
                    decision.policy,
                    workspace=current.spec.workspace,
                    repository_name=repository_name,
                )
            })
        compiled = compile_task_authority(
            target_profile,
            turn_plan.effective_request,
            decision,
            semantic_action_intents=semantic_actions,
            allow_text_semantic_fallback=False,
        )
        required_local = set(compiled.required_local)
        required_external = set(compiled.required_external)
        issued_local = set(current.spec.capabilities)
        issued_external = set(current.spec.external_capabilities)
        fits = (
            target_profile_id == current.spec.profile
            and required_local.issubset(issued_local)
            and required_external.issubset(issued_external)
        )
        expected_artifacts = (
            ["diff"]
            if target_profile_id == "coding"
            and task_requires_workspace_mutation(
                turn_plan.effective_request,
                semantic_action_intents=semantic_actions,
                allow_text_semantic_fallback=False,
            )
            else []
        )
        checks = ["successful_test_command"] if expected_artifacts else []
        sequence = (latest.sequence + 1) if latest is not None else 2
        digest = hashlib.sha256(
            f"{current.run_id}:{command.idempotency_key}".encode("utf-8")
        ).hexdigest()
        revision = TaskRevision(
            revision_id=digest,
            run_id=current.run_id,
            sequence=sequence,
            previous_revision_id=latest.revision_id if latest else None,
            source_command_id=command.idempotency_key,
            user_instruction=message,
            effective_objective=effective,
            effective_success_criteria=[
                SuccessCriterion(
                    id="user-request",
                    description="Complete the latest effective user task and report verifiable evidence.",
                )
            ],
            evidence_decision=decision,
            required_local_capabilities=list(compiled.required_local),
            required_external_capabilities=list(compiled.required_external),
            expected_artifacts=expected_artifacts,
            acceptance_checks=checks,
        )
        if fits:
            return {"revision": revision, "superseding_spec": None}

        workspace = current.spec.workspace
        if target_profile.requires_workspace and workspace is None:
            raise EvidenceCompilationError(
                "required_workspace_unavailable",
                f"steering requires profile {target_profile_id}, but this run has no issued workspace",
            )
        replacement_run_id = hashlib.sha256(
            f"supersede:{current.run_id}:{command.idempotency_key}".encode("utf-8")
        ).hexdigest()
        replacement = AgentRunSpec(
            run_id=replacement_run_id,
            session_id=current.spec.session_id,
            task=turn_plan.effective_request,
            objective=effective,
            profile=target_profile_id,
            model=current.spec.model,
            capabilities=list(compiled.required_local),
            external_capabilities=list(compiled.required_external),
            context_sources=list(target_profile.context_sources),
            workspace=workspace if target_profile.requires_workspace else None,
            execution=current.spec.execution,
            limits=current.spec.limits,
            approval_policy=current.spec.approval_policy,
            request_mode=current.spec.request_mode,
            evidence_policy=decision.policy,
            supersedes_run_id=current.run_id,
            success_criteria=[
                SuccessCriterion(
                    id="user-request",
                    description="Complete the latest effective user task and report verifiable evidence.",
                )
            ],
            expected_artifacts=expected_artifacts,
        )
        return {"revision": revision, "superseding_spec": replacement}

    def _start_superseding_revision(
        self,
        current: AgentRunSnapshot,
        command: AgentRunCommand,
        revision: TaskRevision,
        replacement_spec: AgentRunSpec,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
    ) -> AgentRunSnapshot:
        """Atomically reserve a superseding run and its steering audit trail."""
        self._validate_run_spec_authority(replacement_spec)
        self._validate_evidence_authority(replacement_spec)
        issued = self._prepare_workspace(
            self._bind_github_repository_authority(replacement_spec)
        )

        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            locked = work.connection.execute(
                """
                SELECT superseded_by_run_id
                  FROM omnix_agent_runs
                 WHERE workspace_id = %s AND run_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, current.run_id),
            ).fetchone()
            if locked is None:
                raise KeyError(current.run_id)
            existing_replacement_id = str(locked[0]) if locked[0] else None
            if existing_replacement_id:
                replacement = repository.get_run(existing_replacement_id)
                if replacement is None:
                    raise RuntimeError("superseding run link points to missing run")
                work.rollback()
                return replacement

            stored, command_status = repository.enqueue_command_with_status(command)
            repository.add_task_revision(revision)
            repository.append_event(
                AgentEvent(
                    run_id=current.run_id,
                    event_type="steering.received",
                    payload={
                        "command_id": stored.command_id,
                        "idempotency_key": stored.idempotency_key,
                        "task_revision_id": revision.revision_id,
                        "superseding_run_id": issued.run_id,
                    },
                )
            )
            if command_status != "consumed" and repository.claim_command(
                current.run_id,
                stored.command_id,
            ):
                repository.complete_command(current.run_id, stored.command_id)

            snapshot = self._persist_starting_run(repository, issued)
            repository.mark_superseded(current.run_id, issued.run_id)
            work.commit()

        self.runtime.close_run(current.run_id)
        if reference_context or reference_images:
            return self._launch_runtime(
                issued,
                snapshot,
                reference_context=reference_context,
                reference_images=reference_images,
            )
        return self._launch_runtime(issued, snapshot)

    def _mark_command_failed(self, command: AgentRunCommand, error: Exception) -> None:
        """Make transport/runtime command failures visible and terminal.

        A command updates desired state before it reaches the local runtime. If
        the runtime process has already exited, leaving that intermediate state
        durable makes runs appear permanently paused or cancellation-pending.
        """
        self.runtime.close_run(command.run_id)
        terminal_status = "cancelled" if command.command_type == "cancel" else "failed"
        desired_state = "cancelled"
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            current = repository.get_run(command.run_id)
            if current is not None and current.status not in {"completed", "failed", "cancelled"}:
                repository.update_state(
                    command.run_id,
                    expected_revision=current.revision,
                    status=terminal_status,
                    desired_state=desired_state,
                    worker_id=self.worker_id,
                    last_error=f"command_failed:{type(error).__name__}: {error}"[:2000],
                )
            repository.complete_command(command.run_id, command.command_id)
            work.commit()
        if command.command_type == "cancel":
            self._cancel_descendants(command.run_id)

    def _apply_claimed_command(
        self,
        stored: AgentRunCommand,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
    ) -> AgentRunSnapshot:
        runtime_command = stored
        approval_request = None
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            current = repository.get_run(stored.run_id)
            if current is None:
                raise KeyError(stored.run_id)
            desired = current.desired_state
            status = current.status
            if stored.command_type in {"approve", "reject"}:
                approval_id = str(stored.payload.get("approval_id") or "")
                if not approval_id:
                    raise ValueError("approval_id is required")
                approval = repository.get_approval(stored.run_id, approval_id)
                if approval is None:
                    raise KeyError(approval_id)
                repository.resolve_approval(
                    stored.run_id,
                    approval_id,
                    approved=stored.command_type == "approve",
                    resolution_payload={"source": "agent_run_command"},
                )
                approval_request = approval.request_payload
                desired, status = "running", "running"
            elif stored.command_type == "pause":
                desired, status = "paused", "pause_requested"
            elif stored.command_type == "resume":
                desired, status = "running", "resume_requested"
            elif stored.command_type == "cancel":
                desired, status = "cancelled", "cancel_requested"
            current = repository.update_state(
                stored.run_id,
                expected_revision=current.revision,
                status=status,
                desired_state=desired,
            )
            if approval_request is not None:
                runtime_command = stored.model_copy(update={
                    "payload": {
                        **stored.payload,
                        "approval_request": approval_request,
                    }
                })
            work.commit()

        active = self.runtime.get_status(stored.run_id)
        if (
            active is None
            and stored.command_type == "steer"
            and current.status == "waiting_for_input"
        ):
            # The Pi process is local and may have disappeared while the
            # durable run was waiting. Rehydrate it on the user's answer
            # instead of terminalizing a perfectly valid clarification wait.
            self.runtime.start(current.spec)
            active = self.runtime.get_status(stored.run_id)
        if active is not None:
            contextual_command = getattr(self.runtime, "command_with_context", None)
            def send_runtime_command() -> None:
                if (
                    stored.command_type == "steer"
                    and (reference_context or reference_images)
                    and callable(contextual_command)
                ):
                    contextual_command(
                        stored,
                        reference_context=reference_context,
                        **({"reference_images": reference_images} if reference_images else {}),
                    )
                else:
                    self.runtime.command(runtime_command)

            try:
                send_runtime_command()
            except Exception:
                if stored.command_type != "steer" or current.status != "waiting_for_input":
                    raise
                # A stale in-memory session can still have a snapshot even
                # though its child process exited. Recreate it once and retry
                # the user's answer while the durable run remains waiting.
                self.runtime.close_run(stored.run_id)
                self.runtime.start(current.spec)
                send_runtime_command()
            runtime_status = self.runtime.get_status(stored.run_id)
            if runtime_status is not None:
                with unit_of_work(self.database) as work:
                    repository = PostgresAgentRunRepository(work.connection, self.context)
                    persisted = repository.get_run(stored.run_id)
                    if persisted is not None:
                        current = repository.update_state(
                            stored.run_id,
                            expected_revision=persisted.revision,
                            status=runtime_status.status,
                            desired_state=runtime_status.desired_state,
                        )
                    work.commit()
        elif stored.command_type == "cancel":
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                persisted = repository.get_run(stored.run_id)
                if persisted is not None and persisted.status != "cancelled":
                    current = repository.update_state(
                        stored.run_id,
                        expected_revision=persisted.revision,
                        status="cancelled",
                        desired_state="cancelled",
                    )
                work.commit()
        return current

    def _cancel_descendants(self, run_id: str) -> None:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            children = repository.list_children(run_id)
            work.rollback()
        for child in children:
            if child.status in {"completed", "failed", "cancelled"}:
                continue
            self.command(
                AgentRunCommand(
                    run_id=child.run_id,
                    command_type="cancel",
                    payload={"reason": f"parent_cancelled:{run_id}"},
                    idempotency_key=f"parent-cancel:{run_id}:{child.run_id}",
                )
            )

    def events(self, run_id: str, *, after_sequence: int = 0) -> list[AgentEvent]:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            rows = repository.list_events(run_id, after_sequence=after_sequence)
            work.rollback()
            return rows

    def approvals(self, run_id: str, *, state: str | None = None):
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            rows = repository.list_approvals(run_id, state=state)
            work.rollback()
            return rows

    def artifacts(self, run_id: str) -> list[AgentArtifact]:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            rows = repository.list_artifacts(run_id)
            work.rollback()
            return rows

    def task_revisions(self, run_id: str) -> list[TaskRevision]:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            rows = repository.list_task_revisions(run_id)
            work.rollback()
            return rows

    def evidence_receipts(self, run_id: str):
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            rows = repository.list_evidence_receipts(run_id)
            work.rollback()
            return rows

    def evidence_set(self, run_id: str):
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = repository.get_run(run_id)
            if snapshot is None:
                work.rollback()
                raise KeyError(run_id)
            revision = repository.latest_task_revision(run_id)
            receipts = repository.list_evidence_receipts(run_id)
            work.rollback()
        policy = revision.evidence_decision.policy if revision is not None else snapshot.spec.evidence_policy
        receipts = self._receipts_for_revision(receipts, revision)
        return evaluate_evidence_set(run_id, policy, receipts)

    def _maybe_finalize_parent_in_repository(
        self,
        repository: PostgresAgentRunRepository,
        child_run_id: str,
    ) -> None:
        child = repository.get_run(child_run_id)
        if child is None or not child.spec.parent_run_id:
            return
        if child.status not in {"completed", "failed", "cancelled"}:
            return
        parent = repository.get_run(child.spec.parent_run_id)
        if parent is None or parent.status != "waiting_for_children":
            return
        terminal, failed = self._children_terminal_state(repository, parent.run_id)
        if not terminal:
            return
        if failed:
            repository.update_state(
                parent.run_id,
                expected_revision=parent.revision,
                status="failed",
                last_error="acceptance_failed:child_run_failed",
            )
        else:
            self._finalize_acceptance(repository, parent)

    @staticmethod
    def _children_terminal_state(repository: PostgresAgentRunRepository, run_id: str) -> tuple[bool, bool]:
        children = repository.list_children(run_id)
        if not children:
            return True, False
        terminal = all(child.status in {"completed", "failed", "cancelled"} for child in children)
        failed = any(child.status in {"failed", "cancelled"} for child in children)
        return terminal, failed

    def _finalize_acceptance(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
    ) -> None:
        task_revision = repository.latest_task_revision(current.run_id)
        revision_id = task_revision.revision_id if task_revision is not None else None
        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="acceptance.started",
                payload={"source": "omnix", "task_revision_id": revision_id},
            )
        )
        self._capture_diff(
            repository,
            current.spec,
            task_revision_id=revision_id,
        )
        all_events = repository.list_events(current.run_id, after_sequence=0, limit=5000)
        all_artifacts = repository.list_artifacts(current.run_id)
        all_receipts = repository.list_evidence_receipts(current.run_id)
        events = self._events_for_revision(all_events, task_revision)
        artifacts = self._artifacts_for_revision(all_artifacts, task_revision)
        receipts = self._receipts_for_revision(all_receipts, task_revision)
        effective_policy = (
            task_revision.evidence_decision.policy
            if task_revision is not None
            else current.spec.evidence_policy
        )
        evidence_set = evaluate_evidence_set(current.run_id, effective_policy, receipts)
        result = evaluate_acceptance(
            current.spec,
            events=events,
            artifacts=artifacts,
            task_revision=task_revision,
            evidence_set=evidence_set,
        )
        children_terminal, child_failed = self._children_terminal_state(repository, current.run_id)
        failures = list(result.failures)
        if not children_terminal:
            failures.append("children_not_terminal")
        if child_failed:
            failures.append("child_run_failed")
        passed = result.passed and not failures

        retry_count = _acceptance_retry_count(all_events, revision_id)
        try:
            runtime_available = self.runtime.get_status(current.run_id) is not None
        except Exception:
            runtime_available = False
        retrying = (
            not passed
            and runtime_available
            and retry_count < _acceptance_retry_limit()
            and _acceptance_failures_retryable(failures)
        )
        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="acceptance.completed",
                payload={
                    **result.model_dump(mode="json"),
                    "passed": passed,
                    "failures": failures,
                    "retrying": retrying,
                    "retry_attempt": retry_count + 1 if retrying else None,
                    "task_revision_id": task_revision.revision_id if task_revision else None,
                    "evidence_set": evidence_set.model_dump(mode="json"),
                },
            )
        )
        latest = repository.get_run(current.run_id) or current
        if retrying:
            attempt = retry_count + 1
            repository.append_event(
                AgentEvent(
                    run_id=current.run_id,
                    event_type="acceptance.retry_requested",
                    payload={
                        "source": "omnix",
                        "attempt": attempt,
                        "failures": failures,
                        "task_revision_id": revision_id,
                    },
                )
            )
            retry_snapshot = repository.update_state(
                current.run_id,
                expected_revision=latest.revision,
                status="running",
                desired_state="running",
                worker_id=self.worker_id,
                last_error=None,
            )
            retry_prompt = _acceptance_retry_prompt(failures, attempt=attempt)
            try:
                self.runtime.command(
                    AgentRunCommand(
                        run_id=current.run_id,
                        command_type="resume",
                        payload={"message": retry_prompt},
                        idempotency_key=(
                            f"acceptance-retry:{current.run_id}:{attempt}:"
                            f"{hashlib.sha256(retry_prompt.encode('utf-8')).hexdigest()[:16]}"
                        ),
                    )
                )
            except Exception as exc:
                error = f"acceptance_retry_failed:{type(exc).__name__}: {exc}"[:2000]
                repository.append_event(
                    AgentEvent(
                        run_id=current.run_id,
                        event_type="run.failed",
                        payload={"source": "omnix", "error": error},
                    )
                )
                repository.update_state(
                    current.run_id,
                    expected_revision=retry_snapshot.revision,
                    status="failed",
                    desired_state="cancelled",
                    worker_id=self.worker_id,
                    last_error=error,
                )
            return

        repository.update_state(
            current.run_id,
            expected_revision=latest.revision,
            status="completed" if passed else "failed",
            worker_id=self.worker_id,
            last_error=None if passed else "acceptance_failed:" + ",".join(failures),
        )

    def _persist_runtime_event(self, event: AgentEvent) -> None:
        with self._lock:
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                current = repository.get_run(event.run_id)
                if current is None:
                    work.rollback()
                    return
                if _is_clarification_request(event):
                    event = event.model_copy(update={
                        "payload": {
                            **event.payload,
                            "requires_user_input": True,
                        }
                    })
                repository.append_event(event)
                if current.status in {"completed", "failed", "cancelled"}:
                    work.commit()
                    return
                if _is_clarification_request(event):
                    repository.update_state(
                        event.run_id,
                        expected_revision=current.revision,
                        status="waiting_for_input",
                        desired_state="paused",
                        worker_id=self.worker_id,
                        last_error=None,
                    )
                elif event.event_type == "run.started" and current.status != "running":
                    current = repository.update_state(
                        event.run_id,
                        expected_revision=current.revision,
                        status="running",
                        worker_id=self.worker_id,
                    )
                elif event.event_type in {"run.settled", "run.completed"}:
                    if current.status not in {
                        "waiting_for_approval",
                        "waiting_for_input",
                        "pause_requested",
                        "paused",
                        "cancel_requested",
                        "cancelled",
                    }:
                        children_terminal, _ = self._children_terminal_state(repository, event.run_id)
                        if children_terminal:
                            self._finalize_acceptance(repository, current)
                        else:
                            repository.update_state(
                                event.run_id,
                                expected_revision=current.revision,
                                status="waiting_for_children",
                                worker_id=self.worker_id,
                            )
                elif event.event_type == "run.failed":
                    repository.update_state(
                        event.run_id,
                        expected_revision=current.revision,
                        status="failed",
                        worker_id=self.worker_id,
                        last_error=str(event.payload.get("error") or "Pi runtime failed")[:2000],
                    )
                self._maybe_finalize_parent_in_repository(repository, event.run_id)
                work.commit()
    @staticmethod
    def _events_for_revision(
        events: list[AgentEvent],
        task_revision: TaskRevision | None,
    ) -> list[AgentEvent]:
        if task_revision is None:
            return [
                event
                for event in events
                if event.event_type not in {"tool.started", "tool.completed", "tool.output"}
                or event.payload.get("task_revision_id") is None
            ]
        if task_revision.sequence <= 1:
            return [
                event
                for event in events
                if event.event_type not in {"tool.started", "tool.completed", "tool.output"}
                or event.payload.get("task_revision_id") in {None, task_revision.revision_id}
            ]
        return [
            event
            for event in events
            if event.event_type not in {"tool.started", "tool.completed", "tool.output"}
            or event.payload.get("task_revision_id") == task_revision.revision_id
        ]

    @staticmethod
    def _artifacts_for_revision(
        artifacts: list[AgentArtifact],
        task_revision: TaskRevision | None,
    ) -> list[AgentArtifact]:
        if task_revision is None or task_revision.sequence <= 1:
            return [
                artifact
                for artifact in artifacts
                if artifact.metadata.get("task_revision_id") in {None, task_revision.revision_id if task_revision else None}
            ]
        return [
            artifact
            for artifact in artifacts
            if artifact.metadata.get("task_revision_id") == task_revision.revision_id
        ]

    @staticmethod
    def _receipts_for_revision(receipts, task_revision: TaskRevision | None):
        if task_revision is None:
            return [receipt for receipt in receipts if receipt.task_revision_id is None]
        return [
            receipt
            for receipt in receipts
            if receipt.task_revision_id == task_revision.revision_id
        ]

    def _capture_workspace_baseline(
        self,
        repository: PostgresAgentRunRepository,
        spec: AgentRunSpec,
    ) -> None:
        if spec.workspace is None or "diff" not in spec.expected_artifacts:
            return
        root = spec.workspace.worktree or spec.workspace.root
        baseline = WorkspaceAuthority(root).provenance_snapshot()
        repository.add_artifact(
            AgentArtifact(
                run_id=spec.run_id,
                kind="other",
                name="workspace-baseline.json",
                metadata={
                    "head": baseline["head"],
                    "dirty_paths": baseline["dirty_paths"],
                    "dirty_digests": baseline["dirty_digests"],
                },
            )
        )

    def _capture_diff(
        self,
        repository: PostgresAgentRunRepository,
        spec: AgentRunSpec,
        *,
        task_revision_id: str | None = None,
    ) -> None:
        if spec.workspace is None:
            return
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
                # Mutating runs must have a start-of-run provenance snapshot.
                # Failing closed prevents a pre-existing dirty workspace from
                # being misattributed to a recovered or legacy run.
                return
            baseline_metadata = baseline_artifact.metadata
            dirty_paths = (
                baseline_metadata.get("dirty_paths")
                if isinstance(baseline_metadata.get("dirty_paths"), list)
                else []
            )
            dirty_digests = (
                baseline_metadata.get("dirty_digests")
                if isinstance(baseline_metadata.get("dirty_digests"), dict)
                else {}
            )
            modified_paths = authority.run_owned_paths(dirty_paths)
            baseline_conflicts = authority.baseline_conflicts(
                {str(key): str(value) for key, value in dirty_digests.items()}
            )
            diff = authority.git_diff(modified_paths)
        except Exception:
            return
        content = diff.encode("utf-8")
        workspace_key = hashlib.sha256(
            self.context.workspace_id.encode("utf-8")
        ).hexdigest()[:16]
        run_key = hashlib.sha256(spec.run_id.encode("utf-8")).hexdigest()
        blob = self.blob_store.put_bytes(
            f"agent/runs/{workspace_key}/{run_key}/workspace.diff",
            content,
        )
        preview_limit = 16_000
        file_stats = _diff_file_stats(diff, modified_paths)
        repository.add_artifact(
            AgentArtifact(
                run_id=spec.run_id,
                kind="diff",
                name="workspace.diff",
                storage_ref=str(blob["storage_key"]),
                checksum=str(blob["checksum_sha256"]),
                metadata={
                    "task_revision_id": task_revision_id,
                    "storage_provider": str(blob["storage_provider"]),
                    "byte_size": int(blob["byte_size"]),
                    "preview": diff[:preview_limit],
                    "truncated": len(diff) > preview_limit,
                    "modified_paths": modified_paths,
                    "file_stats": file_stats,
                    "additions": sum(item["additions"] for item in file_stats),
                    "deletions": sum(item["deletions"] for item in file_stats),
                    "baseline_conflicts": baseline_conflicts,
                },
            )
        )

    def recover_orphaned_runs(self) -> list[str]:
        """Re-acquire expired/unowned non-terminal runs and resume from workspace truth."""
        recovered: list[str] = []
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT run.run_id
                  FROM omnix_agent_runs AS run
                  LEFT JOIN omnix_agent_worker_leases AS lease
                    ON lease.workspace_id = run.workspace_id AND lease.run_id = run.run_id
                 WHERE run.workspace_id = %s
                   AND run.status IN ('queued','starting','running','resume_requested')
                   AND run.desired_state = 'running'
                   AND (lease.run_id IS NULL OR lease.lease_expires_at <= CURRENT_TIMESTAMP)
                 ORDER BY run.created_at
                """,
                (self.context.workspace_id,),
            ).fetchall()
            work.rollback()
        for row in rows:
            run_id = str(row[0])
            snapshot = self.get(run_id)
            if snapshot is None or self.runtime.get_status(run_id) is not None:
                continue
            try:
                with unit_of_work(self.database) as work:
                    repository = PostgresAgentRunRepository(work.connection, self.context)
                    repository.acquire_lease(run_id, worker_id=self.worker_id, ttl_seconds=90)
                    repository.reset_processing_commands(run_id)
                    current = repository.get_run(run_id)
                    if current is not None:
                        repository.update_state(
                            run_id,
                            expected_revision=current.revision,
                            status="starting",
                            worker_id=self.worker_id,
                        )
                    work.commit()
                self.runtime.start(snapshot.spec)
                with unit_of_work(self.database) as work:
                    repository = PostgresAgentRunRepository(work.connection, self.context)
                    pending = repository.list_pending_commands(run_id)
                    latest_revision = repository.latest_task_revision(run_id)
                    work.rollback()
                for pending_command in pending:
                    current = self.command(pending_command)
                    if current.status in {"completed", "failed", "cancelled"} or current.desired_state != "running":
                        break
                current = self.get(run_id)
                if current is None:
                    raise RuntimeError("recovered run disappeared")
                if current.status in {"completed", "failed", "cancelled"} or current.desired_state != "running":
                    recovered.append(run_id)
                    continue
                recovery_payload = {
                    "message": "This run was recovered after a worker restart. Reinspect the current workspace before continuing.",
                }
                if latest_revision is not None:
                    recovery_payload.update({
                        "effective_objective": latest_revision.effective_objective,
                        "evidence_policy": latest_revision.evidence_decision.policy.model_dump(mode="json"),
                        "task_revision_id": latest_revision.revision_id,
                    })
                self.runtime.command(
                    AgentRunCommand(
                        run_id=run_id,
                        command_type="steer",
                        payload=recovery_payload,
                    )
                )
                recovered.append(run_id)
            except Exception as exc:
                self._fail_recovery(run_id, exc)
                continue
        return recovered

    def _fail_recovery(self, run_id: str, exc: Exception) -> None:
        self.runtime.close_run(run_id)
        with unit_of_work(self.database) as work:
            locked = work.connection.execute(
                """
                SELECT run_id
                  FROM omnix_agent_runs
                 WHERE workspace_id = %s AND run_id = %s
                 FOR UPDATE
                """,
                (self.context.workspace_id, run_id),
            ).fetchone()
            if locked is None:
                work.rollback()
                return
            repository = PostgresAgentRunRepository(work.connection, self.context)
            current = repository.get_run(run_id)
            if current is not None and current.status not in {"completed", "failed", "cancelled"}:
                repository.update_state(
                    run_id,
                    expected_revision=current.revision,
                    status="failed",
                    desired_state="cancelled",
                    worker_id=self.worker_id,
                    last_error=f"recovery_failed:{type(exc).__name__}: {exc}"[:2000],
                )
                self._maybe_finalize_parent_in_repository(repository, run_id)
            work.commit()

    def _ensure_supervisor(self) -> None:
        if self._supervisor_started:
            return
        with self._supervisor_lock:
            if self._supervisor_started:
                return
            self._supervisor_started = True
            threading.Thread(
                target=self._supervisor_loop,
                name="omnix-agent-supervisor",
                daemon=True,
            ).start()

    def _supervisor_loop(self) -> None:
        while not self._supervisor_stop.is_set():
            try:
                self._supervise_once()
            except Exception:
                pass
            self._supervisor_stop.wait(30.0)

    def _supervise_once(self) -> None:
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT run_id
                  FROM omnix_agent_runs
                 WHERE workspace_id = %s AND worker_id = %s
                   AND status NOT IN ('completed','failed','cancelled')
                """,
                (self.context.workspace_id, self.worker_id),
            ).fetchall()
            work.rollback()
        for row in rows:
            run_id = str(row[0])
            try:
                self.budgets.enforce_wall_time(run_id)
            except AgentBudgetError:
                self.runtime.close_run(run_id)
                self._cancel_descendants(run_id)
                continue
            try:
                self.heartbeat(run_id, ttl_seconds=90)
            except Exception:
                continue
            try:
                self._supervise_stalled_run(run_id)
            except Exception:
                # A transient supervisor/database failure must not take down
                # supervision for every other active run. Lease expiry and
                # orphan recovery remain the fallback safety net.
                continue

        with unit_of_work(self.database) as work:
            terminal_parents = work.connection.execute(
                """
                SELECT DISTINCT parent.run_id
                  FROM omnix_agent_runs AS parent
                  JOIN omnix_agent_runs AS child
                    ON child.workspace_id = parent.workspace_id
                   AND child.parent_run_id = parent.run_id
                 WHERE parent.workspace_id = %s
                   AND parent.status IN ('completed','failed','cancelled')
                   AND child.status NOT IN ('completed','failed','cancelled')
                 ORDER BY parent.run_id
                """,
                (self.context.workspace_id,),
            ).fetchall()
            work.rollback()
        for row in terminal_parents:
            self._cancel_descendants(str(row[0]))

        active_ids = self.runtime.active_run_ids()
        if active_ids:
            with unit_of_work(self.database) as work:
                terminal_runtime_rows = work.connection.execute(
                    """
                    SELECT run_id
                      FROM omnix_agent_runs
                     WHERE workspace_id = %s
                       AND run_id = ANY(%s)
                       AND status IN ('completed','failed','cancelled')
                    """,
                    (self.context.workspace_id, list(active_ids)),
                ).fetchall()
                work.rollback()
            for row in terminal_runtime_rows:
                self.runtime.close_run(str(row[0]))

        self.recover_orphaned_runs()

    def _supervise_stalled_run(self, run_id: str) -> None:
        """Recover a leased run whose runtime stopped making progress.

        Worker heartbeats only establish that the supervisor thread is alive.
        The durable event log is the progress source of truth. A bounded
        restart keeps a hung model/tool process from remaining ``running``
        forever, while preserving the existing workspace and task revision.
        """
        now = datetime.now(timezone.utc)
        terminalize = False
        current: AgentRunSnapshot | None = None
        attempt = 0
        progress_event: AgentEvent | None = None

        with self._lock:
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                current = repository.get_run(run_id)
                if current is None or current.status != "running" or current.desired_state != "running":
                    work.rollback()
                    return
                progress_event = repository.latest_progress_event(run_id)
                progress_at = (
                    progress_event.created_at
                    if progress_event is not None
                    else current.updated_at or current.created_at
                )
                if progress_at is None:
                    work.rollback()
                    return
                if progress_at.tzinfo is None:
                    progress_at = progress_at.replace(tzinfo=timezone.utc)
                if now - progress_at < timedelta(seconds=_progress_idle_timeout_seconds()):
                    work.rollback()
                    return

                attempt = repository.count_events(run_id, "run.recovery_requested") + 1
                quality_stage = None
                list_events = getattr(repository, "list_events", None)
                if callable(list_events):
                    for event in reversed(list_events(run_id, after_sequence=0, limit=5000)):
                        if event.event_type == "quality.stage":
                            quality_stage = str(event.payload.get("stage") or "").strip() or None
                            break
                reason = (
                    f"no durable agent progress for {int((now - progress_at).total_seconds())}s"
                    f" after {progress_event.event_type if progress_event else 'run start'}"
                )
                if attempt > _stalled_recovery_limit():
                    terminalize = True
                    repository.append_event(AgentEvent(
                        run_id=run_id,
                        event_type="run.recovery_failed",
                        payload={
                            "attempt": attempt,
                            "reason": reason,
                            "recovery_limit": _stalled_recovery_limit(),
                        },
                    ))
                    repository.update_state(
                        run_id,
                        expected_revision=current.revision,
                        status="failed",
                        desired_state="cancelled",
                        worker_id=self.worker_id,
                        last_error=f"stalled_run:{reason}; recovery limit exhausted"[:2000],
                    )
                else:
                    repository.append_event(AgentEvent(
                        run_id=run_id,
                        event_type="run.recovery_requested",
                        payload={
                            "attempt": attempt,
                            "reason": reason,
                            "last_progress_event": progress_event.event_type if progress_event else None,
                            "last_progress_sequence": progress_event.sequence if progress_event else None,
                            "quality_stage": quality_stage,
                        },
                    ))
                    current = repository.update_state(
                        run_id,
                        expected_revision=current.revision,
                        status="resume_requested",
                        desired_state="running",
                        worker_id=self.worker_id,
                    )
                work.commit()

            if terminalize:
                self.runtime.close_run(run_id)
                self._cancel_descendants(run_id)
                return

            assert current is not None
            recovery_message = (
                "The previous runtime stopped producing progress. The workspace and durable task "
                "state are authoritative. Resume the current task from the existing workspace, "
                "inspect the last failed or incomplete operation, and continue without changing scope. "
                "The task and objective are already authoritative; do not ask the user to restate the "
                "request or wait for clarification. "
                + (
                    "This is an internal quality/self-review turn that did not finish its protocol. "
                    "Do not modify files or ask the user a question; inspect the current final state and "
                    "return ONLY the required structured verdict JSON, even if the verdict is blocked. "
                    if quality_stage == "self_review"
                    else "If this is an internal quality/self-review turn, return its required structured verdict exactly, even if the verdict is blocked. "
                )
                + f"This is automatic recovery attempt {attempt}."
            )
            get_runtime_status = getattr(self.runtime, "get_status", None)
            runtime_status = (
                get_runtime_status(run_id)
                if callable(get_runtime_status)
                else None
            )
            reuse_active_session = quality_stage == "self_review" and runtime_status is not None
            if not reuse_active_session:
                self.runtime.close_run(run_id)
            try:
                if not reuse_active_session:
                    self.runtime.start(current.spec)
                self.runtime.command(AgentRunCommand(
                    run_id=run_id,
                    command_type="resume",
                    payload={"message": recovery_message, "recovery_attempt": attempt},
                    idempotency_key=f"stalled-recovery:{run_id}:{attempt}",
                ))
                with unit_of_work(self.database) as work:
                    repository = PostgresAgentRunRepository(work.connection, self.context)
                    persisted = repository.get_run(run_id)
                    if persisted is not None and persisted.status not in {"completed", "failed", "cancelled"}:
                        repository.update_state(
                            run_id,
                            expected_revision=persisted.revision,
                            status="running",
                            desired_state="running",
                            worker_id=self.worker_id,
                        )
                    work.commit()
            except Exception as exc:
                self.runtime.close_run(run_id)
                with unit_of_work(self.database) as work:
                    repository = PostgresAgentRunRepository(work.connection, self.context)
                    persisted = repository.get_run(run_id)
                    if persisted is not None and persisted.status not in {"completed", "failed", "cancelled"}:
                        repository.append_event(AgentEvent(
                            run_id=run_id,
                            event_type="run.recovery_failed",
                            payload={"attempt": attempt, "reason": f"{type(exc).__name__}: {exc}"[:2000]},
                        ))
                        repository.update_state(
                            run_id,
                            expected_revision=persisted.revision,
                            status="failed",
                            desired_state="cancelled",
                            worker_id=self.worker_id,
                            last_error=f"stalled_recovery_failed:{type(exc).__name__}: {exc}"[:2000],
                        )
                    work.commit()
                self._cancel_descendants(run_id)

    def heartbeat(self, run_id: str, *, ttl_seconds: int = 60) -> None:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            repository.acquire_lease(run_id, worker_id=self.worker_id, ttl_seconds=ttl_seconds)
            repository.append_event(
                AgentEvent(run_id=run_id, event_type="worker.heartbeat", payload={"worker_id": self.worker_id})
            )
            work.commit()

    @staticmethod
    def _github_origin_repository(repository: str) -> str:
        root = Path(repository).expanduser().resolve()
        completed = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            raise ValueError("github authority requires a readable origin remote")
        owner, name = _github_repository_from_remote(completed.stdout.strip())
        return f"{owner}/{name}"

    @staticmethod
    def _resolve_repository_commit(repository: str, ref: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(Path(repository).expanduser().resolve()), "rev-parse", ref],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            shell=False,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            raise ValueError(f"unable to resolve repository ref: {ref}")
        return completed.stdout.strip()

    @classmethod
    def _bind_repository_evidence_policy(
        cls,
        policy: EvidencePolicy,
        *,
        workspace: WorkspaceSpec,
        repository_name: str,
    ) -> EvidencePolicy:
        if not any(
            requirement.source_class in {"repo_ci_state", "repo_contents"}
            for requirement in policy.requirements
        ):
            return policy
        resolved_commit = cls._resolve_repository_commit(
            workspace.repository or workspace.root,
            workspace.base_ref,
        )
        requirements: list[EvidenceRequirement] = []
        for requirement in policy.requirements:
            if requirement.source_class not in {"repo_ci_state", "repo_contents"}:
                requirements.append(requirement)
                continue
            prior = requirement.subject
            qualifiers = dict(prior.qualifiers if prior else {})
            qualifiers.update({
                "requested_ref": workspace.base_ref,
                "resolved_commit": resolved_commit,
            })
            requirements.append(requirement.model_copy(update={
                "subject": SubjectRef(
                    type="repository_ref",
                    canonical_id=repository_name,
                    display_name=repository_name,
                    qualifiers=qualifiers,
                )
            }))
        return policy.model_copy(update={"requirements": requirements})

    @classmethod
    def _bind_github_repository_authority(
        cls,
        spec: AgentRunSpec,
    ) -> AgentRunSpec:
        github_capabilities = {
            capability
            for capability in spec.external_capabilities
            if capability.startswith("github.")
        }
        if not github_capabilities:
            return spec
        workspace = spec.workspace
        if workspace is None or not workspace.repository:
            raise ValueError(
                "GitHub capabilities require a repository-backed workspace"
            )
        repository = cls._github_origin_repository(workspace.repository)
        scopes: list[ResourceScope] = []
        explicitly_scoped: set[str] = set()
        for scope in spec.resource_scopes:
            if scope.capability not in github_capabilities:
                scopes.append(scope)
                continue
            if (
                scope.resource_type.casefold() not in {"repository", "repo"}
                or scope.resource_id.casefold() != repository.casefold()
            ):
                raise ValueError(
                    f"GitHub resource scope exceeds issued repository: {scope.capability}"
                )
            explicitly_scoped.add(scope.capability)
            scopes.append(
                scope.model_copy(
                    update={
                        "resource_type": "repository",
                        "resource_id": repository,
                    }
                )
            )
        for capability in sorted(github_capabilities - explicitly_scoped):
            scopes.append(
                ResourceScope(
                    capability=capability,
                    resource_type="repository",
                    resource_id=repository,
                )
            )
        bound_policy = cls._bind_repository_evidence_policy(
            spec.evidence_policy,
            workspace=workspace,
            repository_name=repository,
        )
        return spec.model_copy(update={
            "resource_scopes": scopes,
            "evidence_policy": bound_policy,
        })

    @staticmethod
    def _prepare_workspace(spec: AgentRunSpec) -> AgentRunSpec:
        workspace = spec.workspace
        if workspace is None:
            # Read-only research and other non-workspace profiles retain an
            # explicit None workspace. PiRpcSession supplies an ephemeral cwd
            # without turning it into repository authority.
            return spec
        if not workspace.repository or workspace.worktree:
            return spec
        root = Path(
            os.environ.get(
                "OMNIX_AGENT_WORKTREE_ROOT",
                str(Path(tempfile.gettempdir()) / "omnix-agent-worktrees"),
            )
        ).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        target = root / spec.run_id
        authority = WorkspaceAuthority.create_worktree(
            workspace.repository,
            target,
            base_ref=workspace.base_ref,
        )
        try:
            prepare_project_dependencies(repository=workspace.repository, worktree=authority.root)
        except Exception:
            try:
                WorkspaceAuthority.remove_worktree(workspace.repository, authority.root)
            except Exception:
                # Preserve the actionable dependency error; the supervisor can
                # reconcile an orphaned temporary worktree on its next pass.
                pass
            raise
        issued_workspace = workspace.model_copy(update={"root": str(authority.root), "worktree": str(authority.root)})
        return spec.model_copy(update={"workspace": issued_workspace})


@lru_cache(maxsize=1)
def default_agent_run_service() -> AgentRunService:
    return AgentRunService()
