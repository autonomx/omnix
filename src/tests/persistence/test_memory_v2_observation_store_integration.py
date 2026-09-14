from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.assistant_memory_v2 import (
    MemorySpaceKey,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
    ObservationIdempotencyConflict,
    PostgresMemoryV2ObservationStore,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresConstraintError, PostgresDatabase
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
            lock_timeout_ms=60_000,
            application_name="omnix-memory-v2-observation-tests",
        )
    )


def _space(prefix: str) -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=f"{prefix}-{uuid4().hex}",
    )


def _request(
    *,
    space: MemorySpaceKey,
    observation_id: str | None,
    idempotency_key: str,
    text: str,
) -> ObservationAppendRequest:
    return ObservationAppendRequest(
        observation_id=observation_id,
        idempotency_key=idempotency_key,
        space=space,
        visibility_scope=VisibilityScope(kind="global", scope_id="global"),
        event_type="user_said",
        occurred_at=datetime.now(timezone.utc),
        payload={"text": text},
        provenance=ObservationProvenance(
            source_type="user",
            source_id=space.principal_id,
            trust_level="user_explicit",
        ),
    )


def test_concurrent_writers_allocate_exactly_one_monotonic_sequence() -> None:
    database = _database()
    try:
        apply_migrations(database)
        store = PostgresMemoryV2ObservationStore(database)
        space = _space("contention")
        total = 10_016

        def append(index: int) -> int:
            return store.append(
                _request(
                    space=space,
                    observation_id=f"obs:{space.owner_id}:{index}",
                    idempotency_key=f"idem:{index}",
                    text=f"event {index}",
                )
            ).authority_sequence

        with ThreadPoolExecutor(max_workers=32) as executor:
            sequences = list(executor.map(append, range(total)))

        assert sorted(sequences) == list(range(1, total + 1))
        assert store.watermark(space) == total
        stored = store.list(space, limit=20_000)
        assert [item.authority_sequence for item in stored] == list(range(1, total + 1))
    finally:
        database.close()


def test_racing_duplicate_idempotency_key_resolves_to_one_observation() -> None:
    database = _database()
    try:
        apply_migrations(database)
        store = PostgresMemoryV2ObservationStore(database)
        space = _space("retry")
        request = _request(
            space=space,
            observation_id=f"obs:{space.owner_id}:retry",
            idempotency_key="idem:retry",
            text="same request",
        )

        with ThreadPoolExecutor(max_workers=32) as executor:
            observations = list(executor.map(lambda _: store.append(request), range(128)))

        assert len({item.observation_id for item in observations}) == 1
        assert {item.authority_sequence for item in observations} == {1}
        assert store.watermark(space) == 1
        assert len(store.list(space)) == 1
    finally:
        database.close()


def test_idempotency_key_rejects_changed_content() -> None:
    database = _database()
    try:
        apply_migrations(database)
        store = PostgresMemoryV2ObservationStore(database)
        space = _space("conflict")
        original = _request(
            space=space,
            observation_id=f"obs:{space.owner_id}:one",
            idempotency_key="idem:one",
            text="first",
        )
        store.append(original)

        with pytest.raises(ObservationIdempotencyConflict):
            store.append(
                replace(
                    original,
                    observation_id=f"obs:{space.owner_id}:two",
                    payload={"text": "changed"},
                )
            )
        assert store.watermark(space) == 1
    finally:
        database.close()


def test_failed_insert_rolls_back_sequence_and_watermark() -> None:
    database = _database()
    try:
        apply_migrations(database)
        store = PostgresMemoryV2ObservationStore(database)
        source = _space("source")
        target = _space("rollback")
        shared_observation_id = f"obs:shared:{uuid4().hex}"
        store.append(
            _request(
                space=source,
                observation_id=shared_observation_id,
                idempotency_key="source",
                text="source",
            )
        )

        with pytest.raises(PostgresConstraintError):
            store.append(
                _request(
                    space=target,
                    observation_id=shared_observation_id,
                    idempotency_key="target-fails",
                    text="target",
                )
            )

        assert store.watermark(target) == 0
        committed = store.append(
            _request(
                space=target,
                observation_id=f"obs:{target.owner_id}:ok",
                idempotency_key="target-ok",
                text="committed",
            )
        )
        assert committed.authority_sequence == 1
        assert store.watermark(target) == 1
    finally:
        database.close()


def test_authority_streams_are_independent_per_memory_space() -> None:
    database = _database()
    try:
        apply_migrations(database)
        store = PostgresMemoryV2ObservationStore(database)
        sofia = _space("sofia")
        maya = _space("maya")

        for index in range(3):
            for space in (sofia, maya):
                store.append(
                    _request(
                        space=space,
                        observation_id=f"obs:{space.owner_id}:{index}",
                        idempotency_key=f"idem:{index}",
                        text=space.owner_id,
                    )
                )

        assert [item.authority_sequence for item in store.list(sofia)] == [1, 2, 3]
        assert [item.authority_sequence for item in store.list(maya)] == [1, 2, 3]
    finally:
        database.close()


def test_visibility_and_governance_disposition_filter_reads() -> None:
    database = _database()
    try:
        apply_migrations(database)
        store = PostgresMemoryV2ObservationStore(database)
        space = _space("governance")
        global_observation = store.append(
            _request(
                space=space,
                observation_id=f"obs:{space.owner_id}:global",
                idempotency_key="idem:global",
                text="global",
            )
        )
        project_request = replace(
            _request(
                space=space,
                observation_id=f"obs:{space.owner_id}:project",
                idempotency_key="idem:project",
                text="project",
            ),
            visibility_scope=VisibilityScope(kind="project", scope_id="project:omnix"),
        )
        project_observation = store.append(project_request)

        visible = store.list(
            space,
            visible_scopes=(
                VisibilityScope(kind="global", scope_id="global"),
                VisibilityScope(kind="project", scope_id="project:omnix"),
            ),
        )
        assert [item.observation_id for item in visible] == [
            global_observation.observation_id,
            project_observation.observation_id,
        ]

        assert store.set_disposition(
            space,
            project_observation.observation_id,
            state="revoked",
            actor_id="privacy:alice",
            reason="user requested removal",
        ).state == "revoked"
        assert [item.observation_id for item in store.list(space)] == [
            global_observation.observation_id
        ]

        assert store.set_disposition(
            space,
            project_observation.observation_id,
            state="purged",
            actor_id="privacy:alice",
            reason="hard deletion",
        ).state == "purged"
        assert store.watermark(space) == 2
    finally:
        database.close()
