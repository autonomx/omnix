"""Workflow step state: claims, retries, approvals waits, completion and run status (WP-8.2).

Functions over the workflow runtime; ``PostgresWorkflowRuntime`` keeps one
delegator per function, so callers and tests are unchanged.
"""
from __future__ import annotations

from typing import Any
from app.persistence.unit_of_work import unit_of_work
from .workflows import (
    WorkflowEvent,
)
from typing import TYPE_CHECKING
from .workflow_runtime import (
    _json,
)

if TYPE_CHECKING:
    from app.agent_runtime.workflow_runtime import PostgresWorkflowRuntime


def _step_state(workflow: PostgresWorkflowRuntime, run_id: str, step_id: str) -> dict[str, Any] | None:
    with unit_of_work(workflow.database) as work:
        row = work.connection.execute(
            """
            SELECT status, attempts, result, worker_id, lease_expires_at
              FROM omnix_workflow_step_runs
             WHERE workspace_id = %s AND run_id = %s AND step_id = %s
            """,
            (workflow.context.workspace_id, run_id, step_id),
        ).fetchone()
        work.rollback()
    return (
        {
            "status": str(row[0]),
            "attempts": int(row[1]),
            "result": dict(row[2] or {}),
            "worker_id": str(row[3]) if row[3] else None,
            "lease_expires_at": row[4],
        }
        if row
        else None
    )


def _claim_step(workflow: PostgresWorkflowRuntime, run_id: str, step_id: str) -> int | None:
    with unit_of_work(workflow.database) as work:
        row = work.connection.execute(
            """
            UPDATE omnix_workflow_step_runs
               SET status = 'running', attempts = attempts + 1,
                   started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                   last_error = NULL, worker_id = %s,
                   lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '90 seconds',
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND step_id = %s
               AND status IN ('pending','approved')
            RETURNING attempts
            """,
            (workflow.worker_id, workflow.context.workspace_id, run_id, step_id),
        ).fetchone()
        if row is not None:
            workflow._append_event(
                work.connection,
                WorkflowEvent(
                    run_id=run_id,
                    event_type="workflow.step.started",
                    payload={"step_id": step_id, "attempt": int(row[0])},
                ),
            )
        work.commit()
    return int(row[0]) if row else None


def _set_waiting_for_approval(workflow: PostgresWorkflowRuntime, run_id: str, step_id: str) -> None:
    with unit_of_work(workflow.database) as work:
        row = work.connection.execute(
            """
            UPDATE omnix_workflow_step_runs
               SET status = 'waiting_for_approval'
             WHERE workspace_id = %s AND run_id = %s AND step_id = %s
               AND status = 'pending'
            RETURNING step_id
            """,
            (workflow.context.workspace_id, run_id, step_id),
        ).fetchone()
        if row is not None:
            work.connection.execute(
                """
                UPDATE omnix_workflow_runs
                   SET status = 'waiting_for_approval', revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND run_id = %s
                   AND current_step_id = %s
                """,
                (workflow.context.workspace_id, run_id, step_id),
            )
            workflow._append_event(
                work.connection,
                WorkflowEvent(
                    run_id=run_id,
                    event_type="workflow.approval.requested",
                    payload={"step_id": step_id},
                ),
            )
        work.commit()


def _set_step_retry(workflow: PostgresWorkflowRuntime, run_id: str, step_id: str, error: str) -> bool:
    with unit_of_work(workflow.database) as work:
        row = work.connection.execute(
            """
            UPDATE omnix_workflow_step_runs
               SET status = 'pending', last_error = %s, worker_id = NULL,
                   lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND step_id = %s
               AND status = 'running' AND worker_id = %s
            RETURNING step_id
            """,
            (
                error,
                workflow.context.workspace_id,
                run_id,
                step_id,
                workflow.worker_id,
            ),
        ).fetchone()
        if row is not None:
            workflow._append_event(
                work.connection,
                WorkflowEvent(
                    run_id=run_id,
                    event_type="workflow.step.retry",
                    payload={"step_id": step_id, "error": error},
                ),
            )
        work.commit()
    return row is not None


def _set_step_failed(workflow: PostgresWorkflowRuntime, run_id: str, step_id: str, error: str) -> bool:
    with unit_of_work(workflow.database) as work:
        row = work.connection.execute(
            """
            UPDATE omnix_workflow_step_runs
               SET status = 'failed', last_error = %s,
                   completed_at = CURRENT_TIMESTAMP, worker_id = NULL,
                   lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND step_id = %s
               AND status = 'running' AND worker_id = %s
            RETURNING step_id
            """,
            (
                error,
                workflow.context.workspace_id,
                run_id,
                step_id,
                workflow.worker_id,
            ),
        ).fetchone()
        if row is not None:
            workflow._append_event(
                work.connection,
                WorkflowEvent(
                    run_id=run_id,
                    event_type="workflow.step.failed",
                    payload={"step_id": step_id, "error": error},
                ),
            )
        work.commit()
    return row is not None


def _set_step_completed(
    workflow: PostgresWorkflowRuntime,
    run_id: str,
    step_id: str,
    result: dict[str, Any],
) -> bool:
    with unit_of_work(workflow.database) as work:
        row = work.connection.execute(
            """
            UPDATE omnix_workflow_step_runs
               SET status = 'completed', result = %s::jsonb, last_error = NULL,
                   completed_at = CURRENT_TIMESTAMP, worker_id = NULL,
                   lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND step_id = %s
               AND status = 'running' AND worker_id = %s
            RETURNING step_id
            """,
            (
                _json(result),
                workflow.context.workspace_id,
                run_id,
                step_id,
                workflow.worker_id,
            ),
        ).fetchone()
        if row is not None:
            workflow._append_event(
                work.connection,
                WorkflowEvent(
                    run_id=run_id,
                    event_type="workflow.step.completed",
                    payload={"step_id": step_id, "result": result},
                ),
            )
        work.commit()
    return row is not None


def _transition(workflow: PostgresWorkflowRuntime, run_id: str, target: str | None) -> None:
    if target is None:
        workflow._finish(run_id)
        return
    with unit_of_work(workflow.database) as work:
        row = work.connection.execute(
            """
            UPDATE omnix_workflow_runs
               SET current_step_id = %s, status = 'running',
                   revision = revision + 1, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s
               AND status = 'running'
            RETURNING run_id
            """,
            (target, workflow.context.workspace_id, run_id),
        ).fetchone()
        work.commit()
    if row is None:
        return


def _finish(workflow: PostgresWorkflowRuntime, run_id: str) -> None:
    with unit_of_work(workflow.database) as work:
        work.connection.execute(
            """
            UPDATE omnix_workflow_step_runs
               SET status = 'skipped', completed_at = CURRENT_TIMESTAMP,
                   worker_id = NULL, lease_expires_at = NULL,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s AND status IN ('pending','approved')
            """,
            (workflow.context.workspace_id, run_id),
        )
        row = work.connection.execute(
            """
            UPDATE omnix_workflow_runs
               SET current_step_id = NULL, status = 'completed',
                   revision = revision + 1, updated_at = CURRENT_TIMESTAMP,
                   completed_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s
               AND status NOT IN ('failed','cancelled','completed')
            RETURNING run_id
            """,
            (workflow.context.workspace_id, run_id),
        ).fetchone()
        if row is not None:
            workflow._append_event(
                work.connection,
                WorkflowEvent(
                    run_id=run_id,
                    event_type="workflow.run.completed",
                ),
            )
        work.commit()


def _set_status(workflow: PostgresWorkflowRuntime, run_id: str, status: str, *, error: str | None = None) -> None:
    terminal = status in {"completed", "failed", "cancelled"}
    with unit_of_work(workflow.database) as work:
        row = work.connection.execute(
            """
            UPDATE omnix_workflow_runs
               SET status = %s, last_error = %s, revision = revision + 1,
                   updated_at = CURRENT_TIMESTAMP,
                   completed_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE completed_at END
             WHERE workspace_id = %s AND run_id = %s
            RETURNING run_id
            """,
            (status, error, terminal, workflow.context.workspace_id, run_id),
        ).fetchone()
        if row is not None:
            workflow._append_event(
                work.connection,
                WorkflowEvent(
                    run_id=run_id,
                    event_type=f"workflow.run.{status}",
                    payload={"error": error} if error else {},
                ),
            )
        work.commit()
