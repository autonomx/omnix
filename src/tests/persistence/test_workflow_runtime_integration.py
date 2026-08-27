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
