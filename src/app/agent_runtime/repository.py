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
    EvidenceDecision,
    EvidenceReceipt,
    TaskRevision,
    WorkerLease,
)


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return str(value)


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


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
                workspace_id, run_id, session_id, parent_run_id, supersedes_run_id, spec,
                status, desired_state
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'queued', 'running')
            ON CONFLICT (workspace_id, run_id) DO NOTHING
            RETURNING run_id
            """,
            (
                self.context.workspace_id,
                spec.run_id,
                spec.session_id,
                spec.parent_run_id,
                spec.supersedes_run_id,
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
        self.add_task_revision(TaskRevision(
            run_id=spec.run_id,
            sequence=1,
            user_instruction=spec.task,
            effective_objective=spec.objective or spec.task,
            effective_success_criteria=list(spec.success_criteria),
            evidence_decision=EvidenceDecision(
                policy=spec.evidence_policy,
                confidence=1.0,
                reason="compiled_run_spec",
                classifier="deterministic",
            ),
            required_local_capabilities=list(spec.capabilities),
            required_external_capabilities=list(spec.external_capabilities),
            expected_artifacts=list(spec.expected_artifacts),
        ))
        return snapshot

    def get_run(self, run_id: str) -> AgentRunSnapshot | None:
        row = self.connection.execute(
            """
            SELECT run_id, spec, status, desired_state, revision, worker_id,
                   superseded_by_run_id, started_at, completed_at, last_error, created_at, updated_at
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
            superseded_by_run_id=str(row[6]) if row[6] else None,
            started_at=row[7],
            completed_at=row[8],
            last_error=str(row[9]) if row[9] else None,
            created_at=row[10],
            updated_at=row[11],
        )

    def add_task_revision(self, revision: TaskRevision) -> TaskRevision:
        self.connection.execute(
            "SELECT revision FROM omnix_agent_runs WHERE workspace_id = %s AND run_id = %s FOR UPDATE",
            (self.context.workspace_id, revision.run_id),
        ).fetchone()
        inserted = self.connection.execute(
            """
            INSERT INTO omnix_agent_task_revisions (
                workspace_id, run_id, revision_id, sequence, previous_revision_id,
                source_command_id, user_instruction, effective_objective,
                effective_success_criteria, evidence_decision,
                required_local_capabilities, required_external_capabilities,
                expected_artifacts, acceptance_checks, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                %s::jsonb, %s::jsonb, %s
            )
            ON CONFLICT DO NOTHING
            RETURNING revision_id
            """,
            (
                self.context.workspace_id,
                revision.run_id,
                revision.revision_id,
                revision.sequence,
                revision.previous_revision_id,
                revision.source_command_id,
                revision.user_instruction,
                revision.effective_objective,
                _json(revision.effective_success_criteria),
                _json(revision.evidence_decision),
                _json(revision.required_local_capabilities),
                _json(revision.required_external_capabilities),
                _json(revision.expected_artifacts),
                _json(revision.acceptance_checks),
                revision.created_at,
            ),
        )
        row = inserted.fetchone()
        if row is None:
            existing = self.connection.execute(
                """
                SELECT revision_id
                  FROM omnix_agent_task_revisions
                 WHERE workspace_id = %s AND run_id = %s
                   AND (revision_id = %s OR source_command_id = %s)
                 LIMIT 1
                """,
                (
                    self.context.workspace_id,
                    revision.run_id,
                    revision.revision_id,
                    revision.source_command_id,
                ),
            ).fetchone()
            if existing is None:
                raise AgentRunConcurrencyError("task revision sequence conflict")
            rows = self.list_task_revisions(revision.run_id)
            return next(item for item in rows if item.revision_id == str(existing[0]))
        self.append_event(AgentEvent(
            run_id=revision.run_id,
            event_type="task.revised",
            payload={
                "revision_id": revision.revision_id,
                "sequence": revision.sequence,
                "source_command_id": revision.source_command_id,
                "evidence_reason": revision.evidence_decision.reason,
            },
        ))
        return revision

    def list_task_revisions(self, run_id: str) -> list[TaskRevision]:
        rows = self.connection.execute(
            """
            SELECT revision_id, sequence, previous_revision_id, source_command_id,
                   user_instruction, effective_objective, effective_success_criteria,
                   evidence_decision, required_local_capabilities,
                   required_external_capabilities, expected_artifacts,
                   acceptance_checks, created_at
              FROM omnix_agent_task_revisions
             WHERE workspace_id = %s AND run_id = %s
             ORDER BY sequence
            """,
            (self.context.workspace_id, run_id),
        ).fetchall()
        return [
            TaskRevision.model_validate(
                {
                    "revision_id": str(row[0]),
                    "run_id": run_id,
                    "sequence": int(row[1]),
                    "previous_revision_id": str(row[2]) if row[2] else None,
                    "source_command_id": str(row[3]) if row[3] else None,
                    "user_instruction": str(row[4]),
                    "effective_objective": str(row[5]),
                    "effective_success_criteria": list(row[6] or []),
                    "evidence_decision": row[7] or {},
                    "required_local_capabilities": list(row[8] or []),
                    "required_external_capabilities": list(row[9] or []),
                    "expected_artifacts": list(row[10] or []),
                    "acceptance_checks": list(row[11] or []),
                    "created_at": row[12],
                }
            )
            for row in rows
        ]

    def latest_task_revision(self, run_id: str) -> TaskRevision | None:
        rows = self.list_task_revisions(run_id)
        return rows[-1] if rows else None

    def add_evidence_receipt(self, receipt: EvidenceReceipt) -> EvidenceReceipt:
        self.connection.execute(
            """
            INSERT INTO omnix_agent_evidence_receipts (
                workspace_id, run_id, receipt_id, task_revision_id, capability_id,
                source_class, subject, coverage, request_digest, provider, origin,
                source_manifest_id, source_count, executed_at, observed_at,
                freshest_source_at, trust_level, result_digest, metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (workspace_id, run_id, receipt_id) DO NOTHING
            """,
            (
                self.context.workspace_id, receipt.run_id, receipt.receipt_id,
                receipt.task_revision_id, receipt.capability_id, receipt.source_class,
                _json(receipt.subject.model_dump(mode="json") if receipt.subject else None),
                _json([item.model_dump(mode="json") for item in receipt.coverage]),
                receipt.request_digest, receipt.provider, receipt.origin,
                receipt.source_manifest_id, receipt.source_count, receipt.executed_at,
                receipt.observed_at, receipt.freshest_source_at, receipt.trust_level,
                receipt.result_digest, _json(receipt.metadata),
            ),
        )
        self.append_event(AgentEvent(
            run_id=receipt.run_id,
            event_type="evidence.receipt",
            payload={
                "receipt_id": receipt.receipt_id,
                "task_revision_id": receipt.task_revision_id,
                "capability_id": receipt.capability_id,
                "source_class": receipt.source_class,
                "subject": receipt.subject.model_dump(mode="json") if receipt.subject else None,
                "coverage": [item.model_dump(mode="json") for item in receipt.coverage],
                "provider": receipt.provider,
                "observed_at": receipt.observed_at.isoformat(),
                "trust_level": receipt.trust_level,
            },
        ))
        return receipt

    def list_evidence_receipts(self, run_id: str) -> list[EvidenceReceipt]:
        rows = self.connection.execute(
            """
            SELECT receipt_id, task_revision_id, capability_id, source_class,
                   subject, coverage, request_digest, provider, origin, source_manifest_id,
                   source_count, executed_at, observed_at, freshest_source_at,
                   trust_level, result_digest, metadata
              FROM omnix_agent_evidence_receipts
             WHERE workspace_id = %s AND run_id = %s
             ORDER BY observed_at, receipt_id
            """,
            (self.context.workspace_id, run_id),
        ).fetchall()
        return [
            EvidenceReceipt(
                receipt_id=str(row[0]),
                run_id=run_id,
                task_revision_id=str(row[1]) if row[1] else None,
                capability_id=str(row[2]),
                source_class=str(row[3]),
                subject=row[4],
                coverage=list(row[5] or []),
                request_digest=str(row[6]),
                provider=str(row[7]) if row[7] else None,
                origin=str(row[8]) if row[8] else None,
                source_manifest_id=str(row[9]) if row[9] else None,
                source_count=int(row[10] or 0),
                executed_at=row[11],
                observed_at=row[12],
                freshest_source_at=row[13],
                trust_level=str(row[14]),
                result_digest=str(row[15]),
                metadata=dict(row[16] or {}),
            )
            for row in rows
        ]

    def mark_superseded(self, run_id: str, superseded_by_run_id: str) -> AgentRunSnapshot:
        row = self.connection.execute(
            """
            UPDATE omnix_agent_runs
               SET superseded_by_run_id = %s,
                   status = 'cancelled',
                   desired_state = 'cancelled',
                   completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                   last_error = %s,
                   revision = revision + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s
               AND status NOT IN ('completed','failed','cancelled')
            RETURNING revision
            """,
            (
                superseded_by_run_id,
                f"superseded_by:{superseded_by_run_id}",
                self.context.workspace_id,
                run_id,
            ),
        ).fetchone()
        current = self.get_run(run_id)
        if current is None:
            raise KeyError(run_id)
        if row is not None:
            self.append_event(AgentEvent(
                run_id=run_id,
                event_type="run.superseded",
                payload={"superseded_by_run_id": superseded_by_run_id},
            ))
            current = self.get_run(run_id) or current
        return current

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

    def latest_progress_event(self, run_id: str) -> AgentEvent | None:
        """Return the latest durable event that represents agent progress.

        Worker heartbeats and orchestration bookkeeping keep a lease or
        durable state current but do not prove that Pi is advancing. The
        supervisor uses this event-log checkpoint to detect a live worker
        whose runtime has stopped making progress. In particular, approving
        or resuming a stuck run must not move the progress checkpoint forward.
        """
        row = self.connection.execute(
            """
            SELECT event_id, sequence, event_type, payload,
                   correlation_id, causation_id, created_at
              FROM omnix_agent_run_events
             WHERE workspace_id = %s
               AND run_id = %s
               AND event_type NOT IN (
                   'worker.heartbeat',
                   'run.status',
                   'approval.requested',
                   'approval.resolved',
                   'steering.received',
                   'task.revised',
                   'run.recovery_requested',
                   'run.recovery_failed'
               )
             ORDER BY sequence DESC
             LIMIT 1
            """,
            (self.context.workspace_id, run_id),
        ).fetchone()
        if row is None:
            return None
        return AgentEvent(
            event_id=str(row[0]),
            run_id=run_id,
            sequence=int(row[1]),
            event_type=str(row[2]),
            payload=dict(row[3] or {}),
            correlation_id=str(row[4]) if row[4] else None,
            causation_id=str(row[5]) if row[5] else None,
            created_at=row[6],
        )

    def count_events(self, run_id: str, event_type: str) -> int:
        row = self.connection.execute(
            """
            SELECT COUNT(*)
              FROM omnix_agent_run_events
             WHERE workspace_id = %s AND run_id = %s AND event_type = %s
            """,
            (self.context.workspace_id, run_id, event_type),
        ).fetchone()
        return int(row[0] or 0) if row else 0

    def enqueue_command(self, command: AgentRunCommand) -> AgentRunCommand:
        stored, _ = self.enqueue_command_with_status(command)
        return stored

    def enqueue_command_with_status(self, command: AgentRunCommand) -> tuple[AgentRunCommand, str]:
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

    def claim_commands(self, run_id: str, *, limit: int = 20) -> list[AgentRunCommand]:
        """Compatibility batch claim used by repository consumers.

        The orchestration service uses claim_command()/complete_command() so a
        command is not marked consumed until its side effect succeeds. This
        legacy batch API preserves the Phase-3 repository contract for callers
        that explicitly want dequeue-and-consume semantics.
        """
        rows = self.connection.execute(
            """
            WITH claimed AS (
                SELECT command_id
                  FROM omnix_agent_run_commands
                 WHERE workspace_id = %s AND run_id = %s AND status = 'pending'
                 ORDER BY created_at, command_id
                 FOR UPDATE SKIP LOCKED
                 LIMIT %s
            )
            UPDATE omnix_agent_run_commands AS command
               SET status = 'consumed', consumed_at = CURRENT_TIMESTAMP
              FROM claimed
             WHERE command.workspace_id = %s AND command.run_id = %s
               AND command.command_id = claimed.command_id
            RETURNING command.command_id, command.command_type, command.payload,
                      command.idempotency_key, command.created_at
            """,
            (
                self.context.workspace_id,
                run_id,
                max(1, min(limit, 100)),
                self.context.workspace_id,
                run_id,
            ),
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

    def list_approvals(
        self,
        run_id: str,
        *,
        state: str | None = None,
    ) -> list[AgentApproval]:
        if state is None:
            rows = self.connection.execute(
                """
                SELECT approval_id, capability_id, state, request_payload,
                       resolution_payload, created_at, resolved_at
                  FROM omnix_agent_approvals
                 WHERE workspace_id = %s AND run_id = %s
                 ORDER BY created_at, approval_id
                """,
                (self.context.workspace_id, run_id),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT approval_id, capability_id, state, request_payload,
                       resolution_payload, created_at, resolved_at
                  FROM omnix_agent_approvals
                 WHERE workspace_id = %s AND run_id = %s AND state = %s
                 ORDER BY created_at, approval_id
                """,
                (self.context.workspace_id, run_id, state),
            ).fetchall()
        return [
            AgentApproval(
                approval_id=str(row[0]),
                run_id=run_id,
                capability_id=str(row[1]),
                state=str(row[2]),
                request_payload=dict(row[3] or {}),
                resolution_payload=dict(row[4] or {}),
                created_at=row[5],
                resolved_at=row[6],
            )
            for row in rows
        ]

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

    def ensure_capability_execution(
        self,
        run_id: str,
        execution_key: str,
        capability_id: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.connection.execute(
            """
            INSERT INTO omnix_agent_capability_executions (
                workspace_id, run_id, execution_key, capability_id, state, request_payload
            ) VALUES (%s, %s, %s, %s, 'created', %s::jsonb)
            ON CONFLICT (workspace_id, run_id, execution_key) DO NOTHING
            """,
            (
                self.context.workspace_id,
                run_id,
                execution_key,
                capability_id,
                _json(request_payload),
            ),
        )
        row = self.connection.execute(
            """
            SELECT capability_id, state, request_payload, result_payload, error,
                   state_changed, created_at, updated_at
              FROM omnix_agent_capability_executions
             WHERE workspace_id = %s AND run_id = %s AND execution_key = %s
            """,
            (self.context.workspace_id, run_id, execution_key),
        ).fetchone()
        if row is None:
            raise AgentRunConcurrencyError("capability execution disappeared")
        return {
            "capability_id": str(row[0]),
            "state": str(row[1]),
            "request_payload": dict(row[2] or {}),
            "result_payload": dict(row[3] or {}),
            "error": str(row[4]) if row[4] else None,
            "state_changed": bool(row[5]),
            "created_at": row[6],
            "updated_at": row[7],
        }

    def find_capability_approval(
        self,
        run_id: str,
        capability_id: str,
        execution_key: str,
    ) -> AgentApproval | None:
        row = self.connection.execute(
            """
            SELECT approval_id
              FROM omnix_agent_approvals
             WHERE workspace_id = %s AND run_id = %s AND capability_id = %s
               AND request_payload ->> 'execution_key' = %s
             ORDER BY created_at
             LIMIT 1
            """,
            (self.context.workspace_id, run_id, capability_id, execution_key),
        ).fetchone()
        if row is None:
            return None
        return self.get_approval(run_id, str(row[0]))

    def mark_capability_waiting_for_approval(
        self,
        run_id: str,
        execution_key: str,
    ) -> None:
        self.connection.execute(
            """
            UPDATE omnix_agent_capability_executions
               SET state = 'waiting_for_approval', updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND execution_key = %s
               AND state = 'created'
            """,
            (self.context.workspace_id, run_id, execution_key),
        )

    def claim_capability_execution(self, run_id: str, execution_key: str) -> bool:
        row = self.connection.execute(
            """
            UPDATE omnix_agent_capability_executions
               SET state = 'running', updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND execution_key = %s
               AND state IN ('created','waiting_for_approval')
            RETURNING execution_key
            """,
            (self.context.workspace_id, run_id, execution_key),
        ).fetchone()
        return row is not None

    def finish_capability_execution(
        self,
        run_id: str,
        execution_key: str,
        *,
        result_payload: dict[str, Any],
        error: str | None,
        state_changed: bool,
    ) -> None:
        self.connection.execute(
            """
            UPDATE omnix_agent_capability_executions
               SET state = %s, result_payload = %s::jsonb, error = %s,
                   state_changed = %s, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND execution_key = %s
               AND state IN ('created','waiting_for_approval','running')
            """,
            (
                "failed" if error else "completed",
                _json(result_payload),
                error,
                state_changed,
                self.context.workspace_id,
                run_id,
                execution_key,
            ),
        )

    def reserve_evidence_query(
        self,
        run_id: str,
        task_revision_id: str,
        execution_key: str,
        *,
        max_queries: int,
        max_sources: int,
        max_extracts: int,
        requested_sources: int,
        requested_extracts: int,
    ) -> dict[str, Any]:
        """Atomically reserve one evidence attempt and aggregate source/extract capacity."""
        locked = self.connection.execute(
            """
            SELECT revision_id
              FROM omnix_agent_task_revisions
             WHERE workspace_id = %s AND run_id = %s AND revision_id = %s
             FOR UPDATE
            """,
            (self.context.workspace_id, run_id, task_revision_id),
        ).fetchone()
        if locked is None:
            raise KeyError(task_revision_id)

        existing = self.connection.execute(
            """
            SELECT reserved_sources, reserved_extracts, actual_sources,
                   actual_extracts, state
              FROM omnix_agent_evidence_query_reservations
             WHERE workspace_id = %s AND run_id = %s
               AND task_revision_id = %s AND execution_key = %s
            """,
            (
                self.context.workspace_id,
                run_id,
                task_revision_id,
                execution_key,
            ),
        ).fetchone()
        if existing is not None:
            return {
                "allowed": True,
                "reused": True,
                "reserved_sources": int(existing[0] or 0),
                "reserved_extracts": int(existing[1] or 0),
                "actual_sources": int(existing[2] or 0),
                "actual_extracts": int(existing[3] or 0),
                "state": str(existing[4]),
            }

        aggregate = self.connection.execute(
            """
            SELECT COUNT(*),
                   COALESCE(SUM(reserved_sources), 0),
                   COALESCE(SUM(reserved_extracts), 0)
              FROM omnix_agent_evidence_query_reservations
             WHERE workspace_id = %s AND run_id = %s
               AND task_revision_id = %s
            """,
            (self.context.workspace_id, run_id, task_revision_id),
        ).fetchone()
        queries = int(aggregate[0] or 0)
        used_sources = int(aggregate[1] or 0)
        used_extracts = int(aggregate[2] or 0)
        if queries >= max_queries:
            return {"allowed": False, "reason": "query_budget_exceeded"}

        remaining_sources = max(0, max_sources - used_sources)
        remaining_extracts = max(0, max_extracts - used_extracts)
        sources = min(max(0, requested_sources), remaining_sources)
        extracts = min(max(0, requested_extracts), remaining_extracts)
        if requested_sources > 0 and sources <= 0:
            return {"allowed": False, "reason": "source_budget_exceeded"}
        if requested_extracts > 0 and extracts <= 0:
            extracts = 0

        self.connection.execute(
            """
            INSERT INTO omnix_agent_evidence_query_reservations (
                workspace_id, run_id, task_revision_id, execution_key,
                reserved_sources, reserved_extracts
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                self.context.workspace_id,
                run_id,
                task_revision_id,
                execution_key,
                sources,
                extracts,
            ),
        )
        return {
            "allowed": True,
            "reused": False,
            "reserved_sources": sources,
            "reserved_extracts": extracts,
            "actual_sources": 0,
            "actual_extracts": 0,
            "state": "reserved",
        }

    def finish_evidence_query(
        self,
        run_id: str,
        task_revision_id: str,
        execution_key: str,
        *,
        actual_sources: int,
        actual_extracts: int,
        failed: bool,
    ) -> None:
        self.connection.execute(
            """
            UPDATE omnix_agent_evidence_query_reservations
               SET reserved_sources = LEAST(reserved_sources, %s),
                   reserved_extracts = LEAST(reserved_extracts, %s),
                   actual_sources = %s,
                   actual_extracts = %s,
                   state = %s,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s
               AND task_revision_id = %s AND execution_key = %s
            """,
            (
                max(0, actual_sources),
                max(0, actual_extracts),
                max(0, actual_sources),
                max(0, actual_extracts),
                "failed" if failed else "completed",
                self.context.workspace_id,
                run_id,
                task_revision_id,
                execution_key,
            ),
        )

    def reclaim_stale_read_capability_execution(
        self,
        run_id: str,
        execution_key: str,
        *,
        stale_before: datetime,
    ) -> bool:
        row = self.connection.execute(
            """
            UPDATE omnix_agent_capability_executions
               SET state = 'created', updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND execution_key = %s
               AND state = 'running' AND updated_at <= %s
            RETURNING execution_key
            """,
            (
                self.context.workspace_id,
                run_id,
                execution_key,
                stale_before,
            ),
        ).fetchone()
        return row is not None

    def get_usage(self, run_id: str) -> dict[str, Any]:
        self.connection.execute(
            """
            INSERT INTO omnix_agent_run_usage (workspace_id, run_id)
            VALUES (%s, %s)
            ON CONFLICT (workspace_id, run_id) DO NOTHING
            """,
            (self.context.workspace_id, run_id),
        )
        row = self.connection.execute(
            """
            SELECT steps, tool_calls, model_calls, output_tokens, cost
              FROM omnix_agent_run_usage
             WHERE workspace_id = %s AND run_id = %s
            """,
            (self.context.workspace_id, run_id),
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return {
            "steps": int(row[0]),
            "tool_calls": int(row[1]),
            "model_calls": int(row[2]),
            "output_tokens": int(row[3]),
            "cost": float(row[4]),
        }

    def consume_usage(
        self,
        run_id: str,
        *,
        steps: int = 0,
        tool_calls: int = 0,
        model_calls: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
        max_steps: int | None = None,
        max_tool_calls: int | None = None,
        max_output_tokens: int | None = None,
        max_cost: float | None = None,
    ) -> dict[str, Any] | None:
        if min(steps, tool_calls, model_calls, output_tokens) < 0 or cost < 0:
            raise ValueError("usage deltas must be non-negative")
        self.connection.execute(
            """
            INSERT INTO omnix_agent_run_usage (workspace_id, run_id)
            VALUES (%s, %s)
            ON CONFLICT (workspace_id, run_id) DO NOTHING
            """,
            (self.context.workspace_id, run_id),
        )
        row = self.connection.execute(
            """
            UPDATE omnix_agent_run_usage
               SET steps = steps + %s,
                   tool_calls = tool_calls + %s,
                   model_calls = model_calls + %s,
                   output_tokens = output_tokens + %s,
                   cost = cost + %s,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s
               AND (%s::BIGINT IS NULL OR steps + %s <= %s::BIGINT)
               AND (%s::BIGINT IS NULL OR tool_calls + %s <= %s::BIGINT)
               AND (%s::BIGINT IS NULL OR output_tokens + %s <= %s::BIGINT)
               AND (%s::NUMERIC IS NULL OR cost + %s <= %s::NUMERIC)
            RETURNING steps, tool_calls, model_calls, output_tokens, cost
            """,
            (
                steps,
                tool_calls,
                model_calls,
                output_tokens,
                cost,
                self.context.workspace_id,
                run_id,
                max_steps,
                steps,
                max_steps,
                max_tool_calls,
                tool_calls,
                max_tool_calls,
                max_output_tokens,
                output_tokens,
                max_output_tokens,
                max_cost,
                cost,
                max_cost,
            ),
        ).fetchone()
        if row is None:
            return None
        return {
            "steps": int(row[0]),
            "tool_calls": int(row[1]),
            "model_calls": int(row[2]),
            "output_tokens": int(row[3]),
            "cost": float(row[4]),
        }

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
