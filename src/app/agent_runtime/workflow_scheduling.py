"""Workflow schedules: registration of schedules, due fires and the supervisor pass (WP-8.2).

Functions over the workflow runtime; ``PostgresWorkflowRuntime`` keeps one
delegator per function, so callers and tests are unchanged.
"""
from __future__ import annotations

from .exception_logging import log_recovered_exception
from datetime import datetime, timedelta, timezone
import uuid
from app.persistence.unit_of_work import unit_of_work
from .workflows import (
    WorkflowEvent,
    WorkflowScheduleSnapshot,
)
from typing import TYPE_CHECKING
from .workflow_runtime import (
    WorkflowRuntimeError,
    _json,
)

if TYPE_CHECKING:
    from app.agent_runtime.workflow_runtime import PostgresWorkflowRuntime


def schedule(
    workflow: PostgresWorkflowRuntime,
    workflow_id: str,
    input_payload: dict[str, object],
    *,
    run_at: datetime,
    interval_seconds: int | None = None,
    version: int | None = None,
    schedule_id: str | None = None,
) -> str:
    workflow._ensure_supervisor()
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise WorkflowRuntimeError("workflow_schedule_run_at_must_be_timezone_aware")
    if interval_seconds is not None and int(interval_seconds) < 60:
        raise WorkflowRuntimeError("workflow_schedule_interval_minimum_60_seconds")
    if "idempotency_key" in input_payload:
        raise WorkflowRuntimeError("workflow_schedule_input_reserves_idempotency_key")
    definition = workflow._definition(workflow_id, version=version)
    if definition is None:
        raise KeyError(workflow_id)
    issued_id = str(schedule_id or uuid.uuid4().hex).strip()
    if not issued_id:
        raise WorkflowRuntimeError("workflow_schedule_id_required")
    normalized_run_at = run_at.astimezone(timezone.utc)
    interval = int(interval_seconds) if interval_seconds is not None else None
    with unit_of_work(workflow.database) as work:
        inserted = work.connection.execute(
            """
            INSERT INTO omnix_workflow_schedules (
                workspace_id, schedule_id, workflow_id, workflow_version,
                input_payload, interval_seconds, next_run_at, enabled
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, TRUE)
            ON CONFLICT (workspace_id, schedule_id) DO NOTHING
            RETURNING schedule_id
            """,
            (
                workflow.context.workspace_id,
                issued_id,
                definition.id,
                definition.version,
                _json(input_payload),
                interval,
                normalized_run_at,
            ),
        ).fetchone()
        if inserted is None:
            existing = work.connection.execute(
                """
                SELECT workflow_id, workflow_version, input_payload,
                       interval_seconds, next_run_at, enabled
                  FROM omnix_workflow_schedules
                 WHERE workspace_id = %s AND schedule_id = %s
                """,
                (workflow.context.workspace_id, issued_id),
            ).fetchone()
            if existing is None:
                raise WorkflowRuntimeError("workflow_schedule_conflict")
            same = (
                str(existing[0]) == definition.id
                and int(existing[1]) == definition.version
                and dict(existing[2] or {}) == dict(input_payload)
                and (
                    int(existing[3]) if existing[3] is not None else None
                ) == interval
                and existing[4] == normalized_run_at
                and bool(existing[5])
            )
            if not same:
                raise WorkflowRuntimeError(
                    f"workflow_schedule_id_reused:{issued_id}"
                )
            work.rollback()
            return issued_id
        work.commit()
    return issued_id


def list_schedules(workflow: PostgresWorkflowRuntime) -> list[WorkflowScheduleSnapshot]:
    with unit_of_work(workflow.database) as work:
        rows = work.connection.execute(
            """
            SELECT schedule_id, workflow_id, workflow_version, input_payload,
                   interval_seconds, next_run_at, enabled, last_enqueued_at
              FROM omnix_workflow_schedules
             WHERE workspace_id = %s
             ORDER BY created_at, schedule_id
            """,
            (workflow.context.workspace_id,),
        ).fetchall()
        work.rollback()
    return [
        WorkflowScheduleSnapshot(
            schedule_id=str(row[0]),
            workflow_id=str(row[1]),
            workflow_version=int(row[2]),
            input_payload=dict(row[3] or {}),
            interval_seconds=int(row[4]) if row[4] is not None else None,
            next_run_at=row[5],
            enabled=bool(row[6]),
            last_enqueued_at=row[7],
        )
        for row in rows
    ]


def cancel_schedule(workflow: PostgresWorkflowRuntime, schedule_id: str) -> None:
    with unit_of_work(workflow.database) as work:
        row = work.connection.execute(
            """
            UPDATE omnix_workflow_schedules
               SET enabled = FALSE, next_run_at = NULL,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND schedule_id = %s
            RETURNING schedule_id
            """,
            (workflow.context.workspace_id, schedule_id),
        ).fetchone()
        if row is None:
            raise KeyError(schedule_id)
        work.connection.execute(
            """
            UPDATE omnix_workflow_schedule_fires
               SET status = 'cancelled',
                   last_error = 'schedule_cancelled_before_dispatch',
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND schedule_id = %s
               AND status = 'pending'
            """,
            (workflow.context.workspace_id, schedule_id),
        )
        work.commit()


def _supervise_once(workflow: PostgresWorkflowRuntime) -> None:
    workflow._enqueue_due_schedule_fires()
    workflow._dispatch_pending_schedule_fires()
    error = "step_outcome_unknown_after_worker_loss"
    resumable: list[str] = []
    with unit_of_work(workflow.database) as work:
        work.connection.execute(
            """
            UPDATE omnix_workflow_step_runs
               SET lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND worker_id = %s
               AND status = 'running'
            """,
            (workflow.context.workspace_id, workflow.worker_id),
        )
        stale = work.connection.execute(
            """
            SELECT step.run_id, step.step_id
              FROM omnix_workflow_step_runs AS step
              JOIN omnix_workflow_runs AS run
                ON run.workspace_id = step.workspace_id
               AND run.run_id = step.run_id
             WHERE step.workspace_id = %s
               AND run.status = 'running'
               AND run.current_step_id = step.step_id
               AND step.status = 'running'
               AND step.lease_expires_at <= CURRENT_TIMESTAMP
             FOR UPDATE OF step SKIP LOCKED
            """,
            (workflow.context.workspace_id,),
        ).fetchall()
        for run_id, step_id in stale:
            claimed = work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = 'failed', last_error = %s,
                       completed_at = CURRENT_TIMESTAMP,
                       worker_id = NULL, lease_expires_at = NULL,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s AND step_id = %s
                   AND status = 'running'
                   AND lease_expires_at <= CURRENT_TIMESTAMP
                RETURNING step_id
                """,
                (
                    error,
                    workflow.context.workspace_id,
                    str(run_id),
                    str(step_id),
                ),
            ).fetchone()
            if claimed is None:
                continue
            failed_run = work.connection.execute(
                """
                UPDATE omnix_workflow_runs
                   SET status = 'failed', last_error = %s,
                       revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP,
                       completed_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s
                   AND status = 'running'
                RETURNING run_id
                """,
                (error, workflow.context.workspace_id, str(run_id)),
            ).fetchone()
            if failed_run is not None:
                workflow._append_event(
                    work.connection,
                    WorkflowEvent(
                        run_id=str(run_id),
                        event_type="workflow.step.failed",
                        payload={
                            "step_id": str(step_id),
                            "error": error,
                        },
                    ),
                )
                workflow._append_event(
                    work.connection,
                    WorkflowEvent(
                        run_id=str(run_id),
                        event_type="workflow.run.failed",
                        payload={"error": error},
                    ),
                )
        resumable = [
            str(row[0])
            for row in work.connection.execute(
                """
                SELECT DISTINCT run.run_id
                  FROM omnix_workflow_runs AS run
                  JOIN omnix_workflow_step_runs AS step
                    ON step.workspace_id = run.workspace_id
                   AND step.run_id = run.run_id
                   AND step.step_id = run.current_step_id
                 WHERE run.workspace_id = %s
                   AND run.status = 'running'
                   AND step.status IN ('pending','approved','completed')
                 ORDER BY run.run_id
                """,
                (workflow.context.workspace_id,),
            ).fetchall()
        ]
        work.commit()
    for run_id in resumable:
        try:
            workflow._advance(run_id)
        except Exception as exc:
            # The run remains durable; the next supervisor pass retries only
            # safe boundary states. In-flight side effects are never replayed.
            log_recovered_exception("workflow recovery", exc)
            continue


def _enqueue_due_schedule_fires(workflow: PostgresWorkflowRuntime) -> None:
    now = datetime.now(timezone.utc)
    with unit_of_work(workflow.database) as work:
        rows = work.connection.execute(
            """
            SELECT schedule_id, next_run_at, interval_seconds
              FROM omnix_workflow_schedules
             WHERE workspace_id = %s AND enabled
               AND next_run_at IS NOT NULL
               AND next_run_at <= CURRENT_TIMESTAMP
             ORDER BY next_run_at, schedule_id
             FOR UPDATE SKIP LOCKED
             LIMIT 50
            """,
            (workflow.context.workspace_id,),
        ).fetchall()
        for schedule_id, scheduled_for, interval_seconds in rows:
            work.connection.execute(
                """
                INSERT INTO omnix_workflow_schedule_fires (
                    workspace_id, schedule_id, scheduled_for, status
                ) VALUES (%s, %s, %s, 'pending')
                ON CONFLICT (workspace_id, schedule_id, scheduled_for)
                DO NOTHING
                """,
                (
                    workflow.context.workspace_id,
                    str(schedule_id),
                    scheduled_for,
                ),
            )
            if interval_seconds is None:
                next_run_at = None
                enabled = False
            else:
                interval = int(interval_seconds)
                elapsed = max(
                    0.0,
                    (now - scheduled_for).total_seconds(),
                )
                intervals_to_advance = int(elapsed // interval) + 1
                next_run_at = scheduled_for + timedelta(
                    seconds=interval * intervals_to_advance
                )
                enabled = True
            work.connection.execute(
                """
                UPDATE omnix_workflow_schedules
                   SET last_enqueued_at = %s, next_run_at = %s,
                       enabled = %s, updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND schedule_id = %s
                """,
                (
                    scheduled_for,
                    next_run_at,
                    enabled,
                    workflow.context.workspace_id,
                    str(schedule_id),
                ),
            )
        work.commit()


def _dispatch_pending_schedule_fires(workflow: PostgresWorkflowRuntime) -> None:
    with unit_of_work(workflow.database) as work:
        rows = work.connection.execute(
            """
            SELECT fire.schedule_id, fire.scheduled_for,
                   schedule.workflow_id, schedule.workflow_version,
                   schedule.input_payload
              FROM omnix_workflow_schedule_fires AS fire
              JOIN omnix_workflow_schedules AS schedule
                ON schedule.workspace_id = fire.workspace_id
               AND schedule.schedule_id = fire.schedule_id
             WHERE fire.workspace_id = %s AND fire.status = 'pending'
             ORDER BY fire.created_at, fire.schedule_id, fire.scheduled_for
             LIMIT 50
            """,
            (workflow.context.workspace_id,),
        ).fetchall()
        work.rollback()
    for schedule_id, scheduled_for, workflow_id, version, input_payload in rows:
        definition = workflow._definition(
            str(workflow_id),
            version=int(version),
        )
        if definition is None:
            with unit_of_work(workflow.database) as work:
                work.connection.execute(
                    """
                    UPDATE omnix_workflow_schedule_fires
                       SET status = 'failed',
                           last_error = 'workflow_definition_missing',
                           updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND schedule_id = %s
                       AND scheduled_for = %s AND status = 'pending'
                    """,
                    (
                        workflow.context.workspace_id,
                        str(schedule_id),
                        scheduled_for,
                    ),
                )
                work.commit()
            continue
        payload = dict(input_payload or {})
        payload["idempotency_key"] = (
            f"workflow-schedule:{schedule_id}:"
            f"{scheduled_for.astimezone(timezone.utc).isoformat()}"
        )
        try:
            run_id = workflow._start_definition(definition, payload)
        except Exception as exc:
            # Keep the fire pending. A later supervisor pass retries the
            # durable dispatch; deterministic run idempotency prevents
            # duplicate workflow execution if the first attempt committed.
            log_recovered_exception("scheduled workflow dispatch", exc)
            continue
        with unit_of_work(workflow.database) as work:
            work.connection.execute(
                """
                UPDATE omnix_workflow_schedule_fires
                   SET status = 'started', run_id = %s, last_error = NULL,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND schedule_id = %s
                   AND scheduled_for = %s AND status = 'pending'
                """,
                (
                    run_id,
                    workflow.context.workspace_id,
                    str(schedule_id),
                    scheduled_for,
                ),
            )
            work.commit()
