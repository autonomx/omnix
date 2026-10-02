"""Retention worker for ``omnix_retention_policies`` (WP-5.2).

Every enabled policy with a handler deletes eligible rows in batches (each
batch its own short transaction, bounded by the statement timeout) and the
run is recorded in ``omnix_lifecycle_cleanup_runs``. The scheduled task runs
every policy except maintenance-only ones (audit); the operator command
``python -m app.persistence retention`` runs them all.

Deletes span workspaces under the ``retention`` system scope: eligibility is
by age and state, never by tenant.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from app.observability.metrics import record_retention_deleted

from .tenant_scope import system_scope

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5_000
MAX_BATCHES_PER_POLICY = 50

# Agent run events kept for the life of the run: milestones and evidence.
AGENT_EVENT_KEEP_PREFIXES = ("evidence.", "approval.", "acceptance.", "artifact.")
AGENT_EVENT_KEEP_TYPES = (
    "run.created", "run.started", "run.completed", "run.failed", "run.settled", "run.superseded",
    "task.revised", "quality.review_completed", "quality.self_review_completed", "quality.validation_recorded",
)

Handler = Callable[[Any, int, int], int]


def _outbox(record_type: str) -> Handler:
    def delete(connection: Any, days: int, batch: int) -> int:
        from .outbox_repository import PostgresOutboxRepository

        return PostgresOutboxRepository(connection).delete_retained(
            record_type=record_type, retention_days=days, batch_size=batch,
        )

    return delete


def _rpg_narration(connection: Any, days: int, batch: int) -> int:
    from .rpg_narration_event_repository import PostgresRpgNarrationEventRepository

    return PostgresRpgNarrationEventRepository(connection).delete_retained(retention_days=days, batch_size=batch)


def _sql(statement: str) -> Handler:
    def delete(connection: Any, days: int, batch: int) -> int:
        return int(connection.execute(statement, (days, batch)).rowcount)

    return delete


def _audit(connection: Any, days: int, batch: int) -> int:
    # Migration 0107 makes the table append-only except in maintenance.
    connection.execute("SELECT set_config('omnix.audit_maintenance', 'on', true)")
    return int(connection.execute(
        """DELETE FROM omnix_audit_events WHERE id IN (
               SELECT id FROM omnix_audit_events
                WHERE created_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                ORDER BY created_at, id LIMIT %s)""",
        (days, batch),
    ).rowcount)


HANDLERS: MappingProxyType[str, Handler] = MappingProxyType({
    "outbox_events": _outbox("outbox_events"),
    "outbox_consumer_inbox": _outbox("outbox_consumer_inbox"),
    "outbox_dead_letters": _outbox("outbox_dead_letters"),
    "rpg_narration_events": _rpg_narration,
    "runtime_failure_evidence": _sql(
        """DELETE FROM omnix_runtime_failure_evidence WHERE id IN (
               SELECT id FROM omnix_runtime_failure_evidence
                WHERE created_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                ORDER BY created_at, id LIMIT %s)"""
    ),
    # Terminal jobs; events, logs and attempts go with them (ON DELETE CASCADE).
    "jobs": _sql(
        """DELETE FROM omnix_jobs WHERE ctid IN (
               SELECT ctid FROM omnix_jobs
                WHERE status IN ('completed', 'failed', 'canceled')
                  AND COALESCE(completed_at, updated_at) < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                LIMIT %s)"""
    ),
    # Events of long-lived jobs still accumulate: cap their age as well.
    "job_events": _sql(
        """DELETE FROM omnix_job_events WHERE ctid IN (
               SELECT ctid FROM omnix_job_events
                WHERE created_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                LIMIT %s)"""
    ),
    "agent_run_events": lambda connection, days, batch: int(connection.execute(
        """DELETE FROM omnix_agent_run_events WHERE ctid IN (
               SELECT events.ctid FROM omnix_agent_run_events AS events
                 JOIN omnix_agent_runs AS runs
                   ON runs.workspace_id = events.workspace_id AND runs.run_id = events.run_id
                WHERE runs.status IN ('completed', 'failed', 'cancelled')
                  AND COALESCE(runs.completed_at, runs.updated_at) < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                  AND NOT (events.event_type = ANY(%s))
                  AND NOT (events.event_type LIKE ANY(%s))
                LIMIT %s)""",
        (days, list(AGENT_EVENT_KEEP_TYPES), [prefix + "%" for prefix in AGENT_EVENT_KEEP_PREFIXES], batch),
    ).rowcount),
    "trading_strategy_events": _sql(
        """DELETE FROM omnix_trading_strategy_events WHERE ctid IN (
               SELECT ctid FROM omnix_trading_strategy_events
                WHERE observed_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                LIMIT %s)"""
    ),
    "runtime_nodes": _sql(
        """DELETE FROM omnix_runtime_nodes WHERE ctid IN (
               SELECT ctid FROM omnix_runtime_nodes
                WHERE COALESCE(stopped_at, lease_expires_at, heartbeat_at)
                      < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                  AND (stopped_at IS NOT NULL OR lease_expires_at < CURRENT_TIMESTAMP)
                LIMIT %s)"""
    ),
    "auth_sessions": _sql(
        """DELETE FROM omnix_auth_sessions WHERE ctid IN (
               SELECT ctid FROM omnix_auth_sessions
                WHERE LEAST(expires_at, absolute_expires_at, COALESCE(revoked_at, 'infinity'))
                      < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                LIMIT %s)"""
    ),
    "audit_events": _audit,
})


@dataclass(frozen=True)
class RetentionPolicy:
    record_type: str
    retention_days: int
    maintenance_only: bool


@dataclass
class RetentionReport:
    run_id: int
    deleted: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


class RetentionWorker:
    def __init__(self, database: Any, *, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        if batch_size < 1:
            raise ValueError("retention batch size must be positive")
        self.database = database
        self.batch_size = batch_size

    def policies(self) -> list[RetentionPolicy]:
        with system_scope("retention"), self.database.transaction() as connection:
            rows = connection.execute(
                """SELECT record_type, retention_days, COALESCE((metadata->>'maintenance_only')::boolean, FALSE)
                     FROM omnix_retention_policies WHERE enabled ORDER BY record_type LIMIT 200"""
            ).fetchall()
        return [RetentionPolicy(str(row[0]), int(row[1]), bool(row[2])) for row in rows]

    def run_once(self, *, include_maintenance: bool = False) -> RetentionReport:
        with system_scope("retention"), self.database.transaction() as connection:
            run_id = int(connection.execute(
                "INSERT INTO omnix_lifecycle_cleanup_runs (status) VALUES ('running') RETURNING id"
            ).fetchone()[0])
        report = RetentionReport(run_id=run_id)
        try:
            for policy in self.policies():
                handler = HANDLERS.get(policy.record_type)
                if handler is None or (policy.maintenance_only and not include_maintenance):
                    report.skipped.append(policy.record_type)
                    continue
                report.deleted[policy.record_type] = self._run_policy(handler, policy)
                record_retention_deleted(policy.record_type, report.deleted[policy.record_type])
        except Exception as exc:
            self._finish(run_id, "failed", report, error=f"{type(exc).__name__}: {exc}"[:2000])
            raise
        self._finish(run_id, "completed", report)
        return report

    def _run_policy(self, handler: Handler, policy: RetentionPolicy) -> int:
        total = 0
        for _ in range(MAX_BATCHES_PER_POLICY):
            with system_scope("retention"), self.database.transaction() as connection:
                deleted = handler(connection, policy.retention_days, self.batch_size)
            total += deleted
            if deleted < self.batch_size:
                break
        return total

    def _finish(self, run_id: int, status: str, report: RetentionReport, *, error: str | None = None) -> None:
        with system_scope("retention"), self.database.transaction() as connection:
            connection.execute(
                """UPDATE omnix_lifecycle_cleanup_runs
                      SET status = %s, completed_at = CURRENT_TIMESTAMP, deleted_counts = %s::jsonb, error = %s
                    WHERE id = %s""",
                (status, json.dumps(report.deleted, sort_keys=True), error, run_id),
            )
        logger.info("retention_run status=%s deleted=%s skipped=%s", status, report.deleted, report.skipped)


def latest_cleanup_run(connection: Any) -> dict[str, Any] | None:
    """The newest retention run for diagnostics: status, times, counts and the error's class only."""
    row = connection.execute(
        """SELECT status, started_at, completed_at, deleted_counts, error
             FROM omnix_lifecycle_cleanup_runs ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    if row is None:
        return None
    error = str(row[4] or "")
    return {
        "status": str(row[0]),
        "started_at": row[1].isoformat() if row[1] is not None else None,
        "completed_at": row[2].isoformat() if row[2] is not None else None,
        "deleted": {str(key): int(value) for key, value in dict(row[3] or {}).items()},
        # Stored as "<Type>: <message>"; the message can name tables and values.
        "error_class": error.split(":", 1)[0].strip() or None if error else None,
    }


__all__ = ["HANDLERS", "RetentionPolicy", "RetentionReport", "RetentionWorker", "latest_cleanup_run"]
