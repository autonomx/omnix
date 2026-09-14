from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.assistant_memory_v2 import (
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemoryGrant,
    MemorySpaceKey,
    ObservationProvenance,
    RetrievalQuery,
    VisibilityScope,
)
from app.assistant_memory_v2.episode_store import PostgresMemoryV2EpisodeStore
from app.assistant_memory_v2.federated_retrieval import FederatedMemoryV2Retriever
from app.assistant_memory_v2.grant_store import PostgresMemoryV2GrantStore
from app.assistant_memory_v2.graph_store import PostgresMemoryV2GraphStore
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
    PostgresMemoryV2ObservationStore,
)
from app.assistant_memory_v2.relationship_store import PostgresMemoryV2RelationshipStore
from app.assistant_memory_v2.retrieval import UnifiedMemoryV2Retriever
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

T0 = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
GLOBAL = VisibilityScope(kind="global", scope_id="global")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=12,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-grant-tests",
        )
    )


def _space(prefix: str) -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=f"{prefix}-{uuid4().hex}",
    )


def _append(
    store: PostgresMemoryV2ObservationStore,
    space: MemorySpaceKey,
    index: int,
    *,
    scope: VisibilityScope = GLOBAL,
    text: str = "memory",
):
    return store.append(
        ObservationAppendRequest(
            space=space,
            visibility_scope=scope,
            event_type="user_said",
            occurred_at=T0 + timedelta(minutes=index),
            provenance=ObservationProvenance(
                source_type="user",
                source_id="user:alice",
                trust_level="user_explicit",
            ),
            idempotency_key=f"{space.owner_id}:{index}:{scope.kind}:{scope.scope_id}",
            payload={"text": text},
        )
    )


def _put_assertion(
    graph: PostgresMemoryV2GraphStore,
    observation,
    *,
    predicate: str,
    value: str,
    domain: str,
    scope: VisibilityScope = GLOBAL,
) -> GraphAssertion:
    assertion = GraphAssertion(
        assertion_id=f"assert:{uuid4().hex}",
        space=observation.space,
        visibility_scopes=(scope,),
        subject=GraphEntityRef(entity_id="user:alice", entity_type="user"),
        predicate=predicate,
        object=GraphValue(kind="literal", literal=value),
        domain=domain,
        confidence=0.95,
        valid_from=observation.occurred_at,
        evidence_observation_ids=(observation.observation_id,),
        derivation_version="phase11-test@1",
    )
    graph.put(assertion, source_observation_watermark=observation.authority_sequence)
    return assertion


def _retriever(database: PostgresDatabase) -> tuple[FederatedMemoryV2Retriever, PostgresMemoryV2GrantStore]:
    observations = PostgresMemoryV2ObservationStore(database)
    graph = PostgresMemoryV2GraphStore(database)
    local = UnifiedMemoryV2Retriever(
        graph_store=graph,
        observation_store=observations,
        episode_store=PostgresMemoryV2EpisodeStore(database),
        relationship_store=PostgresMemoryV2RelationshipStore(database),
    )
    grants = PostgresMemoryV2GrantStore(database)
    return FederatedMemoryV2Retriever(local_retriever=local, grant_store=grants), grants


def _query(
    target: MemorySpaceKey,
    *,
    grant_ids: tuple[str, ...],
    scopes: tuple[VisibilityScope, ...] = (GLOBAL,),
    as_of: datetime = T0 + timedelta(hours=1),
) -> RetrievalQuery:
    return RetrievalQuery(
        query_id=f"query:{uuid4().hex}",
        space=target,
        visible_scopes=scopes,
        text="Skyrim favorite game",
        authority="final",
        as_of=as_of,
        top_k=10,
        token_budget=2000,
        deadline_ms=1000,
        grant_ids=grant_ids,
    )


def test_grant_roundtrip_is_idempotent_and_read_only() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        source = _space("source")
        target = _space("target")
        _append(observations, source, 1)
        _append(observations, target, 1)
        grants = PostgresMemoryV2GrantStore(database)
        grant = MemoryGrant(
            grant_id=f"grant:{uuid4().hex}",
            source_space=source,
            target_space=target,
            allowed_domains=("preference", "fact"),
            max_sensitivity="normal",
            created_by="user:alice",
            created_at=T0 + timedelta(minutes=2),
        )

        assert grants.put(grant) == grant
        assert grants.put(grant) == grant
        assert grants.get(grant.grant_id) == grant
        assert grants.active_for_target(target, grant_ids=(grant.grant_id,)) == [grant]
    finally:
        database.close()


def test_federated_retrieval_requires_explicit_grant_id_and_never_copies_memory() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        source = _space("source")
        target = _space("target")
        preference_observation = _append(
            observations,
            source,
            1,
            text="Skyrim is my favorite game",
        )
        goal_observation = _append(
            observations,
            source,
            2,
            text="Finish the memory migration",
        )
        _append(observations, target, 1, text="Target stream exists")
        preference = _put_assertion(
            graph,
            preference_observation,
            predicate="favorite_game",
            value="Skyrim",
            domain="preference",
        )
        goal = _put_assertion(
            graph,
            goal_observation,
            predicate="current_goal",
            value="Finish the memory migration",
            domain="goal",
        )
        federated, grants = _retriever(database)
        grant = MemoryGrant(
            grant_id=f"grant:{uuid4().hex}",
            source_space=source,
            target_space=target,
            allowed_domains=("preference",),
            max_sensitivity="normal",
            created_by="user:alice",
            created_at=T0 + timedelta(minutes=3),
        )
        grants.put(grant)

        local_only = federated.retrieve(_query(target, grant_ids=()))
        assert preference.assertion_id not in {item.ref_id for item in local_only.candidates}

        shared = federated.retrieve(_query(target, grant_ids=(grant.grant_id,)))
        ids = {item.ref_id for item in shared.candidates}
        assert preference.assertion_id in ids
        assert goal.assertion_id not in ids
        candidate = next(item for item in shared.candidates if item.ref_id == preference.assertion_id)
        assert f"memory_grant:{grant.grant_id}" in candidate.reasons
        assert graph.list_assertions(target) == []
    finally:
        database.close()


def test_revoked_grant_cannot_be_resurrected_by_historical_query() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        source = _space("source")
        target = _space("target")
        source_observation = _append(observations, source, 1, text="Skyrim is my favorite game")
        _append(observations, target, 1)
        assertion = _put_assertion(
            graph,
            source_observation,
            predicate="favorite_game",
            value="Skyrim",
            domain="preference",
        )
        federated, grants = _retriever(database)
        grant = MemoryGrant(
            grant_id=f"grant:{uuid4().hex}",
            source_space=source,
            target_space=target,
            allowed_domains=("preference",),
            max_sensitivity="normal",
            created_by="user:alice",
            created_at=T0 + timedelta(minutes=2),
        )
        grants.put(grant)
        initially_visible = federated.retrieve(_query(target, grant_ids=(grant.grant_id,)))
        assert assertion.assertion_id in {item.ref_id for item in initially_visible.candidates}

        revoked_at = T0 + timedelta(minutes=10)
        revoked = grants.revoke(
            grant.grant_id,
            target_space=target,
            revoked_at=revoked_at,
        )
        assert revoked.revoked_at == revoked_at

        historical_query = federated.retrieve(
            _query(
                target,
                grant_ids=(grant.grant_id,),
                as_of=revoked_at - timedelta(seconds=1),
            )
        )
        current_query = federated.retrieve(
            _query(
                target,
                grant_ids=(grant.grant_id,),
                as_of=revoked_at + timedelta(seconds=1),
            )
        )
        assert assertion.assertion_id not in {item.ref_id for item in historical_query.candidates}
        assert assertion.assertion_id not in {item.ref_id for item in current_query.candidates}
    finally:
        database.close()


def test_grant_scope_constraints_intersect_with_interaction_visibility() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        source = _space("source")
        target = _space("target")
        workspace = VisibilityScope(kind="workspace", scope_id="workspace:alpha")
        source_observation = _append(
            observations,
            source,
            1,
            scope=workspace,
            text="Skyrim is my favorite game",
        )
        _append(observations, target, 1)
        assertion = _put_assertion(
            graph,
            source_observation,
            predicate="favorite_game",
            value="Skyrim",
            domain="preference",
            scope=workspace,
        )
        federated, grants = _retriever(database)
        grant = MemoryGrant(
            grant_id=f"grant:{uuid4().hex}",
            source_space=source,
            target_space=target,
            allowed_domains=("preference",),
            max_sensitivity="normal",
            scope_constraints=(workspace,),
            created_by="user:alice",
            created_at=T0 + timedelta(minutes=2),
        )
        grants.put(grant)

        hidden = federated.retrieve(_query(target, grant_ids=(grant.grant_id,), scopes=(GLOBAL,)))
        visible = federated.retrieve(_query(target, grant_ids=(grant.grant_id,), scopes=(workspace,)))
        assert assertion.assertion_id not in {item.ref_id for item in hidden.candidates}
        assert assertion.assertion_id in {item.ref_id for item in visible.candidates}
    finally:
        database.close()
