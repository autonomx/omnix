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
            if stored.command_type == "pause":
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
        return self.get(command.run_id) or current

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
                    repository.append_event(
                        AgentEvent(run_id=event.run_id, event_type="acceptance.started", payload={"source": "omnix"})
                    )
                    self._capture_diff(repository, current.spec)
                    events = repository.list_events(event.run_id, after_sequence=0, limit=5000)
                    artifacts = repository.list_artifacts(event.run_id)
                    result = evaluate_acceptance(current.spec, events=events, artifacts=artifacts)
                    repository.append_event(
                        AgentEvent(
                            run_id=event.run_id,
                            event_type="acceptance.completed",
                            payload=result.model_dump(mode="json"),
                        )
                    )
                    current = repository.get_run(event.run_id) or current
                    repository.update_state(
                        event.run_id,
                        expected_revision=current.revision,
                        status="completed" if result.passed else "failed",
                        worker_id=self.worker_id,
                        last_error=None if result.passed else "acceptance_failed:" + ",".join(result.failures),
                    )
                elif event.event_type == "run.failed":
                    repository.update_state(
                        event.run_id,
                        expected_revision=current.revision,
                        status="failed",
                        worker_id=self.worker_id,
                        last_error=str(event.payload.get("error") or "Pi runtime failed")[:2000],
                    )
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
        if workspace is None or not workspace.repository or workspace.worktree:
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
