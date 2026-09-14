from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.assistant_memory.models import MemoryRecord
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
    RetrievalCandidate,
    RetrievalQuery,
    RetrievalResult,
    RetrievalScore,
    VisibilityScope,
)
from app.assistant_memory_v2.convergence import (
    DerivedPlanPayload,
    PostgresMemoryV2DerivedCoordinator,
    StaleDerivedPlanError,
)
from app.assistant_memory_v2.derived_state import PostgresMemoryV2DerivedStateStore
from app.assistant_memory_v2.federated_retrieval import FederatedMemoryV2Retriever
from app.assistant_memory_v2.grant_store import PostgresMemoryV2GrantStore
from app.assistant_memory_v2.graph_store import PostgresMemoryV2GraphStore
from app.assistant_memory_v2.legacy_shadow import (
    LegacyMemoryV2Importer,
    PostgresMemoryV2ShadowEvaluationStore,
    compare_shadow_retrieval,
)
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
    PostgresMemoryV2ObservationStore,
)
from app.assistant_memory_v2.operations import PostgresMemoryV2ConvergenceWorker
from app.assistant_memory_v2.retrieval import UnifiedMemoryV2Retriever
from app.assistant_memory_v2.search_index import PostgresMemoryV2SearchIndex
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresConstraintError, PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

T0 = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)
GLOBAL = VisibilityScope(kind="global", scope_id="profile:alice")
USER = GraphEntityRef(entity_id="user:alice", entity_type="user")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=16,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-live-matrix-hardening",
        )
    )


def _space(tag: str) -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=f"{tag}-{uuid4().hex}",
    )


def _request(
    space: MemorySpaceKey,
    suffix: str,
    text: str,
    *,
    observation_id: str | None = None,
    sensitivity: str = "normal",
) -> ObservationAppendRequest:
    return ObservationAppendRequest(
        space=space,
        visibility_scope=GLOBAL,
        event_type="user_said",
        occurred_at=T0,
        provenance=ObservationProvenance(
            source_type="user",
            source_id="user:alice",
            trust_level="user_explicit",
            session_id="session:matrix-hardening",
            turn_id=f"turn:{suffix}",
            message_id=f"message:{suffix}",
        ),
        idempotency_key=f"matrix-hardening:{space.owner_id}:{suffix}",
        payload={"text": text},
        observation_id=observation_id,
        sensitivity=sensitivity,
    )


def _assertion(
    space: MemorySpaceKey,
    observation_id: str,
    *,
    value: str,
    domain: str = "fact",
    predicate: str = "matrix_fact",
) -> GraphAssertion:
    return GraphAssertion(
        assertion_id=f"assertion:{space.owner_id}:{observation_id}:{predicate}",
        space=space,
        visibility_scopes=(GLOBAL,),
        subject=USER,
        predicate=predicate,
        object=GraphValue(kind="literal", literal=value),
        domain=domain,
        confidence=0.95,
        valid_from=T0,
        evidence_observation_ids=(observation_id,),
        derivation_version="matrix-hardening@1",
    )


def _query(
    space: MemorySpaceKey,
    text: str,
    *,
    grant_ids: tuple[str, ...] = (),
    domains: tuple[str, ...] = (),
) -> RetrievalQuery:
    return RetrievalQuery(
        query_id=f"matrix-hardening:{uuid4().hex}",
        space=space,
        visible_scopes=(GLOBAL,),
        text=text,
        authority="final",
        as_of=T0 + timedelta(days=1),
        top_k=10,
        token_budget=2000,
        deadline_ms=500,
        grant_ids=grant_ids,
        domains=domains,
    )


def _retriever(
    database: PostgresDatabase,
    observations: PostgresMemoryV2ObservationStore,
    graph: PostgresMemoryV2GraphStore,
    derived: PostgresMemoryV2DerivedStateStore,
    search: PostgresMemoryV2SearchIndex,
) -> UnifiedMemoryV2Retriever:
    return UnifiedMemoryV2Retriever(
        graph_store=graph,
        observation_store=observations,
        index_graph_revision_provider=search.index_graph_revision,
        search_index=search,
        derived_store=derived,
    )


def test_M1_hardening_failed_insert_rolls_back_sequence_and_watermark() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        source = _space("m1-source")
        target = _space("m1-target")
        shared_observation_id = f"obs:shared:{uuid4().hex}"
        observations.append(
            _request(
                source,
                "source",
                "source observation",
                observation_id=shared_observation_id,
            )
        )

        with pytest.raises(PostgresConstraintError):
            observations.append(
                _request(
                    target,
                    "failing-target",
                    "must rollback",
                    observation_id=shared_observation_id,
                )
            )

        assert observations.watermark(target) == 0
        committed = observations.append(_request(target, "good-target", "committed"))
        assert committed.authority_sequence == 1
        assert observations.watermark(target) == 1
    finally:
        database.close()


def test_M3_hardening_multi_domain_failure_is_precise_and_atomic() -> None:
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
        space = _space("m3")
        source = observations.append(_request(space, "source", "atomic evidence"))
        assertion = _assertion(space, source.observation_id, value="atomic assertion")
        episode = Episode(
            episode_id=f"episode:{space.owner_id}",
            space=space,
            visibility_scopes=(GLOBAL,),
            title="Atomic episode",
            summary="Must roll back with the rest of the revision.",
            started_at=T0,
            observation_ids=(source.observation_id,),
            importance=0.8,
            derivation_version="matrix-hardening@1",
        )
        relationship = RelationshipState(
            relationship_id=f"relationship:{space.owner_id}",
            space=space,
            subject=GraphEntityRef(entity_id="character:sofia", entity_type="character"),
            counterpart=USER,
            metrics=(
                RelationshipMetric(
                    name="familiarity",
                    value=0.7,
                    confidence=0.8,
                    evidence_observation_ids=(source.observation_id,),
                ),
            ),
            prompt_interpretation="Familiar relationship.",
            evidence_observation_ids=(source.observation_id,),
            derivation_version="matrix-hardening@1",
        )
        invalid_affect = AffectObservation(
            affect_id=f"affect:{space.owner_id}",
            space=space,
            source_observation_id=f"missing:{source.observation_id}",
            source="semantic",
            observed_at=T0,
            valence=0.2,
            confidence=0.8,
            model_version="matrix-hardening@1",
        )
        prepared = coordinator.prepare(
            space,
            lambda _space, _window, _existing: DerivedPlanPayload(
                assertions=(assertion,),
                episodes=(episode,),
                relationships=(relationship,),
                affect=(invalid_affect,),
                consolidator_version="matrix-hardening@1",
            ),
        )
        assert prepared is not None

        with pytest.raises(StaleDerivedPlanError, match="evidence became inactive or disappeared"):
            coordinator.commit(prepared)

        assert derived.state(space).derived_revision == 0
        assert graph.list_assertions(space) == []
        with database.transaction() as connection:
            values = (space.principal_id, space.owner_type, space.owner_id)
            assert connection.execute(
                "SELECT COUNT(*) FROM omnix_memory_v2_episodes WHERE principal_id=%s AND owner_type=%s AND owner_id=%s",
                values,
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM omnix_memory_v2_relationships WHERE principal_id=%s AND owner_type=%s AND owner_id=%s",
                values,
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM omnix_memory_v2_affect_observations WHERE principal_id=%s AND owner_type=%s AND owner_id=%s",
                values,
            ).fetchone()[0] == 0
    finally:
        database.close()


def test_M10_hardening_federation_enforces_sensitivity_domain_and_revocation() -> None:
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
        source = _space("m10-source")
        target = _space("m10-target")
        secret = observations.append(
            _request(source, "secret", "secret launch phrase", sensitivity="secret")
        )
        observations.append(_request(target, "target", "target stream"))
        prepared = coordinator.prepare(
            source,
            lambda _space, _window, _existing: DerivedPlanPayload(
                assertions=(
                    _assertion(source, secret.observation_id, value="secret launch phrase"),
                ),
                consolidator_version="matrix-hardening@1",
            ),
        )
        assert prepared is not None
        coordinator.commit(prepared)
        search.rebuild(source)

        grants = PostgresMemoryV2GrantStore(database)
        created_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        normal_grant = grants.put(
            MemoryGrant(
                grant_id=f"grant:{uuid4().hex}",
                source_space=source,
                target_space=target,
                allowed_domains=("fact",),
                max_sensitivity="normal",
                created_by="matrix-hardening",
                created_at=created_at,
            )
        )
        federated = FederatedMemoryV2Retriever(
            local_retriever=_retriever(database, observations, graph, derived, search),
            grant_store=grants,
        )
        blocked_secret = federated.retrieve(
            _query(target, "secret launch phrase", grant_ids=(normal_grant.grant_id,))
        )
        assert blocked_secret.candidates == ()

        secret_grant = grants.put(
            MemoryGrant(
                grant_id=f"grant:{uuid4().hex}",
                source_space=source,
                target_space=target,
                allowed_domains=("fact",),
                max_sensitivity="secret",
                created_by="matrix-hardening",
                created_at=created_at,
            )
        )
        allowed = federated.retrieve(
            _query(target, "secret launch phrase", grant_ids=(secret_grant.grant_id,))
        )
        assert len(allowed.candidates) == 1
        assert allowed.candidates[0].policy is not None
        assert allowed.candidates[0].policy.sensitivity == "secret"

        wrong_domain = federated.retrieve(
            _query(
                target,
                "secret launch phrase",
                grant_ids=(secret_grant.grant_id,),
                domains=("preference",),
            )
        )
        assert wrong_domain.candidates == ()

        revoked = grants.revoke(
            secret_grant.grant_id,
            target_space=target,
            revoked_at=datetime.now(timezone.utc),
        )
        assert revoked.revision == secret_grant.revision + 1
        after_revoke = federated.retrieve(
            _query(target, "secret launch phrase", grant_ids=(secret_grant.grant_id,))
        )
        assert after_revoke.candidates == ()
    finally:
        database.close()


def test_M13_hardening_shadow_quality_checks_precision_and_staleness() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        space_owner = f"sofia-{uuid4().hex}"
        record = MemoryRecord(
            id=f"v1:{uuid4().hex}",
            owner_type="character",
            owner_id=space_owner,
            scope="global",
            scope_id="profile:alice",
            category="preference",
            kind="preference",
            source="user_saved",
            content="Skyrim is my favorite game",
            normalized_content="skyrim is my favorite game",
            trust_level="user_approved",
            provenance_type="user_message",
            provenance_id="message:v1",
            created_at="2026-09-14T03:00:00+00:00",
            updated_at="2026-09-14T03:00:00+00:00",
        )
        importer = LegacyMemoryV2Importer(observations)
        first = importer.import_record(principal_id="profile:alice", record=record)
        second = importer.import_record(principal_id="profile:alice", record=record)
        assert first is not None and second is not None
        assert first.observation_id == second.observation_id
        space = first.space

        matching = RetrievalCandidate(
            ref_id="candidate:matching",
            item_type="assertion",
            domain="preference",
            content="Skyrim is my favorite game",
            scores=RetrievalScore(semantic=1.0, composite=1.0),
            evidence_observation_ids=(first.observation_id,),
        )
        result = RetrievalResult(
            query_id="shadow:pass",
            candidates=(matching,),
            dynamic_context=(matching.content,),
            observation_watermark=observations.watermark(space),
            graph_revision=graph.state(space).graph_revision,
            index_graph_revision=0,
            elapsed_ms=1.0,
            deadline_ms=50.0,
        )
        report = compare_shadow_retrieval(
            space=space,
            v1_contents=[record.content],
            v2_result=result,
            observation_watermark=observations.watermark(space),
            graph_revision=graph.state(space).graph_revision,
            required_recall=0.8,
            required_precision=0.8,
        )
        assert report.passed is True
        assert report.recall == 1.0
        assert report.precision == 1.0

        store = PostgresMemoryV2ShadowEvaluationStore(
            database,
            graph_store=graph,
            observation_store=observations,
        )
        store.record(report)
        observations.append(_request(space, "later", "new evidence after quality receipt"))
        latest = store.latest(space)
        assert latest is not None and latest.passed is True
        assert latest.observation_watermark < observations.watermark(space)

        noisy = result.model_copy(
            update={
                "query_id": "shadow:noisy",
                "candidates": (
                    matching,
                    matching.model_copy(update={"ref_id": "candidate:false-1", "content": "unrelated false memory one"}),
                    matching.model_copy(update={"ref_id": "candidate:false-2", "content": "unrelated false memory two"}),
                ),
            }
        )
        failed = compare_shadow_retrieval(
            space=space,
            v1_contents=[record.content],
            v2_result=noisy,
            observation_watermark=observations.watermark(space),
            graph_revision=graph.state(space).graph_revision,
            required_recall=0.8,
            required_precision=0.8,
        )
        assert failed.recall == 1.0
        assert failed.precision < 0.8
        assert failed.passed is False
    finally:
        database.close()


def test_M18_hardening_global_queue_does_not_starve_healthy_space_after_poison() -> None:
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
        worker = PostgresMemoryV2ConvergenceWorker(
            database,
            coordinator=coordinator,
            search_index=search,
            derived_store=derived,
            max_backoff_seconds=30,
        )
        bad = _space("m18-bad")
        good = _space("m18-good")
        observations.append(_request(bad, "bad", "poisoned input"))
        good_observation = observations.append(_request(good, "good", "healthy input"))

        with database.transaction() as connection:
            connection.execute(
                "UPDATE omnix_memory_v2_derive_jobs SET available_at = CURRENT_TIMESTAMP - INTERVAL '10 seconds', updated_at = CURRENT_TIMESTAMP - INTERVAL '10 seconds' WHERE principal_id=%s AND owner_type=%s AND owner_id=%s",
                (bad.principal_id, bad.owner_type, bad.owner_id),
            )
            connection.execute(
                "UPDATE omnix_memory_v2_derive_jobs SET available_at = CURRENT_TIMESTAMP - INTERVAL '5 seconds', updated_at = CURRENT_TIMESTAMP - INTERVAL '5 seconds' WHERE principal_id=%s AND owner_type=%s AND owner_id=%s",
                (good.principal_id, good.owner_type, good.owner_id),
            )

        def planner(target: MemorySpaceKey, window, _existing):
            if target == bad:
                raise RuntimeError("poison")
            return DerivedPlanPayload(
                assertions=(
                    _assertion(
                        target,
                        window[0].observation_id,
                        value="healthy derived value",
                    ),
                ),
                consolidator_version="matrix-hardening@1",
            )

        assert worker.derive_once(planner) is True
        assert derived.state(bad).derived_revision == 0
        assert worker.derive_once(planner) is True
        good_state = derived.state(good)
        assert good_state.derived_revision == 1
        assert good_state.source_observation_watermark == good_observation.authority_sequence
    finally:
        database.close()
