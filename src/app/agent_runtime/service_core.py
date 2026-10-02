"""Durable orchestration service for generalized agent runs."""
from __future__ import annotations

from .event_queries import all_events, events_of_types, latest_event
from .exception_logging import log_recovered_exception
from app.config.env import env_str as _env_str

from datetime import datetime, timedelta, timezone
from app.caching.bounded_cache import bounded_lru_cache
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
import tempfile
import threading
from typing import Any, Callable, ContextManager, TypedDict

from app.persistence.blob_store import default_blob_store
from app.persistence.contracts import BlobStore
from app.persistence.database import PostgresDatabase, default_database
from app.security.tenant_context import RequestTenant
from app.persistence.unit_of_work import unit_of_work
from app.assistant_tools.repo_adapter import _github_repository_from_remote
from app.capabilities import default_capability_registry

from .acceptance import evaluate_acceptance
from .coding_quality_repository import PostgresCodingQualityRepository
from .active_objective import RoutingEnvironment, make_active_objective
from .evidence import (
    EvidenceCompilationError,
    compile_task_authority,
    evaluate_evidence_set,
    task_requires_workspace_mutation,
    validate_required_evidence_capabilities,
)
from .profiles import get_agent_profile, resolve_profile_capabilities
from .budget import AgentBudgetError, AgentBudgetManager, apply_default_run_limits
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
    RunChangeSet,
    WorkspaceSpec,
)
from app.observability.agent_logging import configure_agent_debug_logging, log_agent_activity
from .pi_runtime import PiAgentRuntime
from .repository import AgentLeaseConflict, PostgresAgentRunRepository
from .review_orchestration_core import consume_terminal_reviewer_in_repository
from .run_locks import RunLockRegistry
from .semantic_task_parser import (
    classify_semantic_task_safely,
    default_semantic_task_parser,
)
from .turn_plan import TurnPlan, compile_turn_plan, derive_effective_objective
from .workspace import WorkspaceAuthority
from .run_change_set import baseline_identity, patch_structure, run_change_set_from_artifact
from .workspace_promotion import WorkspacePromotionError, promote_change_set
from .workspace_dependencies import prepare_project_dependencies
from app.prompts import prompt_template


ACCEPTANCE_RETRY_PROMPT_TEMPLATE = prompt_template(
    'agent_runtime.service_core.acceptance_retry_prompt', "1",
    (
        'Omnix acceptance did not pass ({joined}). Continue the same task; do not stop yet. '
        'Re-read the original user objective before making any repair: acceptance repair is not '
        'permission to change scope. Inspect the most recent failed or missing validation, '
        'correct the requested implementation or the relevant validation command as needed, and '
        'rerun the smallest task-relevant test/lint/typecheck until it exits successfully. For '
        'web UI work, the workspace command starts at the repository root, so use `npm --prefix '
        'src/apps/web run build` or `npm --prefix src/apps/web run test -- <focused-test>`; do '
        'not use Set-Location or shell directory changes. UI Playwright validation must select '
        'exactly one test by relative spec path and source line; do not run a whole spec, suite, '
        'or grep filter. Do not substitute an unrelated passing test, unrelated diff, or '
        'pre-existing workspace change for completion. This is automatic acceptance repair '
        'attempt {attempt}.'
    ),
)



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


class _LeaseBoundRunRepository:
    """Bind worker state changes in a job to the run's current lease owner."""

    def __init__(self, repository, *, worker_id: str, lease_token: str) -> None:
        self._repository = repository
        self._worker_id = worker_id
        self._lease_token = lease_token

    def update_state(self, run_id: str, **kwargs):
        kwargs["worker_id"] = self._worker_id
        kwargs["lease_token"] = self._lease_token
        return self._repository.update_state(run_id, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._repository, name)


def _acceptance_retry_limit() -> int:
    raw = str(_env_str("OMNIX_AGENT_ACCEPTANCE_RETRY_LIMIT", "2") or "2").strip()
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
    raw = str(_env_str("OMNIX_AGENT_PROGRESS_IDLE_TIMEOUT_SECONDS", "120") or "120").strip()
    try:
        return max(60, min(int(raw), 86_400))
    except ValueError:
        return 120


def _stalled_recovery_limit() -> int:
    raw = str(_env_str("OMNIX_AGENT_STALLED_RECOVERY_LIMIT", "2") or "2").strip()
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
        ACCEPTANCE_RETRY_PROMPT_TEMPLATE.format(joined=joined, attempt=attempt)
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
    context = RequestTenant()
    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        context=None,
        job_store=None,
        pi_path: str | None = None,
        worker_id: str | None = None,
        blob_store: BlobStore | None = None,
        unit_of_work_fn: Callable[..., Any] | None = None,
        repository_factory: Callable[..., Any] | None = None,
        quality_repository_factory: Callable[..., Any] | None = None,
        workspace_authority_factory: Callable[..., Any] | None = None,
        semantic_task_parser: Callable[..., Any] | None = None,
        terminal_reviewer_consumer: Callable[..., Any] | None = None,
    ) -> None:
        configure_agent_debug_logging()
        self.database = database or default_database()
        self.context = context
        self.job_store = job_store
        self.unit_of_work = unit_of_work_fn or unit_of_work
        self._lease_tokens: dict[str, str] = {}
        self._lease_token_lock = threading.Lock()
        self.repository_factory = repository_factory or (
            lambda connection, tenant: PostgresAgentRunRepository(
                connection,
                tenant,
                lease_token_provider=self._lease_token_for,
            )
        )
        self.quality_repository_factory = (
            quality_repository_factory or PostgresCodingQualityRepository
        )
        self.workspace_authority_factory = workspace_authority_factory or WorkspaceAuthority
        self.semantic_task_parser = semantic_task_parser or default_semantic_task_parser
        self.terminal_reviewer_consumer = (
            terminal_reviewer_consumer or consume_terminal_reviewer_in_repository
        )
        self.worker_id = worker_id or f"agent-worker:{os.getpid()}"
        self.blob_store = blob_store or default_blob_store()
        self.runtime = PiAgentRuntime(
            pi_path=pi_path or _env_str("OMNIX_PI_PATH", "pi"),
            event_sink=self._persist_runtime_event,
            run_token_issuer=self._issue_run_token,
        )
        self.budgets = AgentBudgetManager(self.database, context=self.context)
        self._run_locks = RunLockRegistry()
        self._supervisor_lock = threading.Lock()
        self._supervisor_started = False
        self._supervisor_stop = threading.Event()
        self._supervisor_thread: threading.Thread | None = None

    def _issue_run_token(self, spec: AgentRunSpec) -> str:
        """Token the Pi process uses for the broker and model gateway (WP-4.6)."""
        from app.security.run_tokens import capabilities_digest, issue_run_token

        return issue_run_token(
            run_id=spec.run_id,
            workspace_id=self.context.workspace_id,
            owner=self.worker_id,
            caps_digest=capabilities_digest(spec.capabilities, spec.external_capabilities),
        )

    def _run_lock(self, run_id: str) -> ContextManager[None]:
        return self._run_locks.hold(run_id)

    def _remember_lease(self, lease) -> None:
        with self._lease_token_lock:
            self._lease_tokens[lease.run_id] = lease.lease_token

    def _lease_token_for(self, run_id: str) -> str | None:
        with self._lease_token_lock:
            return self._lease_tokens.get(run_id)

    def _runtime_owns_run(self, run_id: str) -> bool:
        status = getattr(getattr(self, "runtime", None), "get_status", None)
        if not callable(status):
            return False
        try:
            return status(run_id) is not None
        except Exception as exc:
            log_recovered_exception("local runtime ownership lookup", exc, level="DEBUG")
            return False

    def start_supervisor(self) -> None:
        """Start supervision through the composed worker startup lifecycle."""
        with self._supervisor_lock:
            if self._supervisor_started:
                return
            self._supervisor_stop.clear()
            thread = threading.Thread(
                target=self._supervisor_loop,
                name="omnix-agent-supervisor",
                daemon=True,
            )
            self._supervisor_thread = thread
            self._supervisor_started = True
            thread.start()

    def stop_supervisor(self) -> None:
        self._supervisor_stop.set()
        with self._supervisor_lock:
            thread = self._supervisor_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=6.0)
        with self._supervisor_lock:
            self._supervisor_thread = None
            self._supervisor_started = False

    def _close_terminal_runtime(self, run_id: str) -> None:
        """Stop a local runtime as soon as durable state becomes terminal."""

        runtime = getattr(self, "runtime", None)
        lease_lock = getattr(self, "_lease_token_lock", None)
        lease_tokens = getattr(self, "_lease_tokens", None)
        if lease_lock is not None and lease_tokens is not None:
            with lease_lock:
                lease_tokens.pop(run_id, None)
        close_run = getattr(runtime, "close_run", None)
        if not callable(close_run):
            return
        try:
            close_run(run_id)
        except Exception as exc:
            log_agent_activity(
                "service.runtime_terminal_cleanup_failed",
                category="service",
                level="error",
                run_id=run_id,
                fields={"worker_id": self.worker_id},
                error=exc,
                include_traceback=True,
            )

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

        spec = apply_default_run_limits(self._prepare_start_spec(spec))

        log_agent_activity(
            "service.start.requested",
            category="service",
            run_id=spec.run_id,
            fields={
                "profile": spec.profile,
                "task": spec.task,
                "objective": spec.objective,
                "provider_id": spec.model.provider_id,
                "model_id": spec.model.model_id,
                "capabilities": list(spec.capabilities),
                "has_reference_context": bool(reference_context),
                "reference_image_count": len(reference_images or []),
            },
        )
        try:
            self._validate_run_spec_authority(spec)
            self._validate_evidence_authority(spec)
        except Exception as exc:
            log_agent_activity(
                "service.start.validation_failed",
                category="service",
                level="error",
                run_id=spec.run_id,
                fields={"profile": spec.profile},
                error=exc,
                include_traceback=True,
            )
            raise
        try:
            issued = self._prepare_workspace(self._bind_github_repository_authority(spec))
        except Exception as exc:
            log_agent_activity(
                "service.start.workspace_failed",
                category="service",
                level="error",
                run_id=spec.run_id,
                fields={"profile": spec.profile},
                error=exc,
                include_traceback=True,
            )
            raise
        log_agent_activity(
            "service.start.workspace_prepared",
            category="service",
            run_id=issued.run_id,
            fields={"workspace": issued.workspace.model_dump(mode="json") if issued.workspace else None},
        )
        try:
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
                snapshot = self._persist_starting_run(repository, issued)
                work.commit()
        except Exception as exc:
            log_agent_activity(
                "service.start.persistence_failed",
                category="service",
                level="error",
                run_id=issued.run_id,
                fields={"workspace": issued.workspace.model_dump(mode="json") if issued.workspace else None},
                error=exc,
                include_traceback=True,
            )
            raise
        log_agent_activity(
            "service.start.persisted",
            category="service",
            run_id=issued.run_id,
            fields={"status": snapshot.status, "revision": snapshot.revision},
        )
        if reference_context or reference_images:
            return self._launch_runtime(
                issued,
                snapshot,
                reference_context=reference_context,
                **({"reference_images": reference_images} if reference_images else {}),
            )
        return self._launch_runtime(issued, snapshot)

    def _prepare_start_spec(self, spec: AgentRunSpec) -> AgentRunSpec:
        """Apply process-specific policy before a run becomes durable."""
        return spec

    def submit_start(
        self,
        spec: AgentRunSpec,
        *,
        job_store,
        reference_session_id: str | None = None,
        reference_message_id: str | None = None,
        reference_message_ids: list[str] | None = None,
        task_graph_run_id: str | None = None,
        task_graph_node_ids: list[str] | None = None,
    ) -> AgentRunSnapshot:
        """Persist a queued run and ask the durable worker to prepare it."""
        from .jobs import create_agent_workspace_prepare_request, enqueue_agent_job

        issued = apply_default_run_limits(self._prepare_start_spec(spec))
        self._validate_run_spec_authority(issued)
        self._validate_evidence_authority(issued)
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            snapshot = repository.create_run(issued)
            work.commit()
        try:
            enqueue_agent_job(
                job_store,
                create_agent_workspace_prepare_request(
                    issued.run_id,
                    reference_session_id=reference_session_id,
                    reference_message_id=reference_message_id,
                    reference_message_ids=reference_message_ids,
                    task_graph_run_id=task_graph_run_id,
                    task_graph_node_ids=task_graph_node_ids,
                ),
                idempotency_key=f"run:{issued.run_id}:workspace-prepare",
            )
        except Exception as exc:
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
                current = repository.get_run(issued.run_id)
                if current is not None and current.status == "queued":
                    repository.update_state(
                        issued.run_id,
                        expected_revision=current.revision,
                        status="failed",
                        desired_state="cancelled",
                        last_error=f"agent_start_enqueue_failed:{type(exc).__name__}: {exc}"[:2000],
                    )
                work.commit()
            raise
        return snapshot

    def prepare_workspace_job(
        self,
        run_id: str,
        *,
        job_store,
        reference_session_id: str | None = None,
        reference_message_id: str | None = None,
        reference_message_ids: list[str] | None = None,
        task_graph_run_id: str | None = None,
        task_graph_node_ids: list[str] | None = None,
    ) -> AgentRunSnapshot:
        """Prepare a queued run's workspace in a durable worker process."""
        from .jobs import create_agent_run_start_request, enqueue_agent_job

        snapshot = self.get(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        if snapshot.status in {"completed", "failed", "cancelled"}:
            return snapshot
        prepared = self._prepare_workspace(
            self._bind_github_repository_authority(snapshot.spec)
        )
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            current = repository.get_run(run_id)
            if current is None:
                raise KeyError(run_id)
            if current.status in {"completed", "failed", "cancelled"}:
                work.rollback()
                return current
            if current.spec != prepared:
                current = repository.update_spec(
                    run_id,
                    expected_revision=current.revision,
                    spec=prepared,
                )
            self._capture_workspace_baseline(repository, prepared)
            work.commit()
        enqueue_agent_job(
            job_store,
            create_agent_run_start_request(
                run_id,
                reference_session_id=reference_session_id,
                reference_message_id=reference_message_id,
                reference_message_ids=reference_message_ids,
                task_graph_run_id=task_graph_run_id,
                task_graph_node_ids=task_graph_node_ids,
            ),
            idempotency_key=f"run:{run_id}:start",
        )
        return current

    def start_prepared_run(
        self,
        run_id: str,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
    ) -> AgentRunSnapshot:
        """Acquire run ownership and start Pi after workspace preparation."""
        snapshot = self.get(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        if snapshot.status in {"completed", "failed", "cancelled"}:
            return snapshot
        if self._runtime_owns_run(run_id):
            return snapshot
        self._validate_run_spec_authority(snapshot.spec)
        self._validate_evidence_authority(snapshot.spec)
        if (
            snapshot.spec.workspace is not None
            and snapshot.spec.workspace.repository
            and snapshot.spec.workspace.isolation_policy == "supervised_worktree"
            and not snapshot.spec.workspace.worktree
        ):
            raise RuntimeError("agent workspace preparation has not completed")
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            current = repository.get_run(run_id)
            if current is None:
                raise KeyError(run_id)
            if current.status in {"completed", "failed", "cancelled"}:
                work.rollback()
                return current
            lease = repository.acquire_lease(run_id, worker_id=self.worker_id, ttl_seconds=90)
            self._remember_lease(lease)
            starting = repository.update_state(
                run_id,
                expected_revision=current.revision,
                status="starting",
                worker_id=self.worker_id,
                lease_token=lease.lease_token,
            )
            work.commit()
        return self._launch_runtime(
            current.spec,
            starting,
            reference_context=reference_context,
            **({"reference_images": reference_images} if reference_images else {}),
        )

    def start_child(self, parent_run_id: str, request) -> AgentRunSnapshot:
        child_spec, _ = self._create_child_start(parent_run_id, request)
        prepared = self._prepare_workspace(
            self._bind_github_repository_authority(child_spec)
        )
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            current = repository.get_run(child_spec.run_id)
            if current is None:
                raise KeyError(child_spec.run_id)
            if current.spec != prepared:
                repository.update_spec(
                    child_spec.run_id,
                    expected_revision=current.revision,
                    spec=prepared,
                )
            snapshot = self._persist_starting_run(repository, prepared)
            work.commit()
        return self._launch_runtime(prepared, snapshot)

    def submit_child_start(self, parent_run_id: str, request, *, job_store) -> AgentRunSnapshot:
        """Reserve a child under its parent lock, then defer workspace work."""
        from .jobs import create_agent_workspace_prepare_request, enqueue_agent_job

        child_spec, snapshot = self._create_child_start(parent_run_id, request)
        try:
            enqueue_agent_job(
                job_store,
                create_agent_workspace_prepare_request(child_spec.run_id),
                idempotency_key=f"run:{child_spec.run_id}:workspace-prepare",
            )
        except Exception as exc:
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
                current = repository.get_run(child_spec.run_id)
                if current is not None and current.status == "queued":
                    repository.update_state(
                        child_spec.run_id,
                        expected_revision=current.revision,
                        status="failed",
                        desired_state="cancelled",
                        last_error=f"agent_child_enqueue_failed:{type(exc).__name__}: {exc}"[:2000],
                    )
                work.commit()
            raise
        return snapshot

    def _enqueue_promote_job(self, run_id: str, *, trigger_id: str) -> bool:
        if self.job_store is None:
            return False
        from .jobs import create_agent_promote_request, enqueue_agent_job

        enqueue_agent_job(
            self.job_store,
            create_agent_promote_request(run_id, trigger_id=trigger_id),
            idempotency_key=f"run:{run_id}:promote:{trigger_id}",
        )
        return True

    def process_promote_job(self, run_id: str) -> AgentRunSnapshot:
        """Run acceptance, diff capture and promotion in a durable job."""
        current = self.get(run_id)
        if current is None:
            raise KeyError(run_id)
        if current.status in {"completed", "failed", "cancelled"}:
            return current
        action = None
        with self.unit_of_work(self.database) as work:
            raw_repository = self.repository_factory(work.connection, self.context)
            current = raw_repository.get_run(run_id)
            if current is None:
                raise KeyError(run_id)
            if current.status in {"completed", "failed", "cancelled"}:
                work.rollback()
                return current
            lease = raw_repository.get_active_lease(run_id)
            if lease is None:
                lease = raw_repository.acquire_lease(
                    run_id,
                    worker_id=self.worker_id,
                    ttl_seconds=90,
                )
                self._remember_lease(lease)
            repository = _LeaseBoundRunRepository(
                raw_repository,
                worker_id=lease.worker_id,
                lease_token=lease.lease_token,
            )
            children_terminal, _ = self._children_terminal_state(repository, run_id)
            if not children_terminal:
                work.rollback()
                raise RuntimeError("agent promotion is waiting for child runs to finish")
            advance_quality = getattr(self, "_advance_quality_on_settle", None)
            if callable(advance_quality):
                action = advance_quality(repository, current)
            else:
                self._finalize_acceptance(repository, current)
            work.commit()
        execute_action = getattr(self, "_execute_quality_action", None)
        if action and callable(execute_action):
            execute_action(action)
        dispatch_pending = getattr(self, "_dispatch_pending_quality_commands", None)
        if callable(dispatch_pending):
            dispatch_pending(run_id, include_parent=True)
        latest = self.get(run_id)
        if latest is None:
            raise KeyError(run_id)
        if latest.status in {"completed", "failed", "cancelled"}:
            self._close_terminal_runtime(run_id)
        return latest

    def _create_child_start(self, parent_run_id: str, request):
        from .subagents import derive_child_spec

        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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
            self._reserve_child_start(repository, parent, child_spec)
            snapshot = repository.create_run(child_spec)
            # The grant row references the child run, so it follows create_run.
            self._record_child_grant(repository, parent, child_spec)
            work.commit()
        return child_spec, snapshot

    def _reserve_child_start(self, repository, parent, child_spec: AgentRunSpec) -> None:
        from .subagents import reserve_child_budget

        reserve_child_budget(
            parent,
            repository.list_children(parent.run_id),
            child_spec,
            parent_usage=repository.get_usage(parent.run_id),
        )

    def _record_child_grant(self, repository, parent, child_spec: AgentRunSpec) -> None:
        return None

    def _persist_starting_run(
        self,
        repository: PostgresAgentRunRepository,
        issued: AgentRunSpec,
    ) -> AgentRunSnapshot:
        log_agent_activity(
            "service.start.persisting_run",
            category="service",
            run_id=issued.run_id,
            fields={"worker_id": self.worker_id},
        )
        snapshot = repository.create_run(issued)
        self._capture_workspace_baseline(repository, issued)
        lease = repository.acquire_lease(issued.run_id, worker_id=self.worker_id, ttl_seconds=90)
        self._remember_lease(lease)
        started = repository.update_state(
            issued.run_id,
            expected_revision=snapshot.revision,
            status="starting",
            worker_id=self.worker_id,
            lease_token=lease.lease_token,
        )
        log_agent_activity(
            "service.start.run_persisted",
            category="service",
            run_id=issued.run_id,
            fields={"status": started.status, "revision": started.revision},
        )
        return started

    def _launch_runtime(
        self,
        issued: AgentRunSpec,
        snapshot: AgentRunSnapshot,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
    ) -> AgentRunSnapshot:
        try:
            log_agent_activity(
                "service.runtime.launch_requested",
                category="service",
                run_id=issued.run_id,
                fields={"status": snapshot.status, "revision": snapshot.revision},
            )
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
            log_agent_activity(
                "service.runtime.launch_failed",
                category="service",
                level="error",
                run_id=issued.run_id,
                fields={"status_before_launch": snapshot.status},
                error=exc,
                include_traceback=True,
            )
            self.runtime.close_run(issued.run_id)
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
                current = repository.get_run(issued.run_id)
                if current is not None:
                    repository.update_state(
                        issued.run_id,
                        expected_revision=current.revision,
                        status="failed",
                        desired_state="cancelled",
                        last_error=f"{type(exc).__name__}: {exc}"[:2000],
                    )
                self._maybe_finalize_parent_in_repository(repository, issued.run_id)
                work.commit()
            raise
        result = self.get(issued.run_id) or snapshot
        log_agent_activity(
            "service.runtime.launch_completed",
            category="service",
            run_id=issued.run_id,
            fields={"status": result.status, "revision": result.revision},
        )
        return result

    def get(self, run_id: str) -> AgentRunSnapshot | None:
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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

        log_agent_activity(
            "service.command.requested",
            category="service",
            run_id=command.run_id,
            fields={
                "command_id": command.command_id,
                "command_type": command.command_type,
                "payload": command.payload,
            },
        )
        if command.command_type == "steer":
            try:
                current = self.get(command.run_id)
                if current is None:
                    raise KeyError(command.run_id)
                steering = self._compile_steering(
                    current,
                    command,
                    reference_context=reference_context,
                    turn_plan=turn_plan,
                )
            except Exception as exc:
                log_agent_activity(
                    "service.command.steering_failed",
                    category="service",
                    level="error",
                    run_id=command.run_id,
                    fields={"command_id": command.command_id},
                    error=exc,
                    include_traceback=True,
                )
                raise
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
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
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
        locally_hosted = self._runtime_owns_run(command.run_id)
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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
                log_agent_activity(
                    "service.command.terminal_short_circuit",
                    category="service",
                    run_id=command.run_id,
                    fields={
                        "command_id": stored.command_id,
                        "command_type": stored.command_type,
                        "status": current.status,
                    },
                )
                return current
            if status == "consumed":
                work.commit()
                log_agent_activity(
                    "service.command.already_consumed",
                    category="service",
                    run_id=command.run_id,
                    fields={"command_id": stored.command_id, "status": status},
                )
                return current
            if not locally_hosted:
                work.commit()
                return current
            if not repository.claim_command(command.run_id, stored.command_id):
                work.commit()
                return current
            work.commit()

        try:
            # Runtime callbacks persist status changes from the Pi reader
            # thread. Keep command-side desired-state changes and the
            # corresponding runtime transition in the same critical section
            # so a callback cannot advance the durable revision between our
            # read and optimistic update.
            with self._run_lock(stored.run_id):
                current = self._apply_claimed_command(
                    stored,
                    reference_context=reference_context,
                    **({"reference_images": reference_images} if reference_images else {}),
                )
        except Exception as exc:
            log_agent_activity(
                "service.command.failed",
                category="service",
                level="error",
                run_id=stored.run_id,
                fields={
                    "command_id": stored.command_id,
                    "command_type": stored.command_type,
                },
                error=exc,
                include_traceback=True,
            )
            self._mark_command_failed(stored, exc)
            raise
        else:
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
                repository.complete_command(stored.run_id, stored.command_id)
                work.commit()

        if stored.command_type == "cancel":
            self._cancel_descendants(stored.run_id)
        if current.status in {"completed", "failed", "cancelled"}:
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
                self._maybe_finalize_parent_in_repository(repository, stored.run_id)
                work.commit()
        result = self.get(stored.run_id) or current
        log_agent_activity(
            "service.command.completed",
            category="service",
            run_id=stored.run_id,
            fields={
                "command_id": stored.command_id,
                "command_type": stored.command_type,
                "status": result.status,
                "desired_state": result.desired_state,
                "revision": result.revision,
            },
        )
        return result

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
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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
                self.semantic_task_parser(
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
        if self.job_store is not None:
            return self._submit_superseding_revision(
                current,
                command,
                revision,
                replacement_spec,
            )
        self._validate_run_spec_authority(replacement_spec)
        self._validate_evidence_authority(replacement_spec)
        issued = self._prepare_workspace(
            self._bind_github_repository_authority(replacement_spec)
        )

        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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

    def _submit_superseding_revision(
        self,
        current: AgentRunSnapshot,
        command: AgentRunCommand,
        revision: TaskRevision,
        replacement_spec: AgentRunSpec,
    ) -> AgentRunSnapshot:
        """Persist the replacement and hand workspace/runtime work to jobs."""
        from .jobs import create_agent_workspace_prepare_request, enqueue_agent_job

        issued = apply_default_run_limits(self._prepare_start_spec(replacement_spec))
        self._validate_run_spec_authority(issued)
        self._validate_evidence_authority(issued)
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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
            existing_id = str(locked[0]) if locked[0] else None
            if existing_id:
                existing = repository.get_run(existing_id)
                if existing is None:
                    raise RuntimeError("superseding run link points to missing run")
                work.rollback()
                return existing
            stored, status = repository.enqueue_command_with_status(command)
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
            if status != "consumed" and repository.claim_command(
                current.run_id,
                stored.command_id,
            ):
                repository.complete_command(current.run_id, stored.command_id)
            snapshot = repository.create_run(issued)
            repository.mark_superseded(current.run_id, issued.run_id)
            work.commit()
        enqueue_agent_job(
            self.job_store,
            create_agent_workspace_prepare_request(issued.run_id),
            idempotency_key=f"run:{issued.run_id}:workspace-prepare",
        )
        return snapshot

    def _mark_command_failed(self, command: AgentRunCommand, error: Exception) -> None:
        """Make transport/runtime command failures visible and terminal.

        A command updates desired state before it reaches the local runtime. If
        the runtime process has already exited, leaving that intermediate state
        durable makes runs appear permanently paused or cancellation-pending.
        """
        log_agent_activity(
            "service.command.failure_state_persisting",
            category="service",
            level="error",
            run_id=command.run_id,
            fields={"command_id": command.command_id, "command_type": command.command_type},
            error=error,
        )
        self.runtime.close_run(command.run_id)
        terminal_status = "cancelled" if command.command_type == "cancel" else "failed"
        desired_state = "cancelled"
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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
                resolution: dict[str, Any] = {"source": "agent_run_command"}
                if stored.payload.get("issued_by"):
                    resolution["decided_by"] = str(stored.payload["issued_by"])
                repository.resolve_approval(
                    stored.run_id,
                    approval_id,
                    approved=stored.command_type == "approve",
                    resolution_payload=resolution,
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
                worker_id=self.worker_id,
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
        if active is None and stored.command_type == "resume":
            # A durable resume is executable work, not merely desired-state
            # bookkeeping. Rehydrate a missing local Pi session before
            # consuming the command so `resume_requested` cannot become a
            # permanent state with no runtime behind it.
            self.runtime.start(current.spec)
            active = self.runtime.get_status(stored.run_id)
            if active is None:
                raise RuntimeError("resume_runtime_rehydration_failed")
            runtime_command = stored.model_copy(update={
                "payload": {
                    **stored.payload,
                    "runtime_rehydrated": True,
                }
            })
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
            except Exception as exc:
                if stored.command_type != "steer" or current.status != "waiting_for_input":
                    raise
                log_recovered_exception("clarification runtime rehydration", exc)
                # A stale in-memory session can still have a snapshot even
                # though its child process exited. Recreate it once and retry
                # the user's answer while the durable run remains waiting.
                self.runtime.close_run(stored.run_id)
                self.runtime.start(current.spec)
                send_runtime_command()
            runtime_status = self.runtime.get_status(stored.run_id)
            if runtime_status is not None:
                with self.unit_of_work(self.database) as work:
                    repository = self.repository_factory(work.connection, self.context)
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
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
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
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            rows = repository.list_events(run_id, after_sequence=after_sequence)
            work.rollback()
            return rows

    def approvals(self, run_id: str, *, state: str | None = None):
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            rows = repository.list_approvals(run_id, state=state)
            work.rollback()
            return rows

    def artifacts(self, run_id: str) -> list[AgentArtifact]:
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            rows = repository.list_artifacts(run_id)
            work.rollback()
            return rows

    def task_revisions(self, run_id: str) -> list[TaskRevision]:
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            rows = repository.list_task_revisions(run_id)
            work.rollback()
            return rows

    def evidence_receipts(self, run_id: str):
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            rows = repository.list_evidence_receipts(run_id)
            work.rollback()
            return rows

    def evidence_set(self, run_id: str):
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
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
                desired_state="cancelled",
                last_error="acceptance_failed:child_run_failed",
            )
        else:
            queued = self._enqueue_promote_job(
                parent.run_id,
                trigger_id=f"children-terminal:{child_run_id}",
            )
            if not queued:
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
        change_set = self._capture_diff(
            repository,
            current.spec,
            task_revision_id=revision_id,
        )
        run_events = all_events(repository, current.run_id)
        all_artifacts = repository.list_artifacts(current.run_id)
        all_receipts = repository.list_evidence_receipts(current.run_id)
        events = self._events_for_revision(run_events, task_revision)
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
        promotion: dict[str, object] | None = None
        if passed:
            try:
                promotion = self._promote_accepted_workspace(
                    repository,
                    current,
                    task_revision_id=revision_id,
                    workspace_state_id=(
                        change_set.candidate_workspace_state_id
                        if change_set is not None
                        else None
                    ),
                )
            except WorkspacePromotionError as exc:
                failures.append(f"workspace_promotion_failed:{exc}")
                passed = False

        retry_count = _acceptance_retry_count(run_events, revision_id)
        runtime_available = (
            self._runtime_owns_run(current.run_id)
            or repository.get_active_lease(current.run_id) is not None
        )
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
                    "workspace_promotion": promotion,
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
            repository.enqueue_command_with_status(
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
            return

        if passed and promotion is not None:
            repository.append_event(
                AgentEvent(
                    run_id=current.run_id,
                    event_type="run.completed",
                    payload={"source": "omnix", "workspace_promotion": promotion},
                )
            )
        repository.update_state(
            current.run_id,
            expected_revision=latest.revision,
            status="completed" if passed else "failed",
            desired_state=None if passed else "cancelled",
            worker_id=self.worker_id,
            last_error=None if passed else "acceptance_failed:" + ",".join(failures),
        )

    def _persist_runtime_event(self, event: AgentEvent) -> None:
        log_agent_activity(
            "service.runtime_event.persisting",
            category="service",
            run_id=event.run_id,
            fields={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "sequence": event.sequence,
                "payload": event.payload,
            },
        )
        promote_trigger: str | None = None
        with self._run_lock(event.run_id):
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
                current = repository.get_run(event.run_id)
                if current is None:
                    log_agent_activity(
                        "service.runtime_event.ignored_unknown_run",
                        category="service",
                        level="warning",
                        run_id=event.run_id,
                        fields={"event_type": event.event_type},
                    )
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
                    log_agent_activity(
                        "service.runtime_event.terminal_run_no_transition",
                        category="service",
                        run_id=event.run_id,
                        fields={"event_type": event.event_type, "status": current.status},
                    )
                    work.commit()
                    self._close_terminal_runtime(event.run_id)
                    return
                terminal_runtime = False
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
                            repository.update_state(
                                event.run_id,
                                expected_revision=current.revision,
                                status="waiting_for_children",
                                worker_id=self.worker_id,
                            )
                            promote_trigger = event.event_id
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
                        desired_state="cancelled",
                        worker_id=self.worker_id,
                        last_error=str(event.payload.get("error") or "Pi runtime failed")[:2000],
                    )
                self._maybe_finalize_parent_in_repository(repository, event.run_id)
                latest = repository.get_run(event.run_id)
                terminal_runtime = latest is not None and latest.status in {
                    "completed",
                    "failed",
                    "cancelled",
                }
                work.commit()
                if terminal_runtime:
                    self._close_terminal_runtime(event.run_id)
        if promote_trigger is not None:
            try:
                queued = self._enqueue_promote_job(
                    event.run_id,
                    trigger_id=promote_trigger,
                )
                if not queued:
                    terminal_after_fallback = False
                    with self.unit_of_work(self.database) as work:
                        repository = self.repository_factory(work.connection, self.context)
                        current = repository.get_run(event.run_id)
                        if current is not None and current.status == "waiting_for_children":
                            self._finalize_acceptance(repository, current)
                            latest = repository.get_run(event.run_id)
                            terminal_after_fallback = latest is not None and latest.status in {
                                "completed",
                                "failed",
                                "cancelled",
                            }
                        work.commit()
                    if terminal_after_fallback:
                        self._close_terminal_runtime(event.run_id)
            except Exception as exc:
                log_agent_activity(
                    "service.acceptance.enqueue_failed",
                    category="quality",
                    level="error",
                    run_id=event.run_id,
                    fields={"trigger_id": promote_trigger},
                    error=exc,
                    include_traceback=True,
                )

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
        baseline = self.workspace_authority_factory(root).provenance_snapshot()
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

    def _quarantine_isolated_workspace_contamination(
        self,
        repository: PostgresAgentRunRepository,
        spec: AgentRunSpec,
        *,
        authority: WorkspaceAuthority | None = None,
    ) -> list[dict[str, str]]:
        workspace = spec.workspace
        if workspace is None or not workspace.worktree:
            return []
        worktree_root = Path(workspace.worktree).expanduser().resolve()
        repository_root = Path(workspace.repository or workspace.root).expanduser().resolve()
        if worktree_root == repository_root:
            return []
        workspace_authority = authority or self.workspace_authority_factory(worktree_root)
        quarantined = workspace_authority.quarantine_generated_windows_cache_contamination()
        if not quarantined:
            return []
        repository.append_event(
            AgentEvent(
                run_id=spec.run_id,
                event_type="run.status",
                payload={
                    "status": "workspace_contamination_quarantined",
                    "artifacts": quarantined,
                },
            )
        )
        log_agent_activity(
            "service.workspace.contamination_quarantined",
            category="quality",
            level="warning",
            run_id=spec.run_id,
            fields={"workspace": str(worktree_root), "artifacts": quarantined},
        )
        return quarantined

    def _capture_diff(
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
            authority = self.workspace_authority_factory(root)
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
                str(path).replace(chr(92), "/")
                for path in (
                    baseline_metadata.get("dirty_paths")
                    if isinstance(baseline_metadata.get("dirty_paths"), list)
                    else []
                )
            ]
            dirty_digests = {
                str(key).replace(chr(92), "/"): str(value)
                for key, value in (
                    baseline_metadata.get("dirty_digests")
                    if isinstance(baseline_metadata.get("dirty_digests"), dict)
                    else {}
                ).items()
            }
            head = str(baseline_metadata.get("head") or authority.git_head())
            baseline_id = str(baseline_metadata.get("baseline_id") or baseline_identity(head, dirty_paths, dirty_digests))
            self._quarantine_isolated_workspace_contamination(
                repository,
                spec,
                authority=authority,
            )
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
            except Exception as exc:
                log_recovered_exception("workspace artifact content upload", exc)
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

    def recover_orphaned_runs(self) -> list[str]:
        """Re-acquire expired/unowned non-terminal runs and resume from workspace truth."""
        recovered: list[str] = []
        with self.unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT run.run_id
                  FROM omnix_agent_runs AS run
                  LEFT JOIN omnix_agent_worker_leases AS lease
                    ON lease.workspace_id = run.workspace_id AND lease.run_id = run.run_id
                 WHERE run.workspace_id = %s
                   AND run.status IN ('starting','running','resume_requested')
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
                with self.unit_of_work(self.database) as work:
                    repository = self.repository_factory(work.connection, self.context)
                    lease = repository.acquire_lease(run_id, worker_id=self.worker_id, ttl_seconds=90)
                    self._remember_lease(lease)
                    repository.reset_processing_commands(run_id)
                    current = repository.get_run(run_id)
                    queued_cancel = next(
                        (
                            item
                            for item in repository.list_pending_commands(run_id)
                            if item.command_type == "cancel"
                        ),
                        None,
                    )
                    if current is not None and queued_cancel is not None:
                        # The dead owner never delivered this cancel. Honour it
                        # instead of restarting a runtime only to stop it.
                        if repository.claim_command(run_id, queued_cancel.command_id):
                            current = repository.update_state(
                                run_id,
                                expected_revision=current.revision,
                                status="cancelled",
                                desired_state="cancelled",
                                worker_id=self.worker_id,
                                lease_token=lease.lease_token,
                            )
                            repository.complete_command(run_id, queued_cancel.command_id)
                            self._maybe_finalize_parent_in_repository(repository, run_id)
                        work.commit()
                        self._cancel_descendants(run_id)
                        recovered.append(run_id)
                        continue
                    if current is not None:
                        repository.update_state(
                            run_id,
                            expected_revision=current.revision,
                            status="starting",
                            worker_id=self.worker_id,
                            lease_token=lease.lease_token,
                        )
                    work.commit()
                self.runtime.start(snapshot.spec)
                with self.unit_of_work(self.database) as work:
                    repository = self.repository_factory(work.connection, self.context)
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
        with self.unit_of_work(self.database) as work:
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
            repository = self.repository_factory(work.connection, self.context)
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

    def _supervisor_loop(self) -> None:
        while not self._supervisor_stop.is_set():
            try:
                self._supervise_once()
            except Exception as exc:
                log_agent_activity(
                    "service.supervisor.loop_failed",
                    category="recovery",
                    level="error",
                    fields={"worker_id": self.worker_id},
                    error=exc,
                    include_traceback=True,
                )
            self._supervisor_stop.wait(5.0)

    def _supervise_once(self) -> None:
        with self.unit_of_work(self.database) as work:
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
            except AgentBudgetError as exc:
                log_agent_activity(
                    "service.supervisor.budget_exceeded",
                    category="recovery",
                    level="error",
                    run_id=run_id,
                    fields={"worker_id": self.worker_id},
                    error=exc,
                )
                self.runtime.close_run(run_id)
                self._cancel_descendants(run_id)
                continue
            try:
                self.heartbeat(run_id, ttl_seconds=90)
            except AgentLeaseConflict as exc:
                # This worker no longer owns the lease. Continuing its local Pi
                # process would violate execution authority, so stop supervising
                # this run immediately and let the current owner proceed.
                log_agent_activity(
                    "service.supervisor.lease_lost",
                    category="recovery",
                    level="warning",
                    run_id=run_id,
                    fields={"worker_id": self.worker_id},
                    error=exc,
                )
                self.runtime.close_run(run_id)
                continue
            except Exception as exc:
                # A transient database failure is not proof that ownership was
                # lost. Keep normal progress supervision active and retry lease
                # renewal on the next supervisor cycle.
                log_agent_activity(
                    "service.supervisor.heartbeat_failed",
                    category="recovery",
                    level="error",
                    run_id=run_id,
                    fields={"worker_id": self.worker_id},
                    error=exc,
                    include_traceback=True,
                )
            try:
                self._supervise_stalled_run(run_id)
            except Exception as exc:
                # A transient supervisor/database failure must not take down
                # supervision for every other active run. Lease expiry and
                # orphan recovery remain the fallback safety net.
                log_agent_activity(
                    "service.supervisor.stall_check_failed",
                    category="recovery",
                    level="error",
                    run_id=run_id,
                    fields={"worker_id": self.worker_id},
                    error=exc,
                    include_traceback=True,
                )
                continue
            try:
                self._deliver_pending_commands(run_id)
            except Exception as exc:
                log_agent_activity(
                    "service.supervisor.command_delivery_failed",
                    category="recovery",
                    level="error",
                    run_id=run_id,
                    fields={"worker_id": self.worker_id},
                    error=exc,
                    include_traceback=True,
                )

        with self.unit_of_work(self.database) as work:
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
            with self.unit_of_work(self.database) as work:
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

    def _deliver_pending_commands(self, run_id: str) -> None:
        if not self._runtime_owns_run(run_id):
            return
        claimed = []
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            for command in repository.list_pending_commands(run_id, limit=20):
                if repository.claim_command(run_id, command.command_id):
                    claimed.append(command)
            work.commit()
        for command in claimed:
            try:
                with self._run_lock(run_id):
                    self._apply_claimed_command(command)
                with self.unit_of_work(self.database) as work:
                    repository = self.repository_factory(work.connection, self.context)
                    repository.complete_command(run_id, command.command_id)
                    work.commit()
            except Exception as exc:
                log_agent_activity(
                    "service.command.owner_delivery_failed",
                    category="service",
                    level="error",
                    run_id=run_id,
                    fields={"command_id": command.command_id, "command_type": command.command_type},
                    error=exc,
                    include_traceback=True,
                )
                self._mark_command_failed(command, exc)

    def _supervise_stalled_run(self, run_id: str) -> None:
        """Supervise a leased run whose durable activity became quiet.

        Worker heartbeats only establish that the supervisor thread is alive.
        Coding runs keep a Pi-owned loop and receive an advisory unless the
        local runtime session is conclusively absent. Other profiles retain
        bounded legacy recovery while they migrate to runtime-owned lifecycles.
        """
        log_agent_activity(
            "service.recovery.check_started",
            category="recovery",
            run_id=run_id,
            fields={
                "idle_timeout_seconds": _progress_idle_timeout_seconds(),
                "recovery_limit": _stalled_recovery_limit(),
            },
        )
        now = datetime.now(timezone.utc)
        terminalize = False
        current: AgentRunSnapshot | None = None
        attempt = 0
        progress_event: AgentEvent | None = None

        with self._run_lock(run_id):
            with self.unit_of_work(self.database) as work:
                repository = self.repository_factory(work.connection, self.context)
                current = repository.get_run(run_id)
                if (
                    current is None
                    or current.status not in {"running", "resume_requested"}
                    or current.desired_state != "running"
                ):
                    log_agent_activity(
                        "service.recovery.not_eligible",
                        category="recovery",
                        run_id=run_id,
                        fields={
                            "found": current is not None,
                            "status": current.status if current is not None else None,
                            "desired_state": current.desired_state if current is not None else None,
                        },
                    )
                    work.rollback()
                    return
                progress_event = repository.latest_progress_event(run_id)
                progress_at = (
                    progress_event.created_at
                    if progress_event is not None
                    else current.updated_at or current.created_at
                )
                if progress_at is None:
                    log_agent_activity(
                        "service.recovery.no_checkpoint",
                        category="recovery",
                        level="warning",
                        run_id=run_id,
                        fields={"status": current.status, "revision": current.revision},
                    )
                    work.rollback()
                    return
                if progress_at.tzinfo is None:
                    progress_at = progress_at.replace(tzinfo=timezone.utc)
                if now - progress_at < timedelta(seconds=_progress_idle_timeout_seconds()):
                    log_agent_activity(
                        "service.recovery.progress_current",
                        category="recovery",
                        level="debug",
                        run_id=run_id,
                        fields={
                            "last_progress_event": progress_event.event_type if progress_event else None,
                            "last_progress_sequence": progress_event.sequence if progress_event else None,
                            "last_progress_at": progress_at.isoformat(),
                            "idle_seconds": round((now - progress_at).total_seconds(), 3),
                        },
                    )
                    work.rollback()
                    return

                get_runtime_status = getattr(self.runtime, "get_status", None)
                runtime_confirmed_missing = (
                    callable(get_runtime_status) and get_runtime_status(run_id) is None
                )
                if current.spec.profile == "coding" and not runtime_confirmed_missing:
                    # Pi owns the complete coding loop. A quiet model/tool turn
                    # is not proof that its process died, and restarting it
                    # destroys the context it needs to finish efficiently.
                    # Persist one advisory warning per progress checkpoint and
                    # leave interruption/recovery to an explicit user command.
                    prior_warning = None
                    if callable(getattr(repository, "list_events", None)):
                        prior_warning = latest_event(repository, run_id, "run.stall_suspected")
                    progress_sequence = progress_event.sequence if progress_event else None
                    warned_sequence = (
                        prior_warning.payload.get("last_progress_sequence")
                        if prior_warning is not None
                        else None
                    )
                    if prior_warning is None or warned_sequence != progress_sequence:
                        reason = (
                            f"no durable agent activity for {int((now - progress_at).total_seconds())}s"
                            f" after {progress_event.event_type if progress_event else 'run start'}"
                        )
                        repository.append_event(AgentEvent(
                            run_id=run_id,
                            event_type="run.stall_suspected",
                            payload={
                                "reason": reason,
                                "idle_seconds": round((now - progress_at).total_seconds(), 3),
                                "last_progress_event": progress_event.event_type if progress_event else None,
                                "last_progress_sequence": progress_sequence,
                                "automatic_recovery": False,
                            },
                        ))
                        log_agent_activity(
                            "service.recovery.stall_advisory_recorded",
                            category="recovery",
                            level="warning",
                            run_id=run_id,
                            fields={"reason": reason, "last_progress_sequence": progress_sequence},
                        )
                        work.commit()
                    else:
                        work.rollback()
                    return

                attempt = repository.count_events(run_id, "run.recovery_requested") + 1
                quality_stage = None
                if callable(getattr(repository, "list_events", None)):
                    stage_event = latest_event(repository, run_id, "quality.stage")
                    if stage_event is not None:
                        quality_stage = str(stage_event.payload.get("stage") or "").strip() or None
                reason = (
                    f"no durable agent progress for {int((now - progress_at).total_seconds())}s"
                    f" after {progress_event.event_type if progress_event else 'run start'}"
                )
                log_agent_activity(
                    "service.recovery.stall_detected",
                    category="recovery",
                    level="warning",
                    run_id=run_id,
                    fields={
                        "attempt": attempt,
                        "reason": reason,
                        "last_progress_event": progress_event.event_type if progress_event else None,
                        "last_progress_sequence": progress_event.sequence if progress_event else None,
                        "last_progress_at": progress_at.isoformat(),
                        "idle_seconds": round((now - progress_at).total_seconds(), 3),
                        "quality_stage": quality_stage,
                    },
                )
                if attempt > _stalled_recovery_limit():
                    terminalize = True
                    log_agent_activity(
                        "service.recovery.exhausted",
                        category="recovery",
                        level="error",
                        run_id=run_id,
                        fields={
                            "attempt": attempt,
                            "recovery_limit": _stalled_recovery_limit(),
                            "reason": reason,
                            "quality_stage": quality_stage,
                        },
                    )
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
                    log_agent_activity(
                        "service.recovery.requested",
                        category="recovery",
                        level="warning",
                        run_id=run_id,
                        fields={
                            "attempt": attempt,
                            "recovery_limit": _stalled_recovery_limit(),
                            "reason": reason,
                            "quality_stage": quality_stage,
                        },
                    )
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
                log_agent_activity(
                    "service.recovery.terminalizing",
                    category="recovery",
                    level="error",
                    run_id=run_id,
                    fields={"attempt": attempt},
                )
                self.runtime.close_run(run_id)
                self._cancel_descendants(run_id)
                return

            assert current is not None
            log_agent_activity(
                "service.recovery.dispatching_resume",
                category="recovery",
                level="warning",
                run_id=run_id,
                fields={"attempt": attempt, "quality_stage": quality_stage},
            )
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
                with self.unit_of_work(self.database) as work:
                    repository = self.repository_factory(work.connection, self.context)
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
                log_agent_activity(
                    "service.recovery.resume_dispatched",
                    category="recovery",
                    level="warning",
                    run_id=run_id,
                    fields={
                        "attempt": attempt,
                        "reused_active_session": reuse_active_session,
                    },
                )
            except Exception as exc:
                log_agent_activity(
                    "service.recovery.resume_failed",
                    category="recovery",
                    level="error",
                    run_id=run_id,
                    fields={
                        "attempt": attempt,
                        "reused_active_session": reuse_active_session,
                    },
                    error=exc,
                    include_traceback=True,
                )
                self.runtime.close_run(run_id)
                with self.unit_of_work(self.database) as work:
                    repository = self.repository_factory(work.connection, self.context)
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
        log_agent_activity(
            "service.heartbeat.requested",
            category="recovery",
            run_id=run_id,
            fields={"ttl_seconds": ttl_seconds, "worker_id": self.worker_id},
        )
        with self.unit_of_work(self.database) as work:
            repository = self.repository_factory(work.connection, self.context)
            lease = repository.renew_lease(
                run_id,
                worker_id=self.worker_id,
                ttl_seconds=ttl_seconds,
            )
            self._remember_lease(lease)
            work.commit()
        log_agent_activity(
            "service.heartbeat.renewed",
            category="recovery",
            run_id=run_id,
            fields={
                "worker_id": self.worker_id,
                "lease_revision": lease.revision,
                "lease_expires_at": lease.lease_expires_at.isoformat(),
            },
        )

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

    def _promote_accepted_workspace(
        self,
        repository: PostgresAgentRunRepository,
        current: AgentRunSnapshot,
        *,
        task_revision_id: str | None,
        workspace_state_id: str | None,
    ) -> dict[str, object] | None:
        """Adopt an accepted isolated coding candidate into its main checkout."""

        spec = current.spec
        workspace = spec.workspace
        if (
            spec.profile != "coding"
            or "diff" not in spec.expected_artifacts
            or workspace is None
            or not workspace.repository
            or not workspace.worktree
        ):
            return None
        source = Path(workspace.worktree).expanduser().resolve()
        target = Path(workspace.repository).expanduser().resolve()
        if source == target:
            return {"status": "already_in_main", "paths": []}

        for event in reversed(events_of_types(repository, current.run_id, {"run.completed"})):
            marker = event.payload.get("workspace_promotion")
            if isinstance(marker, dict) and marker.get("change_set_id"):
                return dict(marker)

        change_set = None
        for artifact in reversed(repository.list_artifacts(current.run_id)):
            change_set = run_change_set_from_artifact(artifact)
            if change_set is not None:
                break
        if change_set is None:
            raise WorkspacePromotionError("accepted run change set is unavailable")
        if change_set.task_revision_id != task_revision_id:
            raise WorkspacePromotionError("accepted run change set revision is stale")
        if change_set.candidate_workspace_state_id != workspace_state_id:
            raise WorkspacePromotionError("accepted run change set workspace state is stale")
        try:
            patch = self.blob_store.read_bytes(
                change_set.patch_storage_ref,
                expected_checksum=change_set.patch_checksum,
            ).decode("utf-8")
        except Exception as exc:
            raise WorkspacePromotionError(f"accepted run change set blob is unavailable: {exc}") from exc
        result = promote_change_set(
            source_root=source,
            target_root=target,
            change_set=change_set,
            patch=patch,
        )
        return {
            "change_set_id": change_set.change_set_id,
            "status": result.status,
            "source_workspace": str(source),
            "target_workspace": str(target),
            "target_head_sha": result.target_head_sha,
            "paths": list(result.paths),
        }

    def _prepare_workspace(self, spec: AgentRunSpec) -> AgentRunSpec:
        workspace = spec.workspace
        if workspace is None:
            # Read-only research and other non-workspace profiles retain an
            # explicit None workspace. PiRpcSession supplies an ephemeral cwd
            # without turning it into repository authority.
            return spec
        if not workspace.repository or workspace.worktree:
            return spec
        root = Path(
            _env_str(
                "OMNIX_AGENT_WORKTREE_ROOT",
                str(Path(tempfile.gettempdir()) / "omnix-agent-worktrees"),
            )
        ).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        target = root / spec.run_id
        authority = self.workspace_authority_factory.create_worktree(
            workspace.repository,
            target,
            base_ref=workspace.base_ref,
        )
        try:
            prepare_project_dependencies(repository=workspace.repository, worktree=authority.root)
        except Exception:
            try:
                self.workspace_authority_factory.remove_worktree(workspace.repository, authority.root)
            except Exception as exc:
                # Preserve the actionable dependency error; the supervisor can
                # reconcile an orphaned temporary worktree on its next pass.
                log_recovered_exception("temporary worktree cleanup", exc)
                pass
            raise
        issued_workspace = workspace.model_copy(update={"root": str(authority.root), "worktree": str(authority.root)})
        return spec.model_copy(update={"workspace": issued_workspace})


@bounded_lru_cache(max_entries=1, ttl_seconds=3600.0)
def default_agent_run_service() -> AgentRunService:
    return AgentRunService()
