"""Durable orchestration service for generalized agent runs."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import os
import subprocess
from pathlib import Path
import tempfile
import threading

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work
from app.assistant_tools.repo_adapter import _github_repository_from_remote

from .acceptance import evaluate_acceptance
from .budget import AgentBudgetError, AgentBudgetManager
from .contracts import AgentArtifact, AgentEvent, AgentRunCommand, AgentRunSnapshot, AgentRunSpec, ResourceScope
from .pi_runtime import PiAgentRuntime
from .repository import PostgresAgentRunRepository
from .workspace import WorkspaceAuthority


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
        self._ensure_supervisor()
        issued = self._prepare_workspace(self._bind_github_repository_authority(spec))
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = self._persist_starting_run(repository, issued)
            work.commit()
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
    ) -> AgentRunSnapshot:
        try:
            self.runtime.start(issued)
        except Exception as exc:
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
        self._ensure_supervisor()
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            stored, status = repository.enqueue_command_with_status(command)
            current = repository.get_run(command.run_id)
            if current is None:
                raise KeyError(command.run_id)
            if status == "consumed" or not repository.claim_command(command.run_id, stored.command_id):
                work.commit()
                return current
            work.commit()

        try:
            current = self._apply_claimed_command(stored)
        except Exception:
            # Leave "processing" durable. A future owner recovery resets abandoned
            # processing commands after the worker lease expires.
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

    def _apply_claimed_command(self, stored: AgentRunCommand) -> AgentRunSnapshot:
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
                repository.resolve_approval(
                    stored.run_id,
                    approval_id,
                    approved=stored.command_type == "approve",
                    resolution_payload={"source": "agent_run_command"},
                )
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
            work.commit()

        active = self.runtime.get_status(stored.run_id)
        if active is not None:
            self.runtime.command(stored)
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
        repository.append_event(
            AgentEvent(run_id=current.run_id, event_type="acceptance.started", payload={"source": "omnix"})
        )
        self._capture_diff(repository, current.spec)
        events = repository.list_events(current.run_id, after_sequence=0, limit=5000)
        artifacts = repository.list_artifacts(current.run_id)
        result = evaluate_acceptance(current.spec, events=events, artifacts=artifacts)
        children_terminal, child_failed = self._children_terminal_state(repository, current.run_id)
        failures = list(result.failures)
        if not children_terminal:
            failures.append("children_not_terminal")
        if child_failed:
            failures.append("child_run_failed")
        passed = result.passed and not failures
        repository.append_event(
            AgentEvent(
                run_id=current.run_id,
                event_type="acceptance.completed",
                payload={**result.model_dump(mode="json"), "passed": passed, "failures": failures},
            )
        )
        latest = repository.get_run(current.run_id) or current
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
                repository.append_event(event)
                if event.event_type == "run.started" and current.status != "running":
                    current = repository.update_state(
                        event.run_id,
                        expected_revision=current.revision,
                        status="running",
                        worker_id=self.worker_id,
                    )
                elif event.event_type in {"run.settled", "run.completed"}:
                    if current.status not in {
                        "waiting_for_approval",
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

    def _capture_diff(self, repository: PostgresAgentRunRepository, spec: AgentRunSpec) -> None:
        if spec.workspace is None:
            return
        root = spec.workspace.worktree or spec.workspace.root
        try:
            diff = WorkspaceAuthority(root).git_diff()
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
        repository.add_artifact(
            AgentArtifact(
                run_id=spec.run_id,
                kind="diff",
                name="workspace.diff",
                storage_ref=str(blob["storage_key"]),
                checksum=str(blob["checksum_sha256"]),
                metadata={
                    "storage_provider": str(blob["storage_provider"]),
                    "byte_size": int(blob["byte_size"]),
                    "preview": diff[:preview_limit],
                    "truncated": len(diff) > preview_limit,
                },
            )
        )

    def recover_orphaned_runs(self) -> list[str]:
        """Re-acquire expired/unowned non-terminal runs and resume from workspace truth."""
        recovered: list[str] = []
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """
                SELECT run_id
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
                self.runtime.command(
                    AgentRunCommand(
                        run_id=run_id,
                        command_type="steer",
                        payload={"message": "This run was recovered after a worker restart. Reinspect the current workspace before continuing."},
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
                continue
            try:
                self.heartbeat(run_id, ttl_seconds=90)
            except Exception:
                continue

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
        return spec.model_copy(update={"resource_scopes": scopes})

    @staticmethod
    def _prepare_workspace(spec: AgentRunSpec) -> AgentRunSpec:
        workspace = spec.workspace
        if workspace is None:
            root = Path(os.environ.get(
                "OMNIX_AGENT_WORKTREE_ROOT",
                str(Path(tempfile.gettempdir()) / "omnix-agent-worktrees"),
            )).expanduser().resolve()
            target = root / spec.run_id
            target.mkdir(parents=True, exist_ok=True)
            from .contracts import WorkspaceSpec
            return spec.model_copy(update={"workspace": WorkspaceSpec(
                root=str(target), worktree=str(target), allowed_paths=[]
            )})
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
        issued_workspace = workspace.model_copy(update={"root": str(authority.root), "worktree": str(authority.root)})
        return spec.model_copy(update={"workspace": issued_workspace})


@lru_cache(maxsize=1)
def default_agent_run_service() -> AgentRunService:
    return AgentRunService()
