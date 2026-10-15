"""The Memory v2 runtime's authoritative appends: sequence, idempotent retries, concurrency."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.platform.assistant_memory.v2 import MemorySpaceKey, ObservationProvenance, VisibilityScope
from app.platform.assistant_memory.v2.observation_store import ObservationAppendRequest
from app.platform.assistant_memory.v2.runtime import AuthoritativeIngestSequenceError, PostgresMemoryV2Runtime
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

T0 = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)
GLOBAL = VisibilityScope(kind="global", scope_id="profile:alice")


@pytest.fixture
def database():
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=12, connect_timeout_seconds=10,
        statement_timeout_ms=60_000, lock_timeout_ms=30_000, application_name="omnix-memory-v2-runtime-tests",
    ))
    apply_migrations(database)
    try:
        yield database
    finally:
        database.close()


def _request(space: MemorySpaceKey, *, suffix: str, text: str) -> ObservationAppendRequest:
    return ObservationAppendRequest(
        space=space,
        visibility_scope=GLOBAL,
        event_type="user_said",
        occurred_at=T0,
        provenance=ObservationProvenance(
            source_type="user",
            source_id="user:alice",
            trust_level="user_explicit",
            session_id="session:runtime",
            turn_id=f"turn:{suffix}",
            message_id=f"message:{suffix}",
        ),
        idempotency_key=f"runtime:{space.owner_id}:{suffix}",
        payload={"text": text},
    )


def _prepare(database: PostgresDatabase) -> tuple[PostgresMemoryV2Runtime, MemorySpaceKey]:
    runtime = PostgresMemoryV2Runtime(database)
    space = MemorySpaceKey(principal_id="profile:alice", owner_type="character", owner_id=f"sofia-{uuid4().hex}")
    first = runtime.append_authoritative_next(_request(space, suffix="1", text="Skyrim is my favorite game"))
    assert first.authority_sequence == 1
    return runtime, space


def _event_watermark(database: PostgresDatabase, space: MemorySpaceKey) -> int:
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT authoritative_event_watermark FROM omnix_memory_v2_authority_streams "
            "WHERE principal_id = %s AND owner_type = %s AND owner_id = %s",
            (space.principal_id, space.owner_type, space.owner_id),
        ).fetchone()
    return int(row[0]) if row is not None else 0


def test_exact_appends_enforce_the_sequence_and_retry_idempotently(database) -> None:
    runtime, space = _prepare(database)

    request = _request(space, suffix="2", text="Second event")
    committed = runtime.append_authoritative_exact(request, authoritative_event_sequence=2)
    repeated = runtime.append_authoritative(request, authoritative_event_sequence=2)

    assert committed.observation_id == repeated.observation_id
    assert committed.authority_sequence == 2
    assert runtime.observation_store.watermark(space) == 2
    assert _event_watermark(database, space) == 2
    with pytest.raises(AuthoritativeIngestSequenceError):
        runtime.append_authoritative_exact(
            _request(space, suffix="4", text="Skipped sequence"), authoritative_event_sequence=4,
        )


def test_next_allocates_the_sequence_and_a_retry_consumes_none(database) -> None:
    runtime, space = _prepare(database)

    request = _request(space, suffix="next", text="Next event")
    committed = runtime.append_authoritative_next(request)
    repeated = runtime.append_authoritative_next(request)

    assert committed.observation_id == repeated.observation_id
    assert committed.authority_sequence == 2
    assert _event_watermark(database, space) == 2
    third = runtime.append_authoritative_next(_request(space, suffix="third", text="Third event"))
    assert third.authority_sequence == 3


def test_next_serializes_concurrent_writers_without_race_retries(database) -> None:
    runtime, space = _prepare(database)
    requests = (
        _request(space, suffix="parallel-a", text="Parallel event A"),
        _request(space, suffix="parallel-b", text="Parallel event B"),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        committed = tuple(executor.map(runtime.append_authoritative_next, requests))

    assert {item.authority_sequence for item in committed} == {2, 3}
    assert len({item.observation_id for item in committed}) == 2
    assert runtime.observation_store.watermark(space) == 3
    assert _event_watermark(database, space) == 3
