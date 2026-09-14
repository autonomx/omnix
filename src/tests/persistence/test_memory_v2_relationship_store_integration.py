from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.assistant_memory_v2 import (
    GraphEntityRef,
    MemorySpaceKey,
    ObservationProvenance,
    RelationshipMetric,
    RelationshipState,
    VisibilityScope,
)
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
    PostgresMemoryV2ObservationStore,
)
from app.assistant_memory_v2.relationship_store import (
    PostgresMemoryV2RelationshipStore,
    RelationshipEvidenceError,
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
            application_name="omnix-memory-v2-relationship-tests",
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


def _relationship(space: MemorySpaceKey, observation_id: str, *, relationship_id: str = "rel:alice"):
    return RelationshipState(
        relationship_id=relationship_id,
        space=space,
        subject=GraphEntityRef(entity_id=space.owner_id, entity_type="character"),
        counterpart=GraphEntityRef(entity_id="user:alice", entity_type="user"),
        metrics=(
            RelationshipMetric(
                name="trust",
                value=0.8,
                confidence=0.9,
                evidence_observation_ids=(observation_id,),
            ),
            RelationshipMetric(
                name="familiarity",
                value=0.6,
                confidence=0.85,
                evidence_observation_ids=(observation_id,),
            ),
        ),
        prompt_interpretation="The character knows Alice well and should respond with established familiarity.",
        evidence_observation_ids=(observation_id,),
        derivation_version="phase6-test@1",
    )


def test_relationship_roundtrip_keeps_metrics_internal_and_interpretation_explicit() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        relationships = PostgresMemoryV2RelationshipStore(database)
        space = _space("roundtrip")
        observation = _append(observations, space, 1)

        stored = relationships.put(_relationship(space, observation.observation_id))
        assert stored.space == space
        assert {metric.name: metric.value for metric in stored.metrics} == {
            "familiarity": 0.6,
            "trust": 0.8,
        }
        assert "established familiarity" in stored.prompt_interpretation
        assert relationships.get(space, stored.relationship_id) == stored
    finally:
        database.close()


def test_relationship_rejects_cross_space_metric_evidence() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        relationships = PostgresMemoryV2RelationshipStore(database)
        sofia = _space("sofia")
        maya = _space("maya")
        _append(observations, sofia, 1)
        foreign = _append(observations, maya, 1)

        with pytest.raises(RelationshipEvidenceError, match="not found"):
            relationships.put(_relationship(sofia, foreign.observation_id))
    finally:
        database.close()


def test_relationship_rejects_revoked_evidence() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        relationships = PostgresMemoryV2RelationshipStore(database)
        space = _space("revoked")
        observation = _append(observations, space, 1)
        observations.set_disposition(
            space,
            observation.observation_id,
            state="revoked",
            actor_id="privacy:alice",
        )

        with pytest.raises(RelationshipEvidenceError, match="inactive"):
            relationships.put(_relationship(space, observation.observation_id))
    finally:
        database.close()


def test_relationship_update_replaces_metrics_and_can_archive() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        relationships = PostgresMemoryV2RelationshipStore(database)
        space = _space("archive")
        observation = _append(observations, space, 1)
        initial = relationships.put(_relationship(space, observation.observation_id, relationship_id="rel:update"))
        archived = relationships.put(
            initial.model_copy(
                update={
                    "metrics": (
                        RelationshipMetric(
                            name="trust",
                            value=0.5,
                            confidence=1.0,
                            evidence_observation_ids=(observation.observation_id,),
                        ),
                    ),
                    "prompt_interpretation": "Archived relationship state.",
                    "status": "archived",
                    "revision": 2,
                }
            )
        )

        assert archived.status == "archived"
        assert archived.revision == 2
        assert [metric.name for metric in archived.metrics] == ["trust"]
        assert relationships.list(space) == []
        assert [item.relationship_id for item in relationships.list(space, status=None)] == ["rel:update"]
    finally:
        database.close()


def test_relationships_are_character_isolated() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        relationships = PostgresMemoryV2RelationshipStore(database)
        sofia = _space("sofia-isolated")
        maya = _space("maya-isolated")
        sofia_observation = _append(observations, sofia, 1)
        maya_observation = _append(observations, maya, 1)
        relationships.put(_relationship(sofia, sofia_observation.observation_id, relationship_id="rel:sofia"))
        relationships.put(_relationship(maya, maya_observation.observation_id, relationship_id="rel:maya"))

        assert [item.relationship_id for item in relationships.list(sofia)] == ["rel:sofia"]
        assert [item.relationship_id for item in relationships.list(maya)] == ["rel:maya"]
    finally:
        database.close()
