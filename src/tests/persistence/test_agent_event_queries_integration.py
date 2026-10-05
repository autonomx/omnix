"""A run's whole event log is readable past 5,000 events (WP-7.4)."""
from __future__ import annotations

import os
import uuid

import pytest

from app.platform.agent_runtime import event_queries
from app.platform.agent_runtime.contracts import AgentRunSpec, ModelRef
from app.platform.agent_runtime.repository import PostgresAgentRunRepository
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.unit_of_work import unit_of_work

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

EVENTS = 20_000


@pytest.fixture
def long_run():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=2))
    context = ensure_local_identity(database)
    run_id = f"long-{uuid.uuid4().hex}"
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)
        repository.create_run(AgentRunSpec(run_id=run_id, task="long run", model=ModelRef(provider_id="test", model_id="m")))
        start = work.connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM omnix_agent_run_events WHERE workspace_id = %s AND run_id = %s",
            (context.workspace_id, run_id),
        ).fetchone()[0]
        # Mostly progress events; the evidence the run is judged by comes last,
        # far past the old 5,000-event window.
        work.connection.execute(
            """
            INSERT INTO omnix_agent_run_events (workspace_id, run_id, sequence, event_id, event_type, payload)
            SELECT %s, %s, %s + n, %s || n,
                   CASE WHEN n = %s THEN 'quality.stage'
                        WHEN n = %s THEN 'tool.started'
                        ELSE 'model.message' END,
                   CASE WHEN n = %s THEN '{"stage": "final-review"}'::jsonb
                        WHEN n = %s THEN '{"tool_call_id": "call-last", "tool": "omnix_change_set"}'::jsonb
                        ELSE '{"phase": "message_update"}'::jsonb END
              FROM generate_series(1, %s) AS n
            """,
            (
                context.workspace_id, run_id, start, f"{run_id}-",
                EVENTS - 1, EVENTS, EVENTS - 1, EVENTS, EVENTS,
            ),
        )
        work.commit()
    try:
        yield database, context, run_id, start
    finally:
        database.close()


def test_typed_reads_see_events_past_the_old_window(long_run) -> None:
    database, context, run_id, start = long_run
    with unit_of_work(database) as work:
        repository = PostgresAgentRunRepository(work.connection, context)

        stage = event_queries.latest_event(repository, run_id, "quality.stage")
        started = event_queries.latest_event(
            repository, run_id, "tool.started", payload_contains={"tool_call_id": "call-last"}
        )
        tools = event_queries.events_of_types(repository, run_id, {"tool.started"})
        everything = event_queries.all_events(repository, run_id)
        work.rollback()

    assert stage is not None and stage.payload["stage"] == "final-review"
    assert started is not None and started.sequence == start + EVENTS
    assert [event.sequence for event in tools] == [start + EVENTS]
    assert len(everything) == start + EVENTS
    assert [event.sequence for event in everything] == list(range(1, start + EVENTS + 1))
