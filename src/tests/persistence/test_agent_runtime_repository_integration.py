from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.contracts import AgentEvent, AgentRunCommand, AgentRunSpec, ModelRef
from app.agent_runtime.repository import AgentLeaseConflict, PostgresAgentRunRepository
from app.agent_runtime.service import AgentRunService
from app.agent_runtime.service_core import AgentRunService as CoreAgentRunService
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


def test_terminal_agent_run_ignores_late_commands_and_runtime_events() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-terminal-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Already done",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            created = repository.create_run(spec)
            terminal = repository.update_state(
                run_id,
                expected_revision=created.revision,
                status="completed",
            )
            work.commit()

        service = AgentRunService(database, worker_id="terminal-worker")
        service._supervisor_started = True

        after_command = service.command(
            AgentRunCommand(
                run_id=run_id,
                command_type="pause",
                idempotency_key="late-pause",
            )
        )
        assert after_command.status == "completed"
        assert after_command.revision == terminal.revision

        service._persist_runtime_event(
            AgentEvent(
                run_id=run_id,
                event_type="run.started",
                payload={"source": "late-pi"},
            )
        )
        service._persist_runtime_event(
            AgentEvent(
                run_id=run_id,
                event_type="run.failed",
                payload={"error": "late failure"},
            )
        )

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            persisted = repository.get_run(run_id)
            assert persisted is not None
            assert persisted.status == "completed"
            assert persisted.revision == terminal.revision
            command_status = work.connection.execute(
                """
                SELECT status
                  FROM omnix_agent_run_commands
                 WHERE workspace_id = %s AND run_id = %s
                   AND idempotency_key = 'late-pause'
                """,
                (context.workspace_id, run_id),
            ).fetchone()
            assert command_status is not None
            assert str(command_status[0]) == "consumed"
            work.rollback()
    finally:
        database.close()


def test_terminal_parent_propagates_cancellation_to_running_child() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        parent_id = f"agent-parent-{uuid.uuid4().hex}"
        child_id = f"agent-child-{uuid.uuid4().hex}"
        parent_spec = AgentRunSpec(
            run_id=parent_id,
            task="Parent",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        child_spec = AgentRunSpec(
            run_id=child_id,
            parent_run_id=parent_id,
            task="Child",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            parent = repository.create_run(parent_spec)
            repository.update_state(
                parent_id,
                expected_revision=parent.revision,
                status="failed",
                desired_state="cancelled",
                last_error="parent_failed",
            )
            child = repository.create_run(child_spec)
            repository.update_state(
                child_id,
                expected_revision=child.revision,
                status="running",
                worker_id="dead-child-worker",
            )
            work.commit()

        service = AgentRunService(database, worker_id="parent-propagation-worker")
        service._supervisor_started = True
        service._supervise_once()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            persisted = repository.get_run(child_id)
            assert persisted is not None
            assert persisted.status == "cancelled"
            assert persisted.desired_state == "cancelled"
            work.rollback()
    finally:
        database.close()



def test_lease_renewal_preserves_token_and_requires_active_owner() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-renew-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Renew lease",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(spec)
            acquired = repository.acquire_lease(run_id, worker_id="worker-a", ttl_seconds=90)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            renewed = repository.renew_lease(run_id, worker_id="worker-a", ttl_seconds=120)
            assert renewed.worker_id == "worker-a"
            assert renewed.lease_token == acquired.lease_token
            assert renewed.revision == acquired.revision + 1
            assert renewed.lease_expires_at >= acquired.lease_expires_at
            with pytest.raises(AgentLeaseConflict):
                repository.renew_lease(run_id, worker_id="worker-b", ttl_seconds=120)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            work.connection.execute(
                """
                UPDATE omnix_agent_worker_leases
                   SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (context.workspace_id, run_id),
            )
            with pytest.raises(AgentLeaseConflict):
                repository.renew_lease(run_id, worker_id="worker-a", ttl_seconds=120)
            takeover = repository.acquire_lease(run_id, worker_id="worker-b", ttl_seconds=120)
            assert takeover.worker_id == "worker-b"
            assert takeover.lease_token != acquired.lease_token
            work.commit()
    finally:
        database.close()


def test_lease_renewal_does_not_wait_for_authoritative_run_row_lock() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-renew-lock-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Renew while acceptance owns run row",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(spec)
            repository.acquire_lease(run_id, worker_id="worker-a", ttl_seconds=90)
            work.commit()

        # Simulate review/acceptance holding the authoritative run row. The
        # renewal connection uses an aggressive lock timeout so this becomes a
        # regression test for the exact contention seen in production logs.
        with unit_of_work(database) as run_lock_work:
            run_lock_work.connection.execute(
                """
                SELECT revision
                  FROM omnix_agent_runs
                 WHERE workspace_id = %s AND run_id = %s
                 FOR UPDATE
                """,
                (context.workspace_id, run_id),
            ).fetchone()
            with unit_of_work(database) as renew_work:
                renew_work.connection.execute("SET LOCAL lock_timeout = '250ms'")
                repository = PostgresAgentRunRepository(renew_work.connection, context)
                renewed = repository.renew_lease(run_id, worker_id="worker-a", ttl_seconds=90)
                assert renewed.worker_id == "worker-a"
                renew_work.commit()
            run_lock_work.rollback()
    finally:
        database.close()


def test_service_heartbeat_renews_lease_without_appending_ordered_event() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-heartbeat-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Heartbeat without event contention",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(spec)
            acquired = repository.acquire_lease(run_id, worker_id="worker-a", ttl_seconds=90)
            before_events = repository.list_events(run_id)
            work.commit()

        service = CoreAgentRunService(database, worker_id="worker-a")
        service._supervisor_started = True
        service.heartbeat(run_id, ttl_seconds=120)

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            after_events = repository.list_events(run_id)
            lease_row = work.connection.execute(
                """
                SELECT lease_token, revision
                  FROM omnix_agent_worker_leases
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (context.workspace_id, run_id),
            ).fetchone()
            assert [event.event_id for event in after_events] == [event.event_id for event in before_events]
            assert all(event.event_type != "worker.heartbeat" for event in after_events)
            assert lease_row is not None
            assert str(lease_row[0]) == acquired.lease_token
            assert int(lease_row[1]) == acquired.revision + 1
            work.rollback()
    finally:
        database.close()


def test_supervisor_stops_local_runtime_when_lease_authority_is_lost(monkeypatch) -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-lease-loss-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Lose ownership",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            created = repository.create_run(spec)
            repository.acquire_lease(run_id, worker_id="worker-b", ttl_seconds=90)
            repository.update_state(
                run_id,
                expected_revision=created.revision,
                status="running",
                worker_id="worker-a",
            )
            work.commit()

        service = CoreAgentRunService(database, worker_id="worker-a")
        service._supervisor_started = True
        closed: list[str] = []
        stalled: list[str] = []
        monkeypatch.setattr(service.budgets, "enforce_wall_time", lambda _run_id: None)
        monkeypatch.setattr(service.runtime, "close_run", lambda value: closed.append(value))
        monkeypatch.setattr(service.runtime, "active_run_ids", lambda: set())
        monkeypatch.setattr(service, "recover_orphaned_runs", lambda: [])
        monkeypatch.setattr(service, "_supervise_stalled_run", lambda value: stalled.append(value))

        service._supervise_once()

        assert closed == [run_id]
        assert stalled == []
    finally:
        database.close()


def test_transient_heartbeat_failure_does_not_skip_progress_supervision(monkeypatch) -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-heartbeat-transient-{uuid.uuid4().hex}"
        worker_id = f"worker-transient-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Transient heartbeat failure",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            created = repository.create_run(spec)
            repository.acquire_lease(run_id, worker_id=worker_id, ttl_seconds=90)
            repository.update_state(
                run_id,
                expected_revision=created.revision,
                status="running",
                worker_id=worker_id,
            )
            work.commit()

        service = CoreAgentRunService(database, worker_id=worker_id)
        service._supervisor_started = True
        stalled: list[str] = []
        monkeypatch.setattr(service.budgets, "enforce_wall_time", lambda _run_id: None)
        monkeypatch.setattr(service, "heartbeat", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("transient db failure")))
        monkeypatch.setattr(service, "_supervise_stalled_run", lambda value: stalled.append(value))
        monkeypatch.setattr(service.runtime, "active_run_ids", lambda: set())
        monkeypatch.setattr(service, "recover_orphaned_runs", lambda: [])

        service._supervise_once()

        assert stalled == [run_id]
    finally:
        database.close()
