from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.assistant_memory_v2 import MemorySpaceKey, ObservationProvenance, VisibilityScope
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
    ObservationIdempotencyConflict,
    PostgresMemoryV2ObservationStore,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=40,
            connect_timeout_seconds=10,
            statement_timeout_ms=120_000,
            lock_timeout_ms=120_000,
            application_name="omnix-memory-v2-observation-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_memory_v2_observation_dispositions, "
            "omnix_memory_v2_observations, omnix_memory_v2_authority_streams CASCADE"
        )


def _space(owner_id: str = "sofia") -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=owner_id,
    )


def _request(index: int, *, space: MemorySpaceKey | None = None) -> ObservationAppendRequest:
    return ObservationAppendRequest(
        space=space or _space(),
        visibility_scope=VisibilityScope(kind="global", scope_id="global"),
        event_type="user_said",
        occurred_at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
        provenance=ObservationProvenance(
            source_type="user",
            source_id="user:alice",
            trust_level="user_explicit",
        ),
        idempotency_key=f"turn:{index}",
        payload={"text": f"message-{index}"},
    )


def test_database_serializes_10000_concurrent_same_space_appends() -> None:
    database = _database()
    try:
        _reset(database)
        store = PostgresMemoryV2ObservationStore(database)
        total = 10_016
        with ThreadPoolExecutor(max_workers=32) as executor:
            observations = list(executor.map(lambda index: store.append(_request(index)), range(total)))

        sequences = sorted(item.authority_sequence for item in observations)
        assert sequences == list(range(1, total + 1))
        assert len({item.observation_id for item in observations}) == total
        assert len({item.idempotency_key for item in observations}) == total
        assert store.watermark(_space()) == total
        replay = store.list(_space(), limit=100_000)
        assert [item.authority_sequence for item in replay] == list(range(1, total + 1))
    finally:
        database.close()


def test_concurrent_idempotent_retries_resolve_to_one_committed_observation() -> None:
    database = _database()
    try:
        _reset(database)
        store = PostgresMemoryV2ObservationStore(database)
        request = _request(1)
        with ThreadPoolExecutor(max_workers=32) as executor:
            results = list(executor.map(lambda _: store.append(request), range(128)))

        assert len({item.observation_id for item in results}) == 1
        assert {item.authority_sequence for item in results} == {1}
        assert store.watermark(_space()) == 1
        assert len(store.list(_space())) == 1
    finally:
        database.close()


def test_idempotency_key_rejects_different_content() -> None:
    database = _database()
    try:
        _reset(database)
        store = PostgresMemoryV2ObservationStore(database)
        first = _request(1)
        store.append(first)
        conflicting = replace(first, payload={"text": "different"})
        with pytest.raises(ObservationIdempotencyConflict):
            store.append(conflicting)
        assert store.watermark(_space()) == 1
    finally:
        database.close()


def test_contract_failure_rolls_back_sequence_and_watermark() -> None:
    database = _database()
    try:
        _reset(database)
        store = PostgresMemoryV2ObservationStore(database)
        invalid = ObservationAppendRequest(
            space=_space(),
            visibility_scope=VisibilityScope(kind="global", scope_id="global"),
            event_type="user_said",
            occurred_at=datetime.now(timezone.utc),
            provenance=ObservationProvenance(
                source_type="assistant",
                source_id="assistant:test",
                trust_level="assistant_inference",
            ),
            idempotency_key="invalid-provenance",
            payload={"text": "must rollback"},
        )
        with pytest.raises(ValueError, match="provenance"):
            store.append(invalid)
        assert store.watermark(_space()) == 0
        assert store.list(_space()) == []

        committed = store.append(_request(2))
        assert committed.authority_sequence == 1
        assert store.watermark(_space()) == 1
    finally:
        database.close()


def test_different_memory_spaces_have_independent_authority_streams() -> None:
    database = _database()
    try:
        _reset(database)
        store = PostgresMemoryV2ObservationStore(database)
        sofia = _space("sofia")
        maya = _space("maya")
        work = [
            _request(index, space=sofia if index % 2 == 0 else maya)
            for index in range(256)
        ]
        with ThreadPoolExecutor(max_workers=32) as executor:
            list(executor.map(store.append, work))

        assert store.watermark(sofia) == 128
        assert store.watermark(maya) == 128
        assert [item.authority_sequence for item in store.list(sofia)] == list(range(1, 129))
        assert [item.authority_sequence for item in store.list(maya)] == list(range(1, 129))
    finally:
        database.close()


def test_visibility_and_governance_overlay_are_enforced() -> None:
    database = _database()
    try:
        _reset(database)
        store = PostgresMemoryV2ObservationStore(database)
        global_observation = store.append(_request(1))
        project_request = replace(
            _request(2),
            visibility_scope=VisibilityScope(kind="project", scope_id="project:omnix"),
        )
        project_observation = store.append(project_request)

        visible = store.list(
            _space(),
            visible_scopes=(VisibilityScope(kind="project", scope_id="project:omnix"),),
        )
        assert [item.observation_id for item in visible] == [project_observation.observation_id]

        store.set_disposition(
            _space(), global_observation.observation_id,
            state="revoked", actor_id="user:alice", reason="forget this",
        )
        assert [item.observation_id for item in store.list(_space())] == [project_observation.observation_id]
        assert len(store.list(_space(), include_inactive=True)) == 2

        store.set_disposition(
            _space(), project_observation.observation_id,
            state="purged", actor_id="user:alice", reason="privacy deletion",
        )
        purged = store.get(_space(), project_observation.observation_id)
        assert purged is not None
        assert purged.payload == {"purged": True}
        assert store.watermark(_space()) == 2
    finally:
        database.close()
