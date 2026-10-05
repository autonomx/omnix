from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

import pytest

from app.rpg.declarations import RETENTION
from app.rpg.persistence.narration_event_repository import (
    MAX_RPG_NARRATION_EVENT_BYTES,
    MAX_RPG_NARRATION_EVENT_PAGE_SIZE,
    MAX_RPG_NARRATION_EVENTS_PER_SESSION,
    PostgresRpgNarrationEventRepository,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations


class _Cursor:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=()):
        normalized = " ".join(statement.split())
        self.calls.append((normalized, params))
        if "RETURNING event_id" in normalized:
            return _Cursor(row=(42,))
        if "COALESCE(MAX(event_id)" in normalized:
            return _Cursor(row=(42,))
        if "SELECT event_id, payload" in normalized:
            return _Cursor(rows=[(43, {"type": "narration_job", "status": "completed"})])
        return _Cursor(rowcount=3)


def test_append_bounds_payload_and_keeps_only_recent_session_events():
    connection = _Connection()
    repository = PostgresRpgNarrationEventRepository(connection)

    assert repository.append("session-1", {"type": "narration_job"}) == 42
    assert "INSERT INTO omnix_rpg_narration_events" in connection.calls[0][0]
    assert connection.calls[0][1][0] == "session-1"
    assert json.loads(connection.calls[0][1][1]) == {"type": "narration_job"}
    assert connection.calls[1][1] == ("session-1", MAX_RPG_NARRATION_EVENTS_PER_SESSION)

    oversized = {"payload": "x" * MAX_RPG_NARRATION_EVENT_BYTES}
    with pytest.raises(ValueError, match="storage limit"):
        repository.append("session-1", oversized)


def test_event_cursor_and_page_are_scoped_to_session_and_page_size_is_bounded():
    connection = _Connection()
    repository = PostgresRpgNarrationEventRepository(connection)

    assert repository.latest_event_id("session-1") == 42
    assert repository.list_after("session-1", 42, limit=MAX_RPG_NARRATION_EVENT_PAGE_SIZE + 10) == [
        (43, {"type": "narration_job", "status": "completed"})
    ]
    assert connection.calls[-1][1] == (
        "session-1",
        42,
        MAX_RPG_NARRATION_EVENT_PAGE_SIZE,
    )
    assert "created_at >= CURRENT_TIMESTAMP - INTERVAL '1 day'" in connection.calls[-1][0]


def test_retention_deletes_oldest_events_in_bounded_batches():
    connection = _Connection()
    (declaration,) = RETENTION

    assert declaration.record_type == "rpg_narration_events" and declaration.capacity_cleanup
    assert declaration.delete(connection, 1, 250) == 3
    assert "ORDER BY created_at, event_id" in connection.calls[0][0]
    assert connection.calls[0][1] == (1, 250)


def test_migration_installs_durable_feed_and_lifecycle_retention():
    migration = Path("src/app/persistence/migrations/0104_rpg_narration_events.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS omnix_rpg_narration_events" in migration
    assert "idx_omnix_rpg_narration_events_session_id" in migration
    assert "('rpg_narration_events', 1, FALSE)" in migration


@pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_event_published_through_one_connection_is_read_through_another():
    database_settings = DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"],
        pool_min=1,
        pool_max=1,
        connect_timeout_seconds=10,
        statement_timeout_ms=30_000,
        application_name="omnix-rpg-narration-events-tests",
    )
    database = PostgresDatabase(database_settings)
    reader_database = PostgresDatabase(database_settings)
    session_id = f"narration-test-{uuid.uuid4().hex}"
    event_id = None
    try:
        apply_migrations(database)
        with database.transaction() as writer:
            event_id = PostgresRpgNarrationEventRepository(writer).append(
                session_id,
                {"type": "narration_job", "status": "completed"},
            )
        with reader_database.transaction() as reader:
            events = PostgresRpgNarrationEventRepository(reader).list_after(session_id, 0)
        assert events == [(event_id, {"type": "narration_job", "status": "completed"})]
    finally:
        try:
            if event_id is not None:
                with database.transaction() as cleanup:
                    cleanup.execute(
                        "DELETE FROM omnix_rpg_narration_events WHERE session_id = %s",
                        (session_id,),
                    )
        finally:
            database.close()
            reader_database.close()
