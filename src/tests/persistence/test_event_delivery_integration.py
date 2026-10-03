"""Commit-safe job event delivery (WP-5.4 acceptance)."""
from __future__ import annotations

import asyncio
import os
import time
import uuid

import psycopg
import pytest

from app.events.event_reader import EventCursor, EventReader, event_cursor
from app.gateway.kernel_routes.live_event_stream import committed_event_stream
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def setup():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    job_id = f"job:events:{uuid.uuid4().hex}"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute(
            "INSERT INTO omnix_jobs (id, workspace_id, module, job_type, resource_class) VALUES (%s, %s, 'test', 'events', 'cpu')",
            (job_id, tenant.workspace_id),
        )
    try:
        yield database, tenant, job_id
    finally:
        database.close()


def _insert(connection, tenant, job_id: str, label: str) -> None:
    connection.execute(
        "INSERT INTO omnix_job_events (workspace_id, job_id, event_type, payload) VALUES (%s, %s, 'probe', %s::jsonb)",
        (tenant.workspace_id, job_id, f'{{"label": "{label}"}}'),
    )


def _labels(events, job_id: str) -> list[str]:
    return [event["payload"]["label"] for event in events if event["job_id"] == job_id]


def _wait_for(reader: EventReader, after: EventCursor, job_id: str, *, count: int) -> list:
    """The reader never passes a transaction in progress anywhere in the cluster
    (other tests' included), so delivery can lag the commit briefly."""
    deadline = time.monotonic() + 15
    while True:
        delivered = reader.events_after(after)
        if len(_labels(delivered, job_id)) >= count or time.monotonic() > deadline:
            return delivered
        time.sleep(0.1)


def test_a_lower_id_that_commits_late_is_delivered_in_order_exactly_once(setup) -> None:
    database, tenant, job_id = setup
    reader = EventReader(database, tenant)
    start = reader.latest_cursor()
    first = psycopg.connect(admin_database_url())
    second = psycopg.connect(admin_database_url())
    try:
        _insert(first, tenant, job_id, "first")     # lower id, transaction still open
        _insert(second, tenant, job_id, "second")   # higher id
        second.commit()
        # An id cursor would deliver "second" now and later skip "first".
        assert _labels(reader.events_after(start), job_id) == []
        first.commit()
        delivered = _wait_for(reader, start, job_id, count=2)
        assert _labels(delivered, job_id) == ["first", "second"]
        assert _labels(reader.events_after(event_cursor(delivered[-1])), job_id) == []
    finally:
        first.close()
        second.close()


def test_reconnecting_with_a_cursor_resumes_without_duplicates(setup) -> None:
    database, tenant, job_id = setup
    reader = EventReader(database, tenant)
    start = reader.latest_cursor()
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        for label in ("a", "b", "c"):
            _insert(admin, tenant, job_id, label)

    async def collect(after: EventCursor, count: int) -> list[str]:
        # The stream waits until the events are deliverable (a transaction
        # still open elsewhere can hold them back), so no polling is needed.
        received: list[str] = []
        stream = committed_event_stream(reader, after)
        async for chunk in stream:
            if chunk.startswith("id:") and job_id in chunk:
                received.append(chunk)
            if len(received) == count:
                await stream.aclose()
                break
        return received

    try:
        first_connection = asyncio.run(asyncio.wait_for(collect(start, 3), timeout=30))
        cursors = [chunk.splitlines()[0].removeprefix("id: ") for chunk in first_connection]
        resumed = asyncio.run(asyncio.wait_for(collect(EventCursor.parse(cursors[0]), 2), timeout=30))
    finally:
        reader.stop()
    assert [chunk.splitlines()[0] for chunk in resumed] == [f"id: {cursor}" for cursor in cursors[1:]]
    assert '"label": "b"' in resumed[0] and '"label": "c"' in resumed[1]


def test_legacy_integer_cursors_restart_conservatively() -> None:
    assert EventCursor.parse("12") == EventCursor(0, 12)
    assert EventCursor.parse("7:12") == EventCursor(7, 12)
    assert EventCursor.parse("garbage") is None
    # A conservative restart may repeat events, never skip them.
    assert EventCursor(0, 12) < EventCursor(1, 3)
