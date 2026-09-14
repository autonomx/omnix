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
    RetrievalCandidate,
    RetrievalResult,
    RetrievalScore,
    VisibilityScope,
)
from app.assistant_memory_v2.authority import (
    PostgresMemoryV2AuthorityStore,
    StaleCutoverReceiptError,
)
from app.assistant_memory_v2.convergence import (
    DerivedPlanPayload,
    PostgresMemoryV2DerivedCoordinator,
)
from app.assistant_memory_v2.graph_store import (
    GraphReplayValidator,
    PostgresMemoryV2GraphStore,
)
from app.assistant_memory_v2.legacy_shadow import (
    PostgresMemoryV2ShadowEvaluationStore,
    compare_shadow_retrieval,
)
from app.assistant_memory_v2.observation_store import (
    ObservationAppendRequest,
    PostgresMemoryV2ObservationStore,
)
from app.assistant_memory_v2.search_index import PostgresMemoryV2SearchIndex
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

T0 = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
GLOBAL = VisibilityScope(kind="global", scope_id="profile:alice")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=12,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-authority-cutover-tests",
        )
    )


def _reset_global_authority_to_v1(database: PostgresDatabase) -> None:
    """Isolate tests that mutate the singleton Memory v2 authority epoch."""

    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE omnix_memory_v2_authority_current
               SET current_epoch = 1, updated_at = CURRENT_TIMESTAMP
             WHERE singleton = TRUE
            """
        )
        connection.execute(
            "DELETE FROM omnix_memory_v2_authority_epochs WHERE epoch > 1"
        )


def _assertion(space: MemorySpaceKey, observation_id: str) -> GraphAssertion:
    return GraphAssertion(
        assertion_id=f"assertion:{observation_id}",
        space=space,
        visibility_scopes=(GLOBAL,),
        subject=GraphEntityRef(entity_id="profile:alice", entity_type="profile"),
        predicate="favorite_game",
        object=GraphValue(kind="literal", literal="Skyrim is my favorite game"),
        domain="preference",
        assertion_type="derived",
        confidence=0.95,
        valid_from=T0,
        evidence_observation_ids=(observation_id,),
        derivation_version="authority-cutover-test@1",
        status="active",
    )


def _prepare_ready_space(
    database: PostgresDatabase,
) -> tuple[
    PostgresMemoryV2AuthorityStore,
    MemorySpaceKey,
    str,
    str,
]:
    _reset_global_authority_to_v1(database)
    observations = PostgresMemoryV2ObservationStore(database)
    graph = PostgresMemoryV2GraphStore(database)
    search = PostgresMemoryV2SearchIndex(database)
    shadow = PostgresMemoryV2ShadowEvaluationStore(
        database,
        graph_store=graph,
        observation_store=observations,
    )
    authority = PostgresMemoryV2AuthorityStore(
        database,
        observation_store=observations,
        graph_store=graph,
        search_index=search,
        shadow_store=shadow,
    )
    coordinator = PostgresMemoryV2DerivedCoordinator(
        database,
        observation_store=observations,
        graph_store=graph,
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
                session_id="session:cutover",
                turn_id="turn:1",
                message_id="message:1",
            ),
            idempotency_key=f"authority-cutover:{space.owner_id}",
            payload={"text": "Skyrim is my favorite game"},
        )
    )
    authority.advance_authoritative_event_watermark(space, observation.authority_sequence)

    def derived_planner(
        planner_space: MemorySpaceKey,
        window: tuple,
        _existing: tuple,
    ) -> DerivedPlanPayload:
        assert planner_space == space
        assert len(window) == 1
        return DerivedPlanPayload(
            assertions=(_assertion(space, window[0].observation_id),),
            consolidator_version="authority-cutover-test@2",
        )

    prepared = coordinator.prepare(space, derived_planner)
    assert prepared is not None
    derived_revision = coordinator.commit(prepared)
    assert derived_revision.derived_revision == 1
    search.rebuild(space)

    graph_state = graph.state(space)
    result = RetrievalResult(
        query_id="shadow:cutover",
        candidates=(
            RetrievalCandidate(
                ref_id=f"assertion:{observation.observation_id}",
                item_type="assertion",
                domain="preference",
                content="Skyrim is my favorite game",
                scores=RetrievalScore(semantic=1.0, composite=1.0),
                evidence_observation_ids=(observation.observation_id,),
            ),
        ),
        dynamic_context=("Skyrim is my favorite game",),
        observation_watermark=observations.watermark(space),
        graph_revision=graph_state.graph_revision,
        index_graph_revision=search.state(space).index_graph_revision,
        elapsed_ms=1.0,
        deadline_ms=50,
    )
    shadow_report = compare_shadow_retrieval(
        space=space,
        v1_contents=["Skyrim is my favorite game"],
        v2_result=result,
        observation_watermark=observations.watermark(space),
        graph_revision=graph_state.graph_revision,
        required_recall=0.8,
        required_precision=0.8,
    )
    assert shadow_report.passed is True
    shadow.record(shadow_report)

    def replay_projector(window: tuple) -> tuple[GraphAssertion, ...]:
        return tuple(_assertion(space, item.observation_id) for item in window)

    replay = GraphReplayValidator(graph, observations).validate(space, replay_projector)
    assert replay.matches is True
    readiness = authority.evaluate_space(space, graph_validation=replay)
    assert readiness.readiness.ready is True
    assert readiness.derived_revision == 1
    assert readiness.index_derived_revision == 1
    return authority, space, readiness.receipt_id, observation.observation_id


def test_transactional_cutover_activates_v2_only_from_fresh_ready_receipt() -> None:
    database = _database()
    try:
        apply_migrations(database)
        authority, _space, receipt_id, _observation_id = _prepare_ready_space(database)
        before = authority.current()
        assert before.epoch.authority == "v1"

        activated = authority.activate_v2(
            (receipt_id,),
            activated_by="test:cutover",
            reason="phase 15 integration test",
        )
        assert activated.epoch.authority == "v2"
        assert activated.epoch.previous_epoch == before.epoch.epoch
        assert activated.epoch.readiness is not None
        assert activated.epoch.readiness.ready is True
        assert activated.readiness_receipt_ids == (receipt_id,)
        assert authority.current() == activated

        repeated = authority.activate_v2(
            (receipt_id,),
            activated_by="test:cutover-retry",
        )
        assert repeated.epoch.epoch == activated.epoch.epoch
    finally:
        database.close()


def test_cutover_receipt_becomes_stale_when_authoritative_feed_advances() -> None:
    database = _database()
    try:
        apply_migrations(database)
        authority, space, receipt_id, _observation_id = _prepare_ready_space(database)
        authority.advance_authoritative_event_watermark(space, 2)
        with pytest.raises(StaleCutoverReceiptError, match="stale"):
            authority.activate_v2((receipt_id,), activated_by="test:stale-feed")
        assert authority.current().epoch.authority == "v1"
    finally:
        database.close()


def test_cutover_receipt_becomes_stale_after_governance_change() -> None:
    database = _database()
    try:
        apply_migrations(database)
        authority, space, receipt_id, observation_id = _prepare_ready_space(database)
        authority.observation_store.set_disposition(
            space,
            observation_id,
            state="revoked",
            actor_id="test:privacy",
            reason="cutover must notice governance changes",
        )
        with pytest.raises(StaleCutoverReceiptError, match="stale"):
            authority.activate_v2((receipt_id,), activated_by="test:stale-governance")
        assert authority.current().epoch.authority == "v1"
    finally:
        database.close()


def test_cutover_receipt_cannot_ignore_a_newer_failing_shadow_evaluation() -> None:
    database = _database()
    try:
        apply_migrations(database)
        authority, space, receipt_id, _observation_id = _prepare_ready_space(database)
        graph_state = authority.graph_store.state(space)
        bad_result = RetrievalResult(
            query_id="shadow:newer-failure",
            candidates=(
                RetrievalCandidate(
                    ref_id="false-1",
                    item_type="assertion",
                    domain="fact",
                    content="The user lives on Mars",
                    scores=RetrievalScore(semantic=1.0, composite=1.0),
                ),
            ),
            dynamic_context=(),
            observation_watermark=authority.observation_store.watermark(space),
            graph_revision=graph_state.graph_revision,
            index_graph_revision=authority.search_index.state(space).index_graph_revision,
            elapsed_ms=1.0,
            deadline_ms=50,
        )
        failure = compare_shadow_retrieval(
            space=space,
            v1_contents=["Skyrim is my favorite game"],
            v2_result=bad_result,
            observation_watermark=authority.observation_store.watermark(space),
            graph_revision=graph_state.graph_revision,
            required_recall=0.8,
            required_precision=0.8,
        )
        assert failure.passed is False
        authority.shadow_store.record(failure)

        with pytest.raises(StaleCutoverReceiptError, match="stale"):
            authority.activate_v2((receipt_id,), activated_by="test:newer-shadow-failure")
        assert authority.current().epoch.authority == "v1"
    finally:
        database.close()
