"""PostgreSQL repository for generalized agent runs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import uuid
from typing import Any

from app.persistence.outbox_repository import PostgresOutboxRepository
from app.persistence.tenant import TenantContext

from .contracts import (
    AgentApproval,
    AgentArtifact,
    AgentEvent,
    AgentRunCommand,
    AgentRunSnapshot,
    AgentRunSpec,
    WorkerLease,
)


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class AgentRunConcurrencyError(RuntimeError):
    pass


class AgentLeaseConflict(RuntimeError):
    pass


class PostgresAgentRunRepository:
    def __init__(self, connection: Any, context: TenantContext) -> None:
        self.connection = connection
        self.context = context
        self.outbox = PostgresOutboxRepository(connection)

    def create_run(self, spec: AgentRunSpec) -> AgentRunSnapshot:
        row = self.connection.execute(
            """
            INSERT INTO omnix_agent_runs (
                workspace_id, run_id, session_id, parent_run_id, spec,
                status, desired_state
            ) VALUES (%s, %s, %s, %s, %s::jsonb, 'queued', 'running')
            ON CONFLICT (workspace_id, run_id) DO NOTHING
            RETURNING run_id
            """,
            (
                self.context.workspace_id,
                spec.run_id,
                spec.session_id,
                spec.parent_run_id,
                _json(spec),
            ),
        ).fetchone()
        if row is None:
            existing = self.get_run(spec.run_id)
            if existing is None:
                raise AgentRunConcurrencyError("agent run create conflict")
            if existing.spec != spec:
                raise AgentRunConcurrencyError("run_id already exists with a different spec")
            return existing
        snapshot = self.get_run(spec.run_id)
        assert snapshot is not None
        self.append_event(AgentEvent(run_id=spec.run_id, event_type="run.created", payload={"profile": spec.profile, "runtime": spec.runtime}))
        return snapshot

    def get_run(self, run_id: str) -> AgentRunSnapshot | None:
        row = self.connection.execute(
            """
            SELECT run_id, spec, status, desired_state, revision, worker_id,
                   started_at, completed_at, last_error, created_at, updated_at
              FROM omnix_agent_runs
             WHERE workspace_id = %s AND run_id = %s
            """,
            (self.context.workspace_id, run_id),
        ).fetchone()
        if row is None:
            return None
        return AgentRunSnapshot(
            run_id=str(row[0]),
            spec=AgentRunSpec.model_validate(row[1]),
            status=str(row[2]),
            desired_state=str(row[3]),
            revision=int(row[4]),
            worker_id=str(row[5]) if row[5] else None,
            started_at=row[6],
            completed_at=row[7],
            last_error=str(row[8]) if row[8] else None,
            created_at=row[9],
            updated_at=row[10],
        )

    def list_children(self, parent_run_id: str) -> list[AgentRunSnapshot]:
        rows = self.connection.execute(
            """
            SELECT run_id
              FROM omnix_agent_runs
             WHERE workspace_id = %s AND parent_run_id = %s
             ORDER BY created_at, run_id
            """,
            (self.context.workspace_id, parent_run_id),
        ).fetchall()
        result: list[AgentRunSnapshot] = []
        for row in rows:
            snapshot = self.get_run(str(row[0]))
            if snapshot is not None:
                result.append(snapshot)
        return result

    def update_state(
        self,
        run_id: str,
        *,
        expected_revision: int,
        status: str | None = None,
        desired_state: str | None = None,
        worker_id: str | None = None,
        last_error: str | None = None,
    ) -> AgentRunSnapshot:
        current = self.get_run(run_id)
        if current is None:
            raise KeyError(run_id)
        next_status = status or current.status
        next_desired = desired_state or current.desired_state
        started = current.started_at
        completed = current.completed_at
        now = datetime.now(timezone.utc)
        if next_status in {"starting", "running"} and started is None:
            started = now
        if next_status in {"completed", "failed", "cancelled"} and completed is None:
            completed = now
        row = self.connection.execute(
            """
            UPDATE omnix_agent_runs
               SET status = %s, desired_state = %s, worker_id = %s,
                   last_error = %s, started_at = %s, completed_at = %s,
                   revision = revision + 1, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND revision = %s
            RETURNING revision
            """,
            (
                next_status,
                next_desired,
                worker_id if worker_id is not None else current.worker_id,
                last_error,
                started,
                completed,
                self.context.workspace_id,
                run_id,
                expected_revision,
            ),
        ).fetchone()
        if row is None:
            raise AgentRunConcurrencyError("agent run revision mismatch")
        updated = self.get_run(run_id)
        assert updated is not None
        self.append_event(
            AgentEvent(
                run_id=run_id,
                event_type="run.status",
                payload={"status": updated.status, "desired_state": updated.desired_state, "revision": updated.revision},
            )
        )
        return updated

    def append_event(self, event: AgentEvent) -> AgentEvent:
        # Lock the run row so MAX(sequence)+1 remains deterministic under concurrent writers.
        locked = self.connection.execute(
            "SELECT revision FROM omnix_agent_runs WHERE workspace_id = %s AND run_id = %s FOR UPDATE",
            (self.context.workspace_id, event.run_id),
        ).fetchone()
        if locked is None:
            raise KeyError(event.run_id)
        row = self.connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1
              FROM omnix_agent_run_events
             WHERE workspace_id = %s AND run_id = %s
            """,
            (self.context.workspace_id, event.run_id),
        ).fetchone()
        sequence = int(row[0])
        stored = event.model_copy(update={"sequence": sequence})
        self.connection.execute(
            """
            INSERT INTO omnix_agent_run_events (
                workspace_id, run_id, sequence, event_id, event_type,
                payload, correlation_id, causation_id, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                self.context.workspace_id,
                stored.run_id,
                sequence,
                stored.event_id,
                stored.event_type,
                _json(stored.payload),
                stored.correlation_id,
                stored.causation_id,
                stored.created_at,
            ),
        )
        self.outbox.append(
            self.context,
            aggregate_type="agent_run",
            aggregate_id=stored.run_id,
            event_type=stored.event_type,
            payload=stored.model_dump(mode="json"),
            ordering_key=f"agent:{stored.run_id}",
            correlation_id=stored.correlation_id,
            causation_id=stored.causation_id,
            event_key=f"agent:{stored.event_id}",
        )
        return stored

    def list_events(self, run_id: str, *, after_sequence: int = 0, limit: int = 500) -> list[AgentEvent]:
        rows = self.connection.execute(
            """
            SELECT event_id, sequence, event_type, payload, correlation_id, causation_id, created_at
              FROM omnix_agent_run_events
             WHERE workspace_id = %s AND run_id = %s AND sequence > %s
             ORDER BY sequence
             LIMIT %s
            """,
            (self.context.workspace_id, run_id, max(0, after_sequence), max(1, min(limit, 5000))),
        ).fetchall()
        return [
            AgentEvent(
                event_id=str(row[0]),
                run_id=run_id,
                sequence=int(row[1]),
                event_type=str(row[2]),
                payload=dict(row[3] or {}),
                correlation_id=str(row[4]) if row[4] else None,
                causation_id=str(row[5]) if row[5] else None,
                created_at=row[6],
            )
            for row in rows
        ]

    def enqueue_command(self, command: AgentRunCommand) -> tuple[AgentRunCommand, str]:
        inserted = self.connection.execute(
            """
            INSERT INTO omnix_agent_run_commands (
                workspace_id, run_id, command_id, command_type, payload,
                idempotency_key, created_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (workspace_id, run_id, idempotency_key) DO NOTHING
            RETURNING command_id
            """,
            (
                self.context.workspace_id,
                command.run_id,
                command.command_id,
                command.command_type,
                _json(command.payload),
                command.idempotency_key,
                command.created_at,
            ),
        ).fetchone()
        row = self.connection.execute(
            """
            SELECT command_id, command_type, payload, idempotency_key, created_at, status
              FROM omnix_agent_run_commands
             WHERE workspace_id = %s AND run_id = %s AND idempotency_key = %s
            """,
            (self.context.workspace_id, command.run_id, command.idempotency_key),
        ).fetchone()
        stored = AgentRunCommand(
            command_id=str(row[0]),
            run_id=command.run_id,
            command_type=str(row[1]),
            payload=dict(row[2] or {}),
            idempotency_key=str(row[3]),
            created_at=row[4],
        )
        if inserted is not None:
            self.append_event(
                AgentEvent(
                    run_id=command.run_id,
                    event_type="steering.received" if stored.command_type == "steer" else "run.status",
                    payload={"command_id": stored.command_id, "command_type": stored.command_type},
                )
            )
        return stored, str(row[5])

    def claim_command(self, run_id: str, command_id: str) -> bool:
        row = self.connection.execute(
            """
            UPDATE omnix_agent_run_commands
               SET status = 'processing'
             WHERE workspace_id = %s AND run_id = %s AND command_id = %s
               AND status = 'pending'
            RETURNING command_id
            """,
            (self.context.workspace_id, run_id, command_id),
        ).fetchone()
        return row is not None

    def complete_command(self, run_id: str, command_id: str) -> None:
        self.connection.execute(
            """
            UPDATE omnix_agent_run_commands
               SET status = 'consumed', consumed_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND command_id = %s
               AND status = 'processing'
            """,
            (self.context.workspace_id, run_id, command_id),
        )

    def reset_processing_commands(self, run_id: str) -> None:
        self.connection.execute(
            """
            UPDATE omnix_agent_run_commands
               SET status = 'pending', consumed_at = NULL
             WHERE workspace_id = %s AND run_id = %s AND status = 'processing'
            """,
            (self.context.workspace_id, run_id),
        )

    def list_pending_commands(self, run_id: str, *, limit: int = 100) -> list[AgentRunCommand]:
        rows = self.connection.execute(
            """
            SELECT command_id, command_type, payload, idempotency_key, created_at
              FROM omnix_agent_run_commands
             WHERE workspace_id = %s AND run_id = %s AND status = 'pending'
             ORDER BY created_at, command_id
             LIMIT %s
            """,
            (self.context.workspace_id, run_id, max(1, min(limit, 1000))),
        ).fetchall()
        return [
            AgentRunCommand(
                command_id=str(row[0]),
                run_id=run_id,
                command_type=str(row[1]),
                payload=dict(row[2] or {}),
                idempotency_key=str(row[3]),
                created_at=row[4],
            )
            for row in rows
        ]

    def add_approval(self, approval: AgentApproval) -> AgentApproval:
        self.connection.execute(
            """
            INSERT INTO omnix_agent_approvals (
                workspace_id, run_id, approval_id, capability_id, state,
                request_payload, resolution_payload, created_at, resolved_at
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (workspace_id, run_id, approval_id) DO NOTHING
            """,
            (
                self.context.workspace_id,
                approval.run_id,
                approval.approval_id,
                approval.capability_id,
                approval.state,
                _json(approval.request_payload),
                _json(approval.resolution_payload),
                approval.created_at,
                approval.resolved_at,
            ),
        )
        self.append_event(AgentEvent(run_id=approval.run_id, event_type="approval.requested", payload={"approval_id": approval.approval_id, "capability_id": approval.capability_id}))
        return approval

    def get_approval(self, run_id: str, approval_id: str) -> AgentApproval | None:
        row = self.connection.execute(
            """
            SELECT capability_id, state, request_payload, resolution_payload,
                   created_at, resolved_at
              FROM omnix_agent_approvals
             WHERE workspace_id = %s AND run_id = %s AND approval_id = %s
            """,
            (self.context.workspace_id, run_id, approval_id),
        ).fetchone()
        if row is None:
            return None
        return AgentApproval(
            approval_id=approval_id, run_id=run_id, capability_id=str(row[0]),
            state=str(row[1]), request_payload=dict(row[2] or {}),
            resolution_payload=dict(row[3] or {}), created_at=row[4], resolved_at=row[5],
        )

    def resolve_approval(
        self, run_id: str, approval_id: str, *, approved: bool,
        resolution_payload: dict[str, Any] | None = None,
    ) -> AgentApproval:
        state = "approved" if approved else "rejected"
        row = self.connection.execute(
            """
            UPDATE omnix_agent_approvals
               SET state = %s, resolution_payload = %s::jsonb, resolved_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND approval_id = %s AND state = 'pending'
            RETURNING capability_id, request_payload, resolution_payload, created_at, resolved_at
            """,
            (state, _json(resolution_payload or {}), self.context.workspace_id, run_id, approval_id),
        ).fetchone()
        if row is None:
            existing = self.get_approval(run_id, approval_id)
            if existing is None:
                raise KeyError(approval_id)
            return existing
        approval = AgentApproval(
            approval_id=approval_id, run_id=run_id, capability_id=str(row[0]), state=state,
            request_payload=dict(row[1] or {}), resolution_payload=dict(row[2] or {}),
            created_at=row[3], resolved_at=row[4],
        )
        self.append_event(AgentEvent(
            run_id=run_id, event_type="approval.resolved",
            payload={"approval_id": approval_id, "state": state, "capability_id": approval.capability_id},
        ))
        return approval

    def add_artifact(self, artifact: AgentArtifact) -> AgentArtifact:
        self.connection.execute(
            """
            INSERT INTO omnix_agent_artifacts (
                workspace_id, run_id, artifact_id, kind, name, storage_ref,
                checksum, metadata, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (workspace_id, run_id, artifact_id) DO NOTHING
            """,
            (
                self.context.workspace_id,
                artifact.run_id,
                artifact.artifact_id,
                artifact.kind,
                artifact.name,
                artifact.storage_ref,
                artifact.checksum,
                _json(artifact.metadata),
                artifact.created_at,
            ),
        )
        self.append_event(AgentEvent(run_id=artifact.run_id, event_type="artifact.created", payload={"artifact_id": artifact.artifact_id, "kind": artifact.kind, "name": artifact.name}))
        return artifact

    def list_artifacts(self, run_id: str) -> list[AgentArtifact]:
        rows = self.connection.execute(
            """
            SELECT artifact_id, kind, name, storage_ref, checksum, metadata, created_at
              FROM omnix_agent_artifacts
             WHERE workspace_id = %s AND run_id = %s
             ORDER BY created_at, artifact_id
            """,
            (self.context.workspace_id, run_id),
        ).fetchall()
        return [
            AgentArtifact(
                artifact_id=str(row[0]),
                run_id=run_id,
                kind=str(row[1]),
                name=str(row[2]),
                storage_ref=str(row[3]) if row[3] else None,
                checksum=str(row[4]) if row[4] else None,
                metadata=dict(row[5] or {}),
                created_at=row[6],
            )
            for row in rows
        ]

    def acquire_lease(self, run_id: str, *, worker_id: str, ttl_seconds: int = 30) -> WorkerLease:
        token = uuid.uuid4().hex
        expires = datetime.now(timezone.utc) + timedelta(seconds=max(5, ttl_seconds))
        row = self.connection.execute(
            """
            INSERT INTO omnix_agent_worker_leases (
                workspace_id, run_id, worker_id, lease_token, lease_expires_at, heartbeat_at
            ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (workspace_id, run_id) DO UPDATE
               SET worker_id = EXCLUDED.worker_id,
                   lease_token = EXCLUDED.lease_token,
                   lease_expires_at = EXCLUDED.lease_expires_at,
                   heartbeat_at = CURRENT_TIMESTAMP,
                   revision = omnix_agent_worker_leases.revision + 1
             WHERE omnix_agent_worker_leases.lease_expires_at <= CURRENT_TIMESTAMP
                OR omnix_agent_worker_leases.worker_id = EXCLUDED.worker_id
            RETURNING worker_id, lease_token, lease_expires_at, heartbeat_at, revision
            """,
            (self.context.workspace_id, run_id, worker_id, token, expires),
        ).fetchone()
        if row is None:
            raise AgentLeaseConflict(f"run {run_id} is leased by another worker")
        return WorkerLease(
            run_id=run_id,
            worker_id=str(row[0]),
            lease_token=str(row[1]),
            lease_expires_at=row[2],
            heartbeat_at=row[3],
            revision=int(row[4]),
        )
