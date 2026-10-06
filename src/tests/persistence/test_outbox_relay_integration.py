"""Outbox relay delivery, dedup and retry (WP-5.3 acceptance)."""
from __future__ import annotations

import asyncio
import os
import uuid

import psycopg
import pytest

from app.events.outbox_relay import OutboxConsumer, OutboxConsumerRegistry, OutboxRelayWorker
from app.events.run_streams import RunEventWakeups, run_stream_consumer, wakeup_key
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.outbox_repository import PostgresOutboxRepository
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    # The relay claims every pending event; other outbox tests share the group.
    pytest.mark.xdist_group("outbox"),
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def setup():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    try:
        yield database, tenant
    finally:
        database.close()


def _append(database, tenant, aggregate_type: str) -> str:
    key = f"relay-test:{uuid.uuid4().hex}"
    with database.transaction() as connection:
        PostgresOutboxRepository(connection).append(
            tenant, aggregate_type=aggregate_type, aggregate_id=key, event_type="probe.created",
            payload={"probe": True}, event_key=key,
        )
    return key


def _status(key: str) -> str:
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        return str(admin.execute("SELECT status FROM omnix_outbox_events WHERE event_key = %s", (key,)).fetchone()[0])


def _make_due(key: str) -> None:
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute("UPDATE omnix_outbox_events SET available_at = CURRENT_TIMESTAMP WHERE event_key = %s", (key,))


def _consumer(name: str, aggregate_type: str, calls: list[str], *, fail_times: int = 0) -> OutboxConsumer:
    def handler(connection, event):
        if event["aggregate_type"] != aggregate_type:
            return None
        calls.append(event["event_key"])
        connection.execute("SELECT 1")
        if len(calls) <= fail_times:
            raise RuntimeError(f"{name} unavailable")
        return {"seen": event["event_key"]}

    return OutboxConsumer(consumer_name=name, aggregate_types=frozenset({aggregate_type}), handler=handler)


def test_each_consumer_runs_once_and_the_event_is_published(setup) -> None:
    database, tenant = setup
    kind = f"probe_{uuid.uuid4().hex[:8]}"
    first, second = [], []
    registry = OutboxConsumerRegistry([_consumer("probe-a", kind, first), _consumer("probe-b", kind, second)])
    key = _append(database, tenant, kind)

    report = OutboxRelayWorker(database, registry).run_once()

    assert first == [key] and second == [key]
    assert _status(key) == "published"
    assert report.deliveries["probe-a"] >= 1
    OutboxRelayWorker(database, registry).run_once()
    assert first == [key] and second == [key]


def test_a_failed_consumer_is_retried_without_repeating_the_others(setup) -> None:
    database, tenant = setup
    kind = f"probe_{uuid.uuid4().hex[:8]}"
    steady, flaky = [], []
    registry = OutboxConsumerRegistry([_consumer("probe-steady", kind, steady), _consumer("probe-flaky", kind, flaky, fail_times=1)])
    key = _append(database, tenant, kind)

    OutboxRelayWorker(database, registry).run_once()
    assert _status(key) == "retrying"
    _make_due(key)
    OutboxRelayWorker(database, registry).run_once()

    assert steady == [key]           # completed once, deduplicated on retry
    assert flaky == [key, key]       # failed, then delivered
    assert _status(key) == "published"


def test_a_consumer_that_keeps_failing_dead_letters_the_event(setup) -> None:
    database, tenant = setup
    kind = f"probe_{uuid.uuid4().hex[:8]}"
    calls: list[str] = []
    registry = OutboxConsumerRegistry([_consumer("probe-broken", kind, calls, fail_times=99)])
    key = _append(database, tenant, kind)
    relay = OutboxRelayWorker(database, registry, max_attempts=2)

    relay.run_once()
    _make_due(key)
    relay.run_once()

    assert _status(key) == "dead_letter"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        letter = admin.execute(
            "SELECT consumer_id, reason FROM omnix_outbox_dead_letters WHERE event_key = %s", (key,)
        ).fetchone()
    assert letter[0] == "probe-broken" and "unavailable" in letter[1]


def test_lag_reports_undelivered_events(setup) -> None:
    database, tenant = setup
    key = _append(database, tenant, f"probe_{uuid.uuid4().hex[:8]}")
    with database.transaction() as connection:
        lag = PostgresOutboxRepository(connection).lag(tenant)
    assert lag["unpublished"] >= 1 and lag["oldest_unpublished_age_seconds"] >= 0
    OutboxRelayWorker(database, OutboxConsumerRegistry()).run_once()
    assert _status(key) == "published"


def test_run_stream_consumer_wakes_the_runs_streams(setup) -> None:
    database, tenant = setup
    run_id = f"relay-test:{uuid.uuid4().hex}"
    wakeups = RunEventWakeups(os.environ["OMNIX_TEST_DATABASE_URL"])
    relay = OutboxRelayWorker(database, OutboxConsumerRegistry([run_stream_consumer()]))

    async def scenario() -> bool:
        with wakeups.subscribe(wakeup_key(tenant.workspace_id, "agent_run", run_id)) as subscription:
            await asyncio.sleep(1.5)  # the listener connects and runs LISTEN
            with database.transaction() as connection:
                PostgresOutboxRepository(connection).append(
                    tenant, aggregate_type="agent_run", aggregate_id=run_id,
                    event_type="run.started", payload={}, event_key=run_id,
                )
            await asyncio.to_thread(relay.run_once)
            return await subscription.wait(timeout=10)

    assert asyncio.run(scenario()) is True
    assert _status(run_id) == "published"
