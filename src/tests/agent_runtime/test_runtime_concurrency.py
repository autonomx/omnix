from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import uuid

import pytest

from app.agent_runtime.contracts import (
    AgentEvent,
    AgentRunCommand,
    AgentRunSpec,
    ModelRef,
)
from app.agent_runtime.repository import (
    AgentRunConcurrencyError,
    PostgresAgentRunRepository,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
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
    context = bootstrap_local_tenant(database)
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

        def update(worker: str) -> str:
            try:
                with unit_of_work(database) as work:
                    repository = PostgresAgentRunRepository(work.connection, context)
                    repository.update_state(
                        run_id,
                        expected_revision=revision,
                        status="running",
                        worker_id=worker,
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
