from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.assistant_memory_v2 import (
    Episode,
    MemorySpaceKey,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory_v2.episode_store import (
    EpisodeEvidenceError,
    PostgresMemoryV2EpisodeStore,
)
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
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
            pool_max=12,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-episode-tests",
        )
    )


def _space(prefix: str) -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=f"{prefix}-{uuid4().hex}",
    )


def _append(store: PostgresMemoryV2ObservationStore, space: MemorySpaceKey, index: int):
    return store.append(
        ObservationAppendRequest(
            space=space,
            visibility_scope=VisibilityScope(kind="global", scope_id="global"),
            event_type="user_said",
            occurred_at=datetime(2026, 9, 13, 12, index, tzinfo=timezone.utc),
            provenance=ObservationProvenance(
                source_type="user",
                source_id="user:alice",
                trust_level="user_explicit",
            ),
            idempotency_key=f"{space.owner_id}:{index}",
            payload={"text": f"turn {index}"},
        )
    )


def _episode(space: MemorySpaceKey, observation_ids: tuple[str, ...], *, episode_id: str = "ep:1") -> Episode:
    return Episode(
        episode_id=episode_id,
        space=space,
        visibility_scopes=(VisibilityScope(kind="global", scope_id="global"),),
        title="Planning Omnix memory",
        summary="Alice and the character discussed the Memory v2 design.",
        started_at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
        participant_entity_ids=("user:alice", space.owner_id),
        observation_ids=observation_ids,
        importance=0.8,
        derivation_version="phase5-test@1",
    )


def test_episode_roundtrip_preserves_observation_membership() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        episodes = PostgresMemoryV2EpisodeStore(database)
        space = _space("roundtrip")
        first = _append(observations, space, 1)
        second = _append(observations, space, 2)

        stored = episodes.put(_episode(space, (first.observation_id, second.observation_id)))
        assert stored.observation_ids == tuple(sorted((first.observation_id, second.observation_id)))
        assert stored.space == space
        assert episodes.get(space, stored.episode_id) == stored
        assert [item.episode_id for item in episodes.list(space)] == [stored.episode_id]
    finally:
        database.close()


def test_episode_rejects_cross_space_observation_evidence() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        episodes = PostgresMemoryV2EpisodeStore(database)
        sofia = _space("sofia")
        maya = _space("maya")
        foreign = _append(observations, maya, 1)
        _append(observations, sofia, 1)

        with pytest.raises(EpisodeEvidenceError, match="not found"):
            episodes.put(_episode(sofia, (foreign.observation_id,)))
    finally:
        database.close()


def test_episode_rejects_revoked_observation() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        episodes = PostgresMemoryV2EpisodeStore(database)
        space = _space("revoked")
        observation = _append(observations, space, 1)
        observations.set_disposition(
            space,
            observation.observation_id,
            state="revoked",
            actor_id="privacy:alice",
        )

        with pytest.raises(EpisodeEvidenceError, match="inactive"):
            episodes.put(_episode(space, (observation.observation_id,)))
    finally:
        database.close()


def test_episode_update_replaces_membership_and_revision() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        episodes = PostgresMemoryV2EpisodeStore(database)
        space = _space("update")
        first = _append(observations, space, 1)
        second = _append(observations, space, 2)
        initial = episodes.put(_episode(space, (first.observation_id,), episode_id="ep:update"))
        updated = episodes.put(
            initial.model_copy(
                update={
                    "observation_ids": (second.observation_id,),
                    "summary": "Updated episode summary.",
                    "revision": 2,
                }
            )
        )

        assert updated.revision == 2
        assert updated.observation_ids == (second.observation_id,)
        assert updated.summary == "Updated episode summary."
    finally:
        database.close()


def test_episode_lists_are_character_isolated() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        episodes = PostgresMemoryV2EpisodeStore(database)
        sofia = _space("sofia-isolated")
        maya = _space("maya-isolated")
        sofia_observation = _append(observations, sofia, 1)
        maya_observation = _append(observations, maya, 1)
        episodes.put(_episode(sofia, (sofia_observation.observation_id,), episode_id="ep:sofia"))
        episodes.put(_episode(maya, (maya_observation.observation_id,), episode_id="ep:maya"))

        assert [item.episode_id for item in episodes.list(sofia)] == ["ep:sofia"]
        assert [item.episode_id for item in episodes.list(maya)] == ["ep:maya"]
    finally:
        database.close()
