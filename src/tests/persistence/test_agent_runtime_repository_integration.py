from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.contracts import AgentRunCommand, AgentRunSpec, ModelRef
from app.agent_runtime.repository import AgentLeaseConflict, PostgresAgentRunRepository
from app.agent_runtime.service import AgentRunService
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
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
            application_name="omnix-agent-runtime-tests",
        )
    )


def test_agent_run_state_commands_events_and_leases_are_durable() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-{uuid.uuid4().hex}"
        spec = AgentRunSpec(run_id=run_id, task="Inspect", model=ModelRef(provider_id="test", model_id="model"))
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            created = repository.create_run(spec)
            command = AgentRunCommand(run_id=run_id, command_type="pause", idempotency_key="pause-once")
            first = repository.enqueue_command(command)
            duplicate = repository.enqueue_command(command.model_copy(update={"command_id": "different"}))
            lease = repository.acquire_lease(run_id, worker_id="worker-a")
            assert first.command_id == duplicate.command_id
            assert lease.worker_id == "worker-a"
            assert repository.list_events(run_id)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            persisted = repository.get_run(run_id)
            assert persisted is not None
            assert persisted.spec.task == "Inspect"
            commands = repository.claim_commands(run_id)
            assert [item.command_type for item in commands] == ["pause"]
            with pytest.raises(AgentLeaseConflict):
                repository.acquire_lease(run_id, worker_id="worker-b")
            work.rollback()
    finally:
        database.close()


def test_recovery_start_failure_fails_run_instead_of_renewing_zombie_lease(monkeypatch) -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-recovery-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Recover me",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            created = repository.create_run(spec)
            repository.acquire_lease(run_id, worker_id="dead-worker", ttl_seconds=90)
            repository.update_state(
                run_id,
                expected_revision=created.revision,
                status="running",
                worker_id="dead-worker",
            )
            work.connection.execute(
                """
                UPDATE omnix_agent_worker_leases
                   SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (context.workspace_id, run_id),
            )
            work.commit()

        service = AgentRunService(database, worker_id="recovery-worker")
        service._supervisor_started = True

        def _boom(_spec):
            raise RuntimeError("pi restart failed")

        monkeypatch.setattr(service.runtime, "start", _boom)

        assert service.recover_orphaned_runs() == []

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            persisted = repository.get_run(run_id)
            assert persisted is not None
            assert persisted.status == "failed"
            assert persisted.desired_state == "cancelled"
            assert persisted.last_error is not None
            assert "recovery_failed:RuntimeError: pi restart failed" in persisted.last_error
            work.rollback()
    finally:
        database.close()
