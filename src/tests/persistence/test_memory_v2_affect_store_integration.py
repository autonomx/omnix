from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.assistant_memory_v2 import (
    AffectObservation,
    MemorySpaceKey,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory_v2.affect_store import (
    AffectEvidenceError,
    PostgresMemoryV2AffectStore,
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
            application_name="omnix-memory-v2-affect-tests",
        )
    )


def _space(prefix: str) -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=f"{prefix}-{uuid4().hex}",
    )


def _append(store: PostgresMemoryV2ObservationStore, space: MemorySpaceKey, index: int, at: datetime):
    return store.append(
        ObservationAppendRequest(
            space=space,
            visibility_scope=VisibilityScope(kind="global", scope_id="global"),
            event_type="acoustic_observation",
            occurred_at=at,
            provenance=ObservationProvenance(
                source_type="acoustic",
                source_id="stt:turn",
                trust_level="assistant_inference",
            ),
            idempotency_key=f"{space.owner_id}:{index}",
            payload={"signal": "affect"},
        )
    )


def _affect(
    space: MemorySpaceKey,
    source_observation_id: str,
    at: datetime,
    *,
    affect_id: str | None = None,
):
    return AffectObservation(
        affect_id=affect_id or f"affect:{space.owner_id}:{source_observation_id}",
        space=space,
        source_observation_id=source_observation_id,
        source="acoustic",
        observed_at=at,
        valence=0.25,
        arousal=0.7,
        emotion_distribution={"engaged": 0.75, "neutral": 0.25},
        confidence=0.8,
        model_version="phase7-test@1",
    )


def test_affect_roundtrip_and_fresh_current_turn_lookup() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        affects = PostgresMemoryV2AffectStore(database)
        space = _space("fresh")
        at = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
        source = _append(observations, space, 1, at)
        stored = affects.put(_affect(space, source.observation_id, at))

        assert affects.get(space, stored.affect_id) == stored
        assert affects.current(
            space,
            as_of=at + timedelta(seconds=2),
            freshness_seconds=5,
            source_observation_id=source.observation_id,
        ) == stored
    finally:
        database.close()


def test_stale_affect_is_history_but_not_current_state() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        affects = PostgresMemoryV2AffectStore(database)
        space = _space("stale")
        at = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
        source = _append(observations, space, 1, at)
        affects.put(_affect(space, source.observation_id, at))

        assert affects.current(space, as_of=at + timedelta(seconds=30), freshness_seconds=5) is None
        assert len(affects.history(space)) == 1
    finally:
        database.close()


def test_current_turn_guard_rejects_prior_turn_affect() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        affects = PostgresMemoryV2AffectStore(database)
        space = _space("turn-guard")
        at = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
        previous = _append(observations, space, 1, at)
        current = _append(observations, space, 2, at + timedelta(seconds=1))
        affects.put(_affect(space, previous.observation_id, at))

        assert affects.current(
            space,
            as_of=at + timedelta(seconds=2),
            freshness_seconds=10,
            source_observation_id=current.observation_id,
        ) is None
    finally:
        database.close()


def test_revoked_source_is_rejected_and_existing_affect_stops_being_current() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        affects = PostgresMemoryV2AffectStore(database)
        space = _space("revoked")
        at = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
        source = _append(observations, space, 1, at)
        stored = affects.put(_affect(space, source.observation_id, at))
        observations.set_disposition(
            space,
            source.observation_id,
            state="revoked",
            actor_id="privacy:alice",
        )

        assert affects.current(space, as_of=at + timedelta(seconds=1), freshness_seconds=10) is None
        with pytest.raises(AffectEvidenceError, match="inactive"):
            affects.put(stored.model_copy(update={"affect_id": "affect:retry"}))
    finally:
        database.close()


def test_affect_source_cannot_cross_character_space() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        affects = PostgresMemoryV2AffectStore(database)
        sofia = _space("sofia")
        maya = _space("maya")
        at = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
        foreign = _append(observations, maya, 1, at)
        _append(observations, sofia, 1, at)

        with pytest.raises(AffectEvidenceError, match="not found"):
            affects.put(_affect(sofia, foreign.observation_id, at))
    finally:
        database.close()
