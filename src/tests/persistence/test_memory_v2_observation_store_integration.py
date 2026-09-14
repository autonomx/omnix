from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone

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
            lock_timeout_ms=60_000,
            application_name="omnix-memory-v2-observation-tests",
        )
    )


def _request(
    *,
    space: MemorySpaceKey,
    observation_id: str,
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


def _space(owner_id: str = "sofia") -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=owner_id,
    )


def test_concurrent_writers_allocate_exactly_one_monotonic_sequence() -> None:
    database = _database()
    apply_migrations(database)
    store = PostgresMemoryV2ObservationStore(database)
    space = _space()
    store.delete_space_for_testing(space)

    total = 10_016

    def append(index: int) -> int:
        observation = store.append(
            _request(
                space=space,
                observation_id=f"obs:{index}",
                idempotency_key=f"idem:{index}",
                text=f"event {index}",
            )
        )
        return observation.authority_sequence

    with ThreadPoolExecutor(max_workers=32) as executor:
        sequences = list(executor.map(append, range(total)))

    assert sorted(sequences) == list(range(1, total + 1))
    assert store.observation_watermark(space) == total
    stored = store.list_active(space)
    assert [item.authority_sequence for item in stored] == list(range(1, total + 1))


def test_racing_duplicate_idempotency_key_resolves_to_one_observation() -> None:
    database = _database()
    apply_migrations(database)
    store = PostgresMemoryV2ObservationStore(database)
    space = _space("maya")
    store.delete_space_for_testing(space)
    request = _request(
        space=space,
        observation_id="obs:retry",
        idempotency_key="idem:retry",
        text="same request",
    )

    with ThreadPoolExecutor(max_workers=32) as executor:
        observations = list(executor.map(lambda _: store.append(request), range(128)))

    assert {item.observation_id for item in observations} == {"obs:retry"}
    assert {item.authority_sequence for item in observations} == {1}
    assert store.observation_watermark(space) == 1
    assert len(store.list_active(space)) == 1


def test_idempotency_key_rejects_changed_content() -> None:
    database = _database()
    apply_migrations(database)
    store = PostgresMemoryV2ObservationStore(database)
    space = _space("conflict")
    store.delete_space_for_testing(space)
    original = _request(
        space=space,
        observation_id="obs:one",
        idempotency_key="idem:one",
        text="first",
    )
    store.append(original)

    with pytest.raises(ObservationIdempotencyConflict):
        store.append(replace(original, observation_id="obs:two", payload={"text": "changed"}))

    assert store.observation_watermark(space) == 1


def test_failed_append_does_not_advance_watermark() -> None:
    database = _database()
    apply_migrations(database)
    store = PostgresMemoryV2ObservationStore(database)
    space = _space("rollback")
    store.delete_space_for_testing(space)
    request = _request(
        space=space,
        observation_id="obs:rollback",
        idempotency_key="idem:rollback",
        text="rollback",
    )

    with pytest.raises(RuntimeError, match="injected append failure"):
        store.append(request, fail_before_commit=True)

    assert store.observation_watermark(space) == 0
    assert store.list_active(space) == []
    committed = store.append(request)
    assert committed.authority_sequence == 1


def test_authority_streams_are_independent_per_memory_space() -> None:
    database = _database()
    apply_migrations(database)
    store = PostgresMemoryV2ObservationStore(database)
    sofia = _space("sofia-independent")
    maya = _space("maya-independent")
    store.delete_space_for_testing(sofia)
    store.delete_space_for_testing(maya)

    for index in range(3):
        store.append(
            _request(
                space=sofia,
                observation_id=f"sofia:{index}",
                idempotency_key=f"sofia:{index}",
                text="sofia",
            )
        )
        store.append(
            _request(
                space=maya,
                observation_id=f"maya:{index}",
                idempotency_key=f"maya:{index}",
                text="maya",
            )
        )

    assert [item.authority_sequence for item in store.list_active(sofia)] == [1, 2, 3]
    assert [item.authority_sequence for item in store.list_active(maya)] == [1, 2, 3]


def test_visibility_and_governance_disposition_filter_reads() -> None:
    database = _database()
    apply_migrations(database)
    store = PostgresMemoryV2ObservationStore(database)
    space = _space("governance")
    store.delete_space_for_testing(space)
    global_observation = store.append(
        _request(
            space=space,
            observation_id="obs:global",
            idempotency_key="idem:global",
            text="global",
        )
    )
    project_request = replace(
        _request(
            space=space,
            observation_id="obs:project",
            idempotency_key="idem:project",
            text="project",
        ),
        visibility_scope=VisibilityScope(kind="project", scope_id="project:omnix"),
    )
    project_observation = store.append(project_request)

    visible = store.list_active(
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

    disposition = store.set_disposition(
        space,
        observation_id=project_observation.observation_id,
        state="revoked",
        actor_id="privacy:alice",
        reason="user requested removal",
    )
    assert disposition.state == "revoked"
    assert [item.observation_id for item in store.list_active(space)] == [
        global_observation.observation_id
    ]

    purged = store.set_disposition(
        space,
        observation_id=project_observation.observation_id,
        state="purged",
        actor_id="privacy:alice",
        reason="hard deletion",
    )
    assert purged.state == "purged"
    assert store.observation_watermark(space) == 2
