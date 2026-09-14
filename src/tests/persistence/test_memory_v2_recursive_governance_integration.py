from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.assistant_memory_v2 import (
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemorySpaceKey,
    ObservationProvenance,
    RetrievalQuery,
    VisibilityScope,
)
from app.assistant_memory_v2.convergence import (
    DerivedPlanPayload,
    PostgresMemoryV2DerivedCoordinator,
)
from app.assistant_memory_v2.derived_state import PostgresMemoryV2DerivedStateStore
from app.assistant_memory_v2.episode_store import PostgresMemoryV2EpisodeStore
from app.assistant_memory_v2.graph_store import PostgresMemoryV2GraphStore
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
    PostgresMemoryV2ObservationStore,
)
from app.assistant_memory_v2.relationship_store import PostgresMemoryV2RelationshipStore
from app.assistant_memory_v2.retrieval import UnifiedMemoryV2Retriever
from app.assistant_memory_v2.search_index import PostgresMemoryV2SearchIndex
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

T0 = datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)
GLOBAL = VisibilityScope(kind="global", scope_id="profile:alice")
USER = GraphEntityRef(entity_id="user:alice", entity_type="user")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=8,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-recursive-governance-tests",
        )
    )


def test_recursive_assertion_evidence_fails_closed_after_revoke_and_purge() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        derived = PostgresMemoryV2DerivedStateStore(database)
        search = PostgresMemoryV2SearchIndex(database)
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
                idempotency_key=f"recursive-governance:{space.owner_id}",
                payload={"text": "the private launch phrase is orchid"},
                sensitivity="secret",
            )
        )
        base = GraphAssertion(
            assertion_id=f"assertion:base:{observation.observation_id}",
            space=space,
            visibility_scopes=(GLOBAL,),
            subject=USER,
            predicate="launch_phrase",
            object=GraphValue(kind="literal", literal="orchid"),
            domain="fact",
            confidence=0.99,
            valid_from=T0,
            evidence_observation_ids=(observation.observation_id,),
            derivation_version="recursive-governance@1",
        )
        dependent = GraphAssertion(
            assertion_id=f"assertion:dependent:{observation.observation_id}",
            space=space,
            visibility_scopes=(GLOBAL,),
            subject=USER,
            predicate="launch_instruction",
            object=GraphValue(kind="literal", literal="use orchid for launch"),
            domain="instruction",
            confidence=0.95,
            valid_from=T0,
            evidence_assertion_ids=(base.assertion_id,),
            derivation_version="recursive-governance@1",
        )
        prepared = coordinator.prepare(
            space,
            lambda _space, _window, _existing: DerivedPlanPayload(
                assertions=(base, dependent),
                consolidator_version="recursive-governance@1",
            ),
        )
        assert prepared is not None
        coordinator.commit(prepared)
        search.rebuild(space)

        dependent_policy = derived.policy(space, "assertion", dependent.assertion_id)
        assert dependent_policy is not None
        assert dependent_policy.source_observation_ids == (observation.observation_id,)

        retriever = UnifiedMemoryV2Retriever(
            graph_store=graph,
            observation_store=observations,
            episode_store=PostgresMemoryV2EpisodeStore(database),
            relationship_store=PostgresMemoryV2RelationshipStore(database),
            index_graph_revision_provider=search.index_graph_revision,
            search_index=search,
            derived_store=derived,
        )
        query = RetrievalQuery(
            query_id=f"query:{uuid4().hex}",
            space=space,
            visible_scopes=(GLOBAL,),
            text="orchid launch",
            authority="final",
            as_of=T0 + timedelta(days=1),
            top_k=10,
            token_budget=2000,
            deadline_ms=500,
        )
        assert {candidate.ref_id for candidate in retriever.retrieve(query).candidates} >= {
            base.assertion_id,
            dependent.assertion_id,
        }

        observations.set_disposition(
            space,
            observation.observation_id,
            state="revoked",
            actor_id="test:privacy",
        )
        assert retriever.retrieve(query).candidates == ()

        observations.set_disposition(
            space,
            observation.observation_id,
            state="purged",
            actor_id="test:privacy",
        )
        assert derived.policy(space, "assertion", dependent.assertion_id) is None
        assert graph.get_assertion(space, dependent.assertion_id) is not None
        assert retriever.retrieve(query).candidates == ()
    finally:
        database.close()
