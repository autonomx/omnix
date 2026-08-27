"""Durable orchestration service for generalized agent runs."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import os
from pathlib import Path
import tempfile
import threading

from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .acceptance import evaluate_acceptance
from .contracts import AgentArtifact, AgentEvent, AgentRunCommand, AgentRunSnapshot, AgentRunSpec
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
    ) -> None:
        self.database = database or default_database()
        self.context = bootstrap_local_tenant(self.database)
        self.worker_id = worker_id or f"agent-worker:{os.getpid()}"
        self.runtime = PiAgentRuntime(pi_path=pi_path or os.environ.get("OMNIX_PI_PATH", "pi"), event_sink=self._persist_runtime_event)
        self._lock = threading.RLock()

    def start(self, spec: AgentRunSpec) -> AgentRunSnapshot:
        issued = self._prepare_workspace(spec)
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = repository.create_run(issued)
            repository.acquire_lease(issued.run_id, worker_id=self.worker_id, ttl_seconds=60)
            snapshot = repository.update_state(
                issued.run_id,
                expected_revision=snapshot.revision,
                status="starting",
                worker_id=self.worker_id,
            )
            work.commit()
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
                work.commit()
            raise
        return self.get(issued.run_id) or snapshot

    def start_child(self, parent_run_id: str, request) -> AgentRunSnapshot:
        from .subagents import derive_child_spec, reserve_child_budget

        parent = self.get(parent_run_id)
        if parent is None:
            raise KeyError(parent_run_id)
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            existing = repository.list_children(parent_run_id)
            work.rollback()
        child_spec = derive_child_spec(parent, request)
        reserve_child_budget(parent, existing, child_spec)
        return self.start(child_spec)

    def get(self, run_id: str) -> AgentRunSnapshot | None:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = repository.get_run(run_id)
            work.rollback()
            return snapshot

    def command(self, command: AgentRunCommand) -> AgentRunSnapshot:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            stored = repository.enqueue_command(command)
            current = repository.get_run(command.run_id)
            if current is None:
                raise KeyError(command.run_id)
            desired = current.desired_state
            status = current.status
            if stored.command_type in {"approve", "reject"}:
                approval_id = str(stored.payload.get("approval_id") or "")
                if not approval_id:
                    raise ValueError("approval_id is required")
                repository.resolve_approval(
                    command.run_id, approval_id,
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
                command.run_id,
                expected_revision=current.revision,
                status=status,
                desired_state=desired,
            )
            work.commit()
        active = self.runtime.get_status(command.run_id)
        if active is not None:
            self.runtime.command(stored)
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                current = repository.get_run(command.run_id)
                if current is not None:
                    runtime_status = self.runtime.get_status(command.run_id)
                    if runtime_status is not None:
                        current = repository.update_state(
                            command.run_id,
                            expected_revision=current.revision,
                            status=runtime_status.status,
                            desired_state=runtime_status.desired_state,
                        )
                work.commit()
        elif stored.command_type == "cancel":
            with unit_of_work(self.database) as work:
                repository = PostgresAgentRunRepository(work.connection, self.context)
                persisted = repository.get_run(command.run_id)
                if persisted is not None and persisted.status != "cancelled":
                    current = repository.update_state(
                        command.run_id,
                        expected_revision=persisted.revision,
                        status="cancelled",
                        desired_state="cancelled",
                    )
                work.commit()
        if stored.command_type == "cancel":
            self._cancel_descendants(command.run_id)
        return self.get(command.run_id) or current

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

    def artifacts(self, run_id: str) -> list[AgentArtifact]:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            rows = repository.list_artifacts(run_id)
            work.rollback()
            return rows

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
                elif event.event_type == "run.completed":
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
                refreshed = repository.get_run(event.run_id)
                if refreshed is not None and refreshed.spec.parent_run_id and refreshed.status in {"completed", "failed", "cancelled"}:
                    parent = repository.get_run(refreshed.spec.parent_run_id)
                    if parent is not None and parent.status == "waiting_for_children":
                        terminal, failed = self._children_terminal_state(repository, parent.run_id)
                        if terminal:
                            if failed:
                                repository.update_state(
                                    parent.run_id,
                                    expected_revision=parent.revision,
                                    status="failed",
                                    last_error="acceptance_failed:child_run_failed",
                                )
                            else:
                                self._finalize_acceptance(repository, parent)
                work.commit()

    def _capture_diff(self, repository: PostgresAgentRunRepository, spec: AgentRunSpec) -> None:
        if spec.workspace is None:
            return
        root = spec.workspace.worktree or spec.workspace.root
        try:
            diff = WorkspaceAuthority(root).git_diff()
        except Exception:
            return
        digest = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        repository.add_artifact(
            AgentArtifact(
                run_id=spec.run_id,
                kind="diff",
                name="workspace.diff",
                checksum=digest,
                metadata={"preview": diff[:200_000], "truncated": len(diff) > 200_000},
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
                    repository.acquire_lease(run_id, worker_id=self.worker_id, ttl_seconds=60)
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
                self.runtime.command(
                    AgentRunCommand(
                        run_id=run_id,
                        command_type="steer",
                        payload={"message": "This run was recovered after a worker restart. Reinspect the current workspace before continuing."},
                    )
                )
                recovered.append(run_id)
            except Exception:
                continue
        return recovered

    def heartbeat(self, run_id: str, *, ttl_seconds: int = 60) -> None:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            repository.acquire_lease(run_id, worker_id=self.worker_id, ttl_seconds=ttl_seconds)
            repository.append_event(
                AgentEvent(run_id=run_id, event_type="worker.heartbeat", payload={"worker_id": self.worker_id})
            )
            work.commit()

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
