from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
import uuid

import pytest

from app.agent_runtime.workflow_runtime import PostgresWorkflowRuntime, WorkflowRuntimeError
from app.agent_runtime.workflows import WorkflowDefinition, WorkflowStepDefinition
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-workflow-runtime-tests",
        )
    )


def test_workflow_versions_idempotency_and_stale_step_recovery() -> None:
    database = _database()
    runtime = PostgresWorkflowRuntime(database)
    suffix = uuid.uuid4().hex[:10]
    try:
        immutable = WorkflowDefinition(
            id=f"immutable-{suffix}",
            version=1,
            name="Immutable",
            steps=[],
        )
        runtime.register(immutable)
        assert runtime.register(immutable) == immutable
        with pytest.raises(WorkflowRuntimeError, match="workflow_version_immutable"):
            runtime.register(
                immutable.model_copy(update={"name": "Changed in place"})
            )

        idempotent = WorkflowDefinition(
            id=f"idempotent-{suffix}",
            version=1,
            name="Idempotent",
            steps=[],
        )
        runtime.register(idempotent)
        key = f"idem-{suffix}"
        first = runtime.start(idempotent.id, {"idempotency_key": key})
        second = runtime.start(idempotent.id, {"idempotency_key": key})
        assert second == first

        guarded = WorkflowDefinition(
            id=f"guarded-{suffix}",
            version=1,
            name="Guarded mutation",
            steps=[
                WorkflowStepDefinition(
                    id="set-state",
                    capability_id="home.set_state",
                    input_template={"target": "Desk", "state": "off"},
                )
            ],
        )
        runtime.register(guarded)
        guarded_run = runtime.start(guarded.id, {})
        assert runtime.get_status(guarded_run)["status"] == "waiting_for_approval"

        with unit_of_work(database) as work:
            work.connection.execute(
                """
                UPDATE omnix_workflow_runs
                   SET status = 'running'
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (runtime.context.workspace_id, guarded_run),
            )
            work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = 'running', worker_id = 'dead-worker',
                       lease_expires_at = %s
                 WHERE workspace_id = %s AND run_id = %s AND step_id = 'set-state'
                """,
                (
                    datetime.now(timezone.utc) - timedelta(minutes=5),
                    runtime.context.workspace_id,
                    guarded_run,
                ),
            )
            work.commit()

        runtime._supervise_once()
        recovered = runtime.get_status(guarded_run)
        assert recovered is not None
        assert recovered["status"] == "failed"
    finally:
        runtime._supervisor_stop.set()
        database.close()


def test_workflow_supervisor_resumes_completed_and_pending_safe_boundaries() -> None:
    database = _database()
    runtime = PostgresWorkflowRuntime(database)
    suffix = uuid.uuid4().hex[:10]
    try:
        definition = WorkflowDefinition(
            id=f"resume-safe-{suffix}",
            version=1,
            name="Resume safe boundary",
            steps=[
                WorkflowStepDefinition(
                    id="first",
                    kind="condition",
                    condition="input.ready",
                ),
                WorkflowStepDefinition(
                    id="second",
                    kind="condition",
                    condition="input.ready",
                ),
            ],
        )
        runtime.register(definition)
        run_id = runtime.start(definition.id, {"ready": True})
        assert runtime.get_status(run_id)["status"] == "completed"

        with unit_of_work(database) as work:
            work.connection.execute(
                """
                UPDATE omnix_workflow_runs
                   SET status = 'running', current_step_id = 'first',
                       completed_at = NULL
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (runtime.context.workspace_id, run_id),
            )
            work.connection.execute(
                """
                UPDATE omnix_workflow_step_runs
                   SET status = CASE
                       WHEN step_id = 'first' THEN 'completed'
                       WHEN step_id = 'second' THEN 'pending'
                       ELSE status
                   END,
                   worker_id = NULL, lease_expires_at = NULL,
                   completed_at = CASE
                       WHEN step_id = 'second' THEN NULL
                       ELSE completed_at
                   END
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (runtime.context.workspace_id, run_id),
            )
            work.commit()

        runtime._supervise_once()

        resumed = runtime.get_status(run_id)
        assert resumed is not None
        assert resumed["status"] == "completed"
        assert resumed["current_step_id"] is None
    finally:
        runtime._supervisor_stop.set()
        database.close()


def test_terminal_workflow_ignores_late_pause_resume_and_cancel() -> None:
    database = _database()
    runtime = PostgresWorkflowRuntime(database)
    suffix = uuid.uuid4().hex[:10]
    try:
        definition = WorkflowDefinition(
            id=f"terminal-{suffix}",
            version=1,
            name="Terminal workflow",
            steps=[],
        )
        runtime.register(definition)
        run_id = runtime.start(definition.id, {})
        before = runtime.get_status(run_id)
        assert before is not None
        assert before["status"] == "completed"

        runtime.pause(run_id)
        runtime.resume(run_id)
        runtime.cancel(run_id)

        after = runtime.get_status(run_id)
        assert after is not None
        assert after["status"] == "completed"
        assert after["revision"] == before["revision"]
    finally:
        runtime._supervisor_stop.set()
        database.close()



def test_workflow_schedule_persists_fire_pins_version_and_dispatches_once() -> None:
    database = _database()
    runtime = PostgresWorkflowRuntime(database)
    runtime._supervisor_started = True
    suffix = uuid.uuid4().hex[:10]
    try:
        first = WorkflowDefinition(
            id=f"scheduled-{suffix}",
            version=1,
            name="Scheduled v1",
            steps=[],
        )
        runtime.register(first)
        scheduled_for = datetime.now(timezone.utc) - timedelta(seconds=5)
        schedule_id = runtime.schedule(
            first.id,
            {"source": "scheduler-test"},
            run_at=scheduled_for,
            schedule_id=f"schedule-{suffix}",
        )

        runtime.register(
            WorkflowDefinition(
                id=first.id,
                version=2,
                name="Scheduled v2",
                steps=[],
            )
        )

        runtime._supervise_once()
        runtime._supervise_once()

        schedules = runtime.list_schedules()
        schedule = next(row for row in schedules if row.schedule_id == schedule_id)
        assert schedule.workflow_version == 1
        assert schedule.enabled is False
        assert schedule.next_run_at is None
        assert schedule.last_enqueued_at is not None

        history = runtime.list_runs(workflow_id=first.id)
        scheduled_runs = [
            row
            for row in history
            if str(row["input_payload"].get("idempotency_key", "")).startswith(
                f"workflow-schedule:{schedule_id}:"
            )
        ]
        assert len(scheduled_runs) == 1
        assert scheduled_runs[0]["workflow_version"] == 1
        assert scheduled_runs[0]["status"] == "completed"

        with unit_of_work(database) as work:
            fire = work.connection.execute(
                """
                SELECT status, run_id
                  FROM omnix_workflow_schedule_fires
                 WHERE workspace_id = %s AND schedule_id = %s
                """,
                (runtime.context.workspace_id, schedule_id),
            ).fetchone()
            work.rollback()
        assert fire is not None
        assert str(fire[0]) == "started"
        assert str(fire[1]) == scheduled_runs[0]["run_id"]
    finally:
        runtime._supervisor_stop.set()
        database.close()


def test_workflow_schedule_rejects_unsafe_timing_and_reserved_idempotency() -> None:
    database = _database()
    runtime = PostgresWorkflowRuntime(database)
    runtime._supervisor_started = True
    suffix = uuid.uuid4().hex[:10]
    try:
        definition = WorkflowDefinition(
            id=f"schedule-policy-{suffix}",
            version=1,
            name="Schedule policy",
            steps=[],
        )
        runtime.register(definition)
        with pytest.raises(
            WorkflowRuntimeError,
            match="run_at_must_be_timezone_aware",
        ):
            runtime.schedule(
                definition.id,
                {},
                run_at=datetime.now(),
            )
        with pytest.raises(
            WorkflowRuntimeError,
            match="interval_minimum_60_seconds",
        ):
            runtime.schedule(
                definition.id,
                {},
                run_at=datetime.now(timezone.utc),
                interval_seconds=30,
            )
        with pytest.raises(
            WorkflowRuntimeError,
            match="reserves_idempotency_key",
        ):
            runtime.schedule(
                definition.id,
                {"idempotency_key": "caller-controlled"},
                run_at=datetime.now(timezone.utc),
            )
    finally:
        runtime._supervisor_stop.set()
        database.close()



def test_recurring_workflow_schedule_collapses_missed_intervals() -> None:
    database = _database()
    runtime = PostgresWorkflowRuntime(database)
    runtime._supervisor_started = True
    suffix = uuid.uuid4().hex[:10]
    try:
        definition = WorkflowDefinition(
            id=f"recurring-{suffix}",
            version=1,
            name="Recurring",
            steps=[],
        )
        runtime.register(definition)
        schedule_id = runtime.schedule(
            definition.id,
            {"source": "recurring-test"},
            run_at=datetime.now(timezone.utc) - timedelta(hours=2),
            interval_seconds=60,
            schedule_id=f"recurring-schedule-{suffix}",
        )

        runtime._supervise_once()
        first_history = runtime.list_runs(workflow_id=definition.id)
        runtime._supervise_once()
        second_history = runtime.list_runs(workflow_id=definition.id)

        assert len(first_history) == 1
        assert len(second_history) == 1
        schedule = next(
            row for row in runtime.list_schedules()
            if row.schedule_id == schedule_id
        )
        assert schedule.enabled is True
        assert schedule.next_run_at is not None
        assert schedule.next_run_at > datetime.now(timezone.utc)
    finally:
        runtime._supervisor_stop.set()
        database.close()


def test_cancel_schedule_suppresses_pending_fire() -> None:
    database = _database()
    runtime = PostgresWorkflowRuntime(database)
    runtime._supervisor_started = True
    suffix = uuid.uuid4().hex[:10]
    try:
        definition = WorkflowDefinition(
            id=f"cancel-schedule-{suffix}",
            version=1,
            name="Cancel schedule",
            steps=[],
        )
        runtime.register(definition)
        schedule_id = runtime.schedule(
            definition.id,
            {},
            run_at=datetime.now(timezone.utc) - timedelta(seconds=5),
            schedule_id=f"cancel-schedule-id-{suffix}",
        )
        runtime._enqueue_due_schedule_fires()
        runtime.cancel_schedule(schedule_id)
        runtime._dispatch_pending_schedule_fires()

        assert runtime.list_runs(workflow_id=definition.id) == []
        with unit_of_work(database) as work:
            state = work.connection.execute(
                """
                SELECT status
                  FROM omnix_workflow_schedule_fires
                 WHERE workspace_id = %s AND schedule_id = %s
                """,
                (runtime.context.workspace_id, schedule_id),
            ).fetchone()
            work.rollback()
        assert state is not None
        assert str(state[0]) == "cancelled"
    finally:
        runtime._supervisor_stop.set()
        database.close()
