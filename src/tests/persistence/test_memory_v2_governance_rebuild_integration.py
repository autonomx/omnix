from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.assistant_memory_v2 import (
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemorySpaceKey,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory_v2.convergence import (
    DerivedPlanPayload,
    PostgresMemoryV2DerivedCoordinator,
)
from app.assistant_memory_v2.derived_state import PostgresMemoryV2DerivedStateStore
from app.assistant_memory_v2.graph_store import PostgresMemoryV2GraphStore
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

T0 = datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc)
GLOBAL = VisibilityScope(kind="global", scope_id="profile:alice")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=8,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-governance-rebuild-tests",
        )
    )


def test_governance_rebuild_is_full_replacement_not_incremental_merge() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        derived = PostgresMemoryV2DerivedStateStore(database)
        coordinator = PostgresMemoryV2DerivedCoordinator(
            database,
            observation_store=observations,
            graph_store=graph,
            derived_store=derived,
        )
        space = MemorySpaceKey(
            principal_id="profile:alice",
            owner_type="character",
            owner_id=f"sofia-{uuid4().hex}",
        )
        observation = observations.append(
            ObservationAppendRequest(
                space=space,
                visibility_scope=GLOBAL,
                event_type="user_said",
                occurred_at=T0,
                provenance=ObservationProvenance(
                    source_type="user",
                    source_id="user:alice",
                    trust_level="user_explicit",
                ),
                idempotency_key=f"governance-rebuild:{space.owner_id}",
                payload={"text": "Skyrim is my favorite game"},
            )
        )
        assertion = GraphAssertion(
            assertion_id=f"assertion:{observation.observation_id}",
            space=space,
            visibility_scopes=(GLOBAL,),
            subject=GraphEntityRef(entity_id="profile:alice", entity_type="profile"),
            predicate="favorite_game",
            object=GraphValue(kind="literal", literal="Skyrim"),
            domain="preference",
            confidence=0.95,
            valid_from=T0,
            evidence_observation_ids=(observation.observation_id,),
            derivation_version="governance-rebuild-test@1",
        )

        initial = coordinator.prepare(
            space,
            lambda _space, _window, _existing: DerivedPlanPayload(
                assertions=(assertion,),
                consolidator_version="governance-rebuild-test@1",
            ),
        )
        assert initial is not None
        first_revision = coordinator.commit(initial)
        assert first_revision.derived_revision == 1
        assert graph.list_assertions(space) == [assertion]
        assert derived.policy(space, "assertion", assertion.assertion_id) is not None

        observations.set_disposition(
            space,
            observation.observation_id,
            state="revoked",
            actor_id="test:privacy",
            reason="remove source evidence",
        )

        def rebuild_planner(_space, window, existing):
            assert window == ()
            assert existing
            return DerivedPlanPayload(consolidator_version="governance-rebuild-test@1")

        replacement = coordinator.prepare(space, rebuild_planner)
        assert replacement is not None
        assert replacement.rebuild is True
        second_revision = coordinator.commit(replacement)
        assert second_revision.derived_revision == 2
        assert second_revision.source_governance_revision == 1

        assert graph.list_assertions(space) == []
        assert derived.policy(space, "assertion", assertion.assertion_id) is None
        state = derived.state(space)
        assert state.derived_revision == 2
        assert state.source_observation_watermark == observation.authority_sequence
        assert state.source_governance_revision == 1
    finally:
        database.close()
