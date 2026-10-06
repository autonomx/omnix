from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
import time
import uuid
from types import SimpleNamespace

import pytest

from app.platform.agent_runtime.contracts import (
    AgentEvent,
    AgentApproval,
    AgentRunCommand,
    AgentRunSpec,
    ModelRef,
    TaskRevision,
)
from app.platform.agent_runtime.repository import (
    AgentLeaseConflict,
    AgentRunConcurrencyError,
    PostgresAgentRunRepository,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for runtime concurrency tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=12,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-agent-concurrency-tests",
        )
    )


def _create_run(database: PostgresDatabase) -> tuple[object, str, int]:
    context = ensure_local_identity(database)
    run_id = f"race-{uuid.uuid4().hex}"
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        snapshot = repository.create_run(
            AgentRunSpec(
                run_id=run_id,
                task="concurrency test",
                model=ModelRef(provider_id="test", model_id="model"),
            )
        )
        work.commit()
    return context, run_id, snapshot.revision


def _agent_run_owner_process(url: str, tenant_values: tuple, control) -> None:
    from app.platform.agent_runtime.contracts import AgentEvent
    from app.platform.agent_runtime.jobs import (
        AGENT_RUN_JOB_HANDLERS,
        create_agent_promote_request,
        enqueue_agent_job,
    )
    from app.platform.agent_runtime.service import AgentRunService
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.jobs.handlers import JobHandlerRegistry
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.runtime.tenant_context import TenantContext, install_process_tenant
    from app.composition.worker_runtime.durable_feature_worker import DurableFeatureJobWorker

    database = PostgresDatabase(DatabaseSettings(url=url, pool_min=1, pool_max=6))
    context = TenantContext(
        user_id=tenant_values[0],
        workspace_id=tenant_values[1],
        membership_id=tenant_values[2],
        roles=frozenset(tenant_values[3]),
    )
    # Like application processes (persistence.startup), this owner process
    # runs as its tenant, which row-level security requires (WP-4.4).
    install_process_tenant(context)
    try:
        jobs = PostgresJobStoreAdapter(database, context=context)
        service = AgentRunService(
            database,
            context=context,
            job_store=jobs,
            worker_id=f"agent-owner:{os.getpid()}",
        )

        class Runtime:
            def __init__(self) -> None:
                self.active: dict[str, str] = {}
                self.commands: list[str] = []

            def start(self, spec: AgentRunSpec) -> None:
                self.active[spec.run_id] = "running"

            def get_status(self, run_id: str):
                # Matches the runtime contract: a snapshot-like status or None.
                status = self.active.get(run_id)
                return SimpleNamespace(run_id=run_id, status=status, desired_state="running") if status else None

            def command(self, command: AgentRunCommand):
                self.commands.append(command.command_type)

            def close_run(self, run_id: str) -> None:
                self.active.pop(run_id, None)

        runtime = Runtime()
        service.runtime = runtime
        service._advance_quality_on_settle = None
        service._dispatch_pending_quality_commands = lambda *_args, **_kwargs: None
        service._finalize_acceptance = lambda repository, current: repository.update_state(
            current.run_id,
            expected_revision=current.revision,
            status="completed",
        )
        # Agent lifecycle jobs run through a real leased job worker, as in production.
        handlers = JobHandlerRegistry(AGENT_RUN_JOB_HANDLERS)
        worker = DurableFeatureJobWorker(
            jobs,
            handlers,
            pool_name="agent",
            services=SimpleNamespace(agent_runs=service, jobs=jobs),
            poll_seconds=0.05,
            max_concurrency=1,
            shutdown_grace_seconds=5,
            worker_id=f"agent-owner-jobs:{os.getpid()}",
        )
        worker.start()

        def wait_for_status(run_id: str, expected: str) -> str:
            deadline = time.monotonic() + 30
            status = service.get(run_id).status
            while status != expected and time.monotonic() < deadline:
                time.sleep(0.05)
                status = service.get(run_id).status
            return status

        control.send({"event": "ready", "pid": os.getpid()})

        while True:
            request = control.recv()
            action = request["action"]
            run_id = request["run_id"]
            if action == "start":
                # The API process already enqueued agent.workspace.prepare, which
                # enqueues agent.run.start; the worker claims and runs both.
                assert wait_for_status(run_id, "starting") == "starting"
                service._persist_runtime_event(
                    AgentEvent(run_id=run_id, event_type="run.started")
                )
                control.send({"event": "started", "status": service.get(run_id).status})
            elif action == "poll":
                # The owner's supervisor also delivers commands; wait until every
                # command for the run has left the pending/claimed states.
                deadline = time.monotonic() + 30
                while True:
                    service._deliver_pending_commands(run_id)
                    with database.connection() as connection:
                        outstanding = connection.execute(
                            """
                            SELECT count(*) FROM omnix_agent_run_commands
                             WHERE workspace_id = %s AND run_id = %s
                               AND status NOT IN ('consumed', 'failed')
                            """,
                            (context.workspace_id, run_id),
                        ).fetchone()[0]
                    if not outstanding or time.monotonic() > deadline:
                        break
                    time.sleep(0.05)
                control.send({"event": "delivered", "commands": list(runtime.commands)})
            elif action == "complete":
                settled = AgentEvent(run_id=run_id, event_type="run.settled")
                service._persist_runtime_event(settled)
                promote_request = create_agent_promote_request(
                    run_id, trigger_id=settled.event_id
                )
                enqueue_agent_job(
                    jobs,
                    promote_request,
                    idempotency_key=f"run:{run_id}:promote:{settled.event_id}",
                )
                control.send({"event": "completed", "status": wait_for_status(run_id, "completed")})
            elif action == "stop":
                worker.stop(grace_seconds=5)
                control.send({"event": "stopped"})
                return
    except BaseException as exc:
        control.send({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        raise
    finally:
        database.close()


def _receive_agent_owner(control, event: str):
    assert control.poll(45), f"timed out waiting for {event}"
    payload = control.recv()
    assert payload.get("event") == event, payload
    return payload


def test_concurrent_duplicate_commands_collapse_to_one_durable_command() -> None:
    database = _database()
    try:
        context, run_id, _ = _create_run(database)

        def enqueue(index: int) -> str:
            command = AgentRunCommand(
                command_id=f"command-{index}",
                run_id=run_id,
                command_type="pause",
                idempotency_key="same-logical-command",
            )
            with unit_of_work(database) as work:
                repository = PostgresAgentRunRepository(work.connection, context)
                stored, _status = repository.enqueue_command_with_status(command)
                work.commit()
                return stored.command_id

        with ThreadPoolExecutor(max_workers=6) as pool:
            command_ids = list(pool.map(enqueue, range(6)))

        assert len(set(command_ids)) == 1

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            rows = work.connection.execute(
                """
                SELECT COUNT(*)
                  FROM omnix_agent_run_commands
                 WHERE workspace_id = %s AND run_id = %s
                   AND idempotency_key = %s
                """,
                (context.workspace_id, run_id, "same-logical-command"),
            ).fetchone()
            events = repository.list_events(run_id, after_sequence=0, limit=5000)
            work.rollback()

        assert int(rows[0]) == 1
        command_events = [
            event
            for event in events
            if event.payload.get("command_id") == command_ids[0]
        ]
        assert len(command_events) == 1
    finally:
        database.close()


def test_optimistic_run_revision_allows_exactly_one_concurrent_update() -> None:
    database = _database()
    try:
        context, run_id, revision = _create_run(database)
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            lease = repository.acquire_lease(run_id, worker_id="worker-race")
            work.commit()

        def update(worker: str) -> str:
            try:
                with unit_of_work(database) as work:
                    repository = PostgresAgentRunRepository(work.connection, context)
                    repository.update_state(
                        run_id,
                        expected_revision=revision,
                        status="running",
                        worker_id=lease.worker_id,
                        lease_token=lease.lease_token,
                    )
                    work.commit()
                return "updated"
            except AgentRunConcurrencyError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(update, ("worker-a", "worker-b")))

        assert sorted(outcomes) == ["conflict", "updated"]
    finally:
        database.close()


def test_run_state_update_rejects_superseded_lease_token() -> None:
    database = _database()
    try:
        context, run_id, revision = _create_run(database)
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            stale_lease = repository.acquire_lease(run_id, worker_id="worker-old")
            work.connection.execute(
                "UPDATE omnix_agent_worker_leases SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second' "
                "WHERE workspace_id = %s AND run_id = %s",
                (context.workspace_id, run_id),
            )
            current_lease = repository.acquire_lease(run_id, worker_id="worker-new")
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            with pytest.raises(AgentLeaseConflict):
                repository.update_state(
                    run_id,
                    expected_revision=revision,
                    status="running",
                    worker_id=stale_lease.worker_id,
                    lease_token=stale_lease.lease_token,
                )
            work.rollback()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            updated = repository.update_state(
                run_id,
                expected_revision=revision,
                status="running",
                worker_id=current_lease.worker_id,
                lease_token=current_lease.lease_token,
            )
            work.commit()
        assert updated.status == "running"
    finally:
        database.close()


def test_concurrent_command_claim_has_single_winner() -> None:
    database = _database()
    try:
        context, run_id, _ = _create_run(database)
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            command = repository.enqueue_command(
                AgentRunCommand(
                    run_id=run_id,
                    command_type="cancel",
                    idempotency_key="claim-once",
                )
            )
            work.commit()

        def claim(_index: int) -> bool:
            with unit_of_work(database) as work:
                repository = PostgresAgentRunRepository(work.connection, context)
                won = repository.claim_command(run_id, command.command_id)
                work.commit()
                return won

        with ThreadPoolExecutor(max_workers=5) as pool:
            outcomes = list(pool.map(claim, range(5)))

        assert outcomes.count(True) == 1
        assert outcomes.count(False) == 4
    finally:
        database.close()


def test_concurrent_event_writers_get_unique_monotonic_sequences() -> None:
    database = _database()
    try:
        context, run_id, _ = _create_run(database)

        def append(index: int) -> int:
            with unit_of_work(database) as work:
                repository = PostgresAgentRunRepository(work.connection, context)
                stored = repository.append_event(
                    AgentEvent(
                        run_id=run_id,
                        event_type="model.message",
                        payload={"writer": index},
                    )
                )
                work.commit()
                assert stored.sequence is not None
                return stored.sequence

        with ThreadPoolExecutor(max_workers=8) as pool:
            sequences = list(pool.map(append, range(16)))

        assert len(sequences) == len(set(sequences))
        assert sorted(sequences) == list(range(min(sequences), max(sequences) + 1))
    finally:
        database.close()


def test_processing_command_can_be_recovered_after_worker_death() -> None:
    database = _database()
    try:
        context, run_id, _ = _create_run(database)
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            command = repository.enqueue_command(
                AgentRunCommand(
                    run_id=run_id,
                    command_type="pause",
                    idempotency_key="recover-processing",
                )
            )
            assert repository.claim_command(run_id, command.command_id) is True
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.reset_processing_commands(run_id)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            assert repository.claim_command(run_id, command.command_id) is True
            repository.complete_command(run_id, command.command_id)
            work.commit()

        with unit_of_work(database) as work:
            row = work.connection.execute(
                """
                SELECT status
                  FROM omnix_agent_run_commands
                 WHERE workspace_id = %s AND run_id = %s AND command_id = %s
                """,
                (context.workspace_id, run_id, command.command_id),
            ).fetchone()
            work.rollback()
        assert row[0] == "consumed"
    finally:
        database.close()


def test_consumed_idempotency_key_cannot_execute_again() -> None:
    database = _database()
    try:
        context, run_id, _ = _create_run(database)
        original = AgentRunCommand(
            run_id=run_id,
            command_type="cancel",
            idempotency_key="network-retry",
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            stored, status = repository.enqueue_command_with_status(original)
            assert status == "pending"
            assert repository.claim_command(run_id, stored.command_id) is True
            repository.complete_command(run_id, stored.command_id)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            replay, status = repository.enqueue_command_with_status(
                original.model_copy(update={"command_id": "retry-command-id"})
            )
            assert replay.command_id == stored.command_id
            assert status == "consumed"
            assert repository.claim_command(run_id, replay.command_id) is False
            work.rollback()
    finally:
        database.close()


@pytest.mark.postgres
@pytest.mark.multiprocess
def test_agent_run_start_steer_approve_complete_across_processes() -> None:
    from app.platform.agent_runtime.service import AgentRunService
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.persistence.runtime import ensure_postgresql_runtime_ready

    database = _database()
    process = None
    control = None
    context = None
    run_id = f"agent-multiprocess:{uuid.uuid4().hex}"
    try:
        ensure_postgresql_runtime_ready(database)
        context = ensure_local_identity(database)
        jobs = PostgresJobStoreAdapter(database, context=context)
        api_service = AgentRunService(
            database,
            context=context,
            job_store=jobs,
            worker_id=f"agent-api:{uuid.uuid4().hex}",
        )
        api_service.runtime = SimpleNamespace(get_status=lambda _run_id: None)

        def compile_steering(current, command, **_kwargs):
            # The durable start already recorded the initial task revision.
            with unit_of_work(database) as work:
                latest = PostgresAgentRunRepository(work.connection, context).latest_task_revision(current.run_id)
                work.rollback()
            return {
                "revision": TaskRevision(
                    run_id=current.run_id,
                    sequence=(latest.sequence if latest is not None else 0) + 1,
                    source_command_id=command.command_id,
                    user_instruction=str(command.payload.get("message") or "steer"),
                    effective_objective="Cross-process lifecycle steering",
                ),
                "superseding_spec": None,
            }

        api_service._compile_steering = compile_steering
        spec = AgentRunSpec(
            run_id=run_id,
            task="Cross-process lifecycle test",
            profile="research",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        queued = api_service.submit_start(spec, job_store=jobs)
        assert queued.status == "queued"

        process_context = multiprocessing.get_context("spawn")
        parent, child = process_context.Pipe()
        process = process_context.Process(
            target=_agent_run_owner_process,
            args=(
                database.settings.url,
                (context.user_id, context.workspace_id, context.membership_id, tuple(context.roles)),
                child,
            ),
        )
        process.start()
        child.close()
        control = parent
        _receive_agent_owner(control, "ready")

        control.send({"action": "start", "run_id": run_id})
        assert _receive_agent_owner(control, "started")["status"] == "running"

        approval = AgentApproval(
            approval_id=f"approval:{uuid.uuid4().hex}",
            run_id=run_id,
            capability_id="browser.navigate",
            request_payload={"url": "https://example.invalid"},
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.add_approval(approval)
            work.commit()

        steer = AgentRunCommand(
            run_id=run_id,
            command_type="steer",
            payload={"message": "Keep the same task and inspect the result."},
            idempotency_key=f"steer:{run_id}",
        )
        approve = AgentRunCommand(
            run_id=run_id,
            command_type="approve",
            payload={"approval_id": approval.approval_id},
            idempotency_key=f"approve:{run_id}",
        )
        api_service.command(steer)
        api_service.command(approve)
        control.send({"action": "poll", "run_id": run_id})
        delivered = _receive_agent_owner(control, "delivered")
        # Supervisor and poll may interleave; each command is delivered exactly once.
        assert sorted(delivered["commands"]) == ["approve", "steer"]

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            resolved_approval = repository.get_approval(run_id, approval.approval_id)
            command_states = work.connection.execute(
                """
                SELECT command_type, status
                  FROM omnix_agent_run_commands
                 WHERE workspace_id = %s AND run_id = %s
                 ORDER BY created_at, command_id
                """,
                (context.workspace_id, run_id),
            ).fetchall()
            work.rollback()
        assert resolved_approval is not None and resolved_approval.state == "approved"
        assert sorted((row[0], row[1]) for row in command_states) == [
            ("approve", "consumed"),
            ("steer", "consumed"),
        ]

        control.send({"action": "complete", "run_id": run_id})
        assert _receive_agent_owner(control, "completed")["status"] == "completed"
        assert api_service.get(run_id).status == "completed"
    finally:
        if control is not None:
            try:
                control.send({"action": "stop", "run_id": run_id})
                if control.poll(2):
                    control.recv()
            except (BrokenPipeError, EOFError, OSError):
                pass
            control.close()
        if process is not None:
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)
        if context is not None:
            with unit_of_work(database) as work:
                work.connection.execute(
                    """
                    DELETE FROM omnix_jobs
                     WHERE workspace_id = %s AND module = 'agent-runtime'
                       AND input_payload ->> 'run_id' = %s
                    """,
                    (context.workspace_id, run_id),
                )
                work.connection.execute(
                    "DELETE FROM omnix_agent_runs WHERE workspace_id = %s AND run_id = %s",
                    (context.workspace_id, run_id),
                )
                work.commit()
        database.close()


def test_appending_an_event_does_not_wait_for_a_run_update() -> None:
    """Appends lock the run's counter row, not the run row (WP-7.4)."""
    database = _database()
    try:
        context, run_id, _ = _create_run(database)
        with unit_of_work(database) as work:
            previous = work.connection.execute(
                "SELECT MAX(sequence) FROM omnix_agent_run_events WHERE workspace_id = %s AND run_id = %s",
                (context.workspace_id, run_id),
            ).fetchone()[0] or 0
            work.rollback()
        with unit_of_work(database) as holder:
            # An uncommitted run update, as a status change holds while it runs.
            holder.connection.execute(
                "UPDATE omnix_agent_runs SET updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s AND run_id = %s",
                (context.workspace_id, run_id),
            )
            with unit_of_work(database) as work:
                work.connection.execute("SET LOCAL lock_timeout = '2s'")
                stored = PostgresAgentRunRepository(work.connection, context).append_event(
                    AgentEvent(run_id=run_id, event_type="model.message", payload={})
                )
                work.commit()
            holder.rollback()
        assert stored.sequence == previous + 1
    finally:
        database.close()


def test_the_event_counter_catches_up_with_events_written_without_it() -> None:
    database = _database()
    try:
        context, run_id, _ = _create_run(database)
        with unit_of_work(database) as work:
            # An event appended by code that predates the counter table.
            work.connection.execute(
                """
                INSERT INTO omnix_agent_run_events (workspace_id, run_id, sequence, event_id, event_type, payload)
                VALUES (%s, %s, 7, %s, 'model.message', '{}'::jsonb)
                """,
                (context.workspace_id, run_id, f"legacy-{uuid.uuid4().hex}"),
            )
            stored = PostgresAgentRunRepository(work.connection, context).append_event(
                AgentEvent(run_id=run_id, event_type="model.message", payload={})
            )
            following = PostgresAgentRunRepository(work.connection, context).append_event(
                AgentEvent(run_id=run_id, event_type="model.message", payload={})
            )
            work.commit()
        assert (stored.sequence, following.sequence) == (8, 9)
    finally:
        database.close()
