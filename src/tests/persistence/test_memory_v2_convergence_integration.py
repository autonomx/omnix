from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.assistant_memory_v2 import (
    AffectObservation,
    Episode,
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemoryGrant,
    MemorySpaceKey,
    ObservationProvenance,
    RelationshipMetric,
    RelationshipState,
    RetrievalQuery,
    VisibilityScope,
)
from app.assistant_memory_v2.affect_store import PostgresMemoryV2AffectStore
from app.assistant_memory_v2.consolidation import PostgresMemoryV2Consolidator
from app.assistant_memory_v2.convergence import (
    DerivedPlanPayload,
    PostgresMemoryV2DerivedCoordinator,
    RedactedDecisionSetError,
    StaleDerivedPlanError,
)
from app.assistant_memory_v2.derived_state import PostgresMemoryV2DerivedStateStore
from app.assistant_memory_v2.episode_store import PostgresMemoryV2EpisodeStore
from app.assistant_memory_v2.federated_retrieval import FederatedMemoryV2Retriever
from app.assistant_memory_v2.grant_store import PostgresMemoryV2GrantStore
from app.assistant_memory_v2.graph_store import PostgresMemoryV2GraphStore
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
    PostgresMemoryV2ObservationStore,
)
from app.assistant_memory_v2.operations import PostgresMemoryV2ConvergenceWorker
from app.assistant_memory_v2.relationship_store import PostgresMemoryV2RelationshipStore
from app.assistant_memory_v2.replay import PostgresMemoryV2DerivedReplayValidator
from app.assistant_memory_v2.retrieval import UnifiedMemoryV2Retriever
from app.assistant_memory_v2.search_index import PostgresMemoryV2SearchIndex
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

T0 = datetime(2026, 9, 14, 4, 0, tzinfo=timezone.utc)
GLOBAL = VisibilityScope(kind="global", scope_id="profile:alice")
SESSION = VisibilityScope(kind="session", scope_id="session:private")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=12,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-convergence-tests",
        )
    )


def _space(suffix: str | None = None) -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=f"sofia-{suffix or uuid4().hex}",
    )


def _append(
    store: PostgresMemoryV2ObservationStore,
    space: MemorySpaceKey,
    *,
    suffix: str,
    scope: VisibilityScope = SESSION,
    sensitivity: str = "sensitive",
):
    return store.append(
        ObservationAppendRequest(
            space=space,
            visibility_scope=scope,
            event_type="user_said",
            occurred_at=T0,
            provenance=ObservationProvenance(
                source_type="user",
                source_id="user:alice",
                trust_level="user_explicit",
                session_id="session:private",
                turn_id=f"turn:{suffix}",
                message_id=f"message:{suffix}",
            ),
            sensitivity=sensitivity,
            idempotency_key=f"convergence:{space.owner_id}:{suffix}",
            payload={"text": f"private fact {suffix}"},
        )
    )


def _assertion(space: MemorySpaceKey, observation_id: str) -> GraphAssertion:
    return GraphAssertion(
        assertion_id=f"assertion:{observation_id}",
        space=space,
        # Deliberately broader than the session-local evidence. Policy convergence must
        # retain the session requirement instead of promoting this belief to global.
        visibility_scopes=(GLOBAL,),
        subject=GraphEntityRef(entity_id="profile:alice", entity_type="profile"),
        predicate="private_fact",
        object=GraphValue(kind="literal", literal="private fact"),
        domain="fact",
        confidence=0.9,
        valid_from=T0,
        evidence_observation_ids=(observation_id,),
        derivation_version="convergence-test@1",
    )


def _multi_domain_plan(space: MemorySpaceKey, observation_id: str) -> DerivedPlanPayload:
    subject = GraphEntityRef(entity_id="character:sofia", entity_type="character")
    counterpart = GraphEntityRef(entity_id="profile:alice", entity_type="profile")
    return DerivedPlanPayload(
        assertions=(_assertion(space, observation_id),),
        episodes=(
            Episode(
                episode_id=f"episode:{observation_id}",
                space=space,
                visibility_scopes=(GLOBAL,),
                title="Private discussion",
                summary="A session-local private discussion.",
                started_at=T0,
                observation_ids=(observation_id,),
                importance=0.8,
                derivation_version="convergence-test@1",
            ),
        ),
        relationships=(
            RelationshipState(
                relationship_id=f"relationship:{observation_id}",
                space=space,
                subject=subject,
                counterpart=counterpart,
                metrics=(
                    RelationshipMetric(
                        name="familiarity",
                        value=0.7,
                        confidence=0.8,
                        evidence_observation_ids=(observation_id,),
                    ),
                ),
                prompt_interpretation="The relationship is becoming familiar.",
                evidence_observation_ids=(observation_id,),
                derivation_version="convergence-test@1",
            ),
        ),
        affect=(
            AffectObservation(
                affect_id=f"affect:{observation_id}",
                space=space,
                source_observation_id=observation_id,
                source="semantic",
                observed_at=T0,
                valence=0.2,
                confidence=0.8,
                model_version="convergence-test@1",
            ),
        ),
        normalized_proposals=(
            {"source_observation_id": observation_id, "kind": "test-proposal"},
        ),
        consolidator_version="convergence-test@1",
    )


def test_atomic_derived_revision_propagates_policy_and_exact_replays() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        coordinator = PostgresMemoryV2DerivedCoordinator(
            database,
            observation_store=observations,
            graph_store=graph,
        )
        space = _space()
        observation = _append(observations, space, suffix="atomic")

        def planner(_space, window, _existing):
            assert window == (observation,)
            return _multi_domain_plan(space, observation.observation_id)

        prepared = coordinator.prepare(space, planner)
        assert prepared is not None
        revision = coordinator.commit(prepared)
        assert revision.derived_revision == 1
        assert revision.source_observation_watermark == observation.authority_sequence
        assert PostgresMemoryV2Consolidator(database).watermark(space) == observation.authority_sequence

        derived = PostgresMemoryV2DerivedStateStore(database)
        policies = {
            kind: derived.policy(space, kind, ref_id)
            for kind, ref_id in (
                ("assertion", f"assertion:{observation.observation_id}"),
                ("episode", f"episode:{observation.observation_id}"),
                ("relationship", f"relationship:{observation.observation_id}"),
                ("affect", f"affect:{observation.observation_id}"),
            )
        }
        assert all(policy is not None for policy in policies.values())
        for policy in policies.values():
            assert policy is not None
            assert policy.sensitivity == "sensitive"
            assert SESSION in policy.effective_visibility

        assert PostgresMemoryV2EpisodeStore(database).get(
            space, f"episode:{observation.observation_id}"
        ) is not None
        assert PostgresMemoryV2RelationshipStore(database).get(
            space, f"relationship:{observation.observation_id}"
        ) is not None
        assert PostgresMemoryV2AffectStore(database).get(
            space, f"affect:{observation.observation_id}"
        ) is not None

        replay = PostgresMemoryV2DerivedReplayValidator(database).validate(space)
        assert replay.matches is True
        assert replay.derived_revision == 1
    finally:
        database.close()


def test_governance_change_during_inference_rejects_stale_plan_without_deadlock() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        coordinator = PostgresMemoryV2DerivedCoordinator(database, observation_store=observations)
        space = _space()
        observation = _append(observations, space, suffix="race")

        def planner(_space, _window, _existing):
            # This succeeds only because planner execution is outside the authority
            # transaction. It also makes the prepared plan stale by construction.
            observations.set_disposition(
                space,
                observation.observation_id,
                state="revoked",
                actor_id="test:governance-race",
            )
            return _multi_domain_plan(space, observation.observation_id)

        prepared = coordinator.prepare(space, planner)
        assert prepared is not None
        with pytest.raises(StaleDerivedPlanError, match="governance revision changed"):
            coordinator.commit(prepared)
        assert PostgresMemoryV2DerivedStateStore(database).state(space).derived_revision == 0
    finally:
        database.close()


def test_purge_redacts_decision_set_and_blocks_exact_replay() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        coordinator = PostgresMemoryV2DerivedCoordinator(database, observation_store=observations)
        space = _space()
        observation = _append(observations, space, suffix="purge")
        prepared = coordinator.prepare(
            space,
            lambda _space, _window, _existing: _multi_domain_plan(
                space, observation.observation_id
            ),
        )
        assert prepared is not None
        revision = coordinator.commit(prepared)

        observations.set_disposition(
            space,
            observation.observation_id,
            state="purged",
            actor_id="test:privacy",
            reason="user requested deletion",
        )
        decision = coordinator.decision_set(revision.decision_set_id)
        assert decision is not None
        assert decision.redacted_at is not None
        assert decision.normalized_proposals == ()
        with pytest.raises(RedactedDecisionSetError):
            coordinator.exact_replay_payload(revision.decision_set_id)
    finally:
        database.close()


def test_durable_worker_converges_observation_derived_and_projection_lag() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        worker = PostgresMemoryV2ConvergenceWorker(database)
        space = _space()
        observation = _append(observations, space, suffix="worker", scope=GLOBAL)

        assert worker.lag(space).observation_to_derived == 1
        assert worker.derive_once(
            lambda _space, _window, _existing: DerivedPlanPayload(
                assertions=(_assertion(space, observation.observation_id),),
                consolidator_version="worker-test@1",
            )
        ) is True
        after_derive = worker.lag(space)
        assert after_derive.observation_to_derived == 0
        assert after_derive.derived_to_index == 1
        assert worker.project_once() is True
        converged = worker.lag(space)
        assert converged.observation_to_derived == 0
        assert converged.governance_to_derived == 0
        assert converged.derived_to_index == 0
    finally:
        database.close()


def test_federated_grant_enforces_sensitivity_and_reports_source_revision() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        search = PostgresMemoryV2SearchIndex(database)
        derived = PostgresMemoryV2DerivedStateStore(database)
        coordinator = PostgresMemoryV2DerivedCoordinator(
            database,
            observation_store=observations,
            graph_store=graph,
            derived_store=derived,
        )
        source = _space("source")
        target = _space("target")
        secret = _append(
            observations,
            source,
            suffix="secret",
            scope=GLOBAL,
            sensitivity="secret",
        )
        prepared = coordinator.prepare(
            source,
            lambda _space, _window, _existing: DerivedPlanPayload(
                assertions=(_assertion(source, secret.observation_id),),
                consolidator_version="federation-test@1",
            ),
        )
        assert prepared is not None
        coordinator.commit(prepared)
        search.rebuild(source)

        local = UnifiedMemoryV2Retriever(
            graph_store=graph,
            observation_store=observations,
            episode_store=PostgresMemoryV2EpisodeStore(database),
            relationship_store=PostgresMemoryV2RelationshipStore(database),
            index_graph_revision_provider=search.index_graph_revision,
            search_index=search,
            derived_store=derived,
        )
        grants = PostgresMemoryV2GrantStore(database)
        normal_grant = MemoryGrant(
            grant_id=f"grant:normal:{uuid4().hex}",
            source_space=source,
            target_space=target,
            allowed_domains=("fact",),
            max_sensitivity="normal",
            created_by="test",
            created_at=T0,
        )
        secret_grant = MemoryGrant(
            grant_id=f"grant:secret:{uuid4().hex}",
            source_space=source,
            target_space=target,
            allowed_domains=("fact",),
            max_sensitivity="secret",
            created_by="test",
            created_at=T0,
        )
        grants.put(normal_grant)
        grants.put(secret_grant)
        federated = FederatedMemoryV2Retriever(local_retriever=local, grant_store=grants)

        def query(grant_id: str) -> RetrievalQuery:
            return RetrievalQuery(
                query_id=f"federated:{grant_id}",
                space=target,
                visible_scopes=(GLOBAL,),
                text="private fact",
                authority="final",
                as_of=T0,
                grant_ids=(grant_id,),
            )

        blocked = federated.retrieve(query(normal_grant.grant_id))
        assert blocked.candidates == ()
        allowed = federated.retrieve(query(secret_grant.grant_id))
        assert len(allowed.candidates) == 1
        assert allowed.candidates[0].source_space == source
        assert allowed.source_revisions
        source_revision = next(
            item for item in allowed.source_revisions if item.source_space == source
        )
        assert source_revision.derived_revision == 1
        assert source_revision.grant_revision == secret_grant.revision
        assert allowed.federation_revision_digest
    finally:
        database.close()
