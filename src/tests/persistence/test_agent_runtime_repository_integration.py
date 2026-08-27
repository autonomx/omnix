from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.contracts import AgentRunCommand, AgentRunSpec, ModelRef
from app.agent_runtime.repository import AgentLeaseConflict, PostgresAgentRunRepository
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
