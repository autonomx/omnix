from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
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
    RetrievalQuery,
    RetrievalResult,
    RetrievalScore,
    VisibilityScope,
)
from app.assistant_memory_v2.authority import PostgresMemoryV2AuthorityStore
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
from app.assistant_memory_v2.runtime import (
    AuthoritativeIngestSequenceError,
    MemoryV2NotAuthoritativeError,
    PostgresMemoryV2Runtime,
    UnsafeMemoryRollbackError,
)
from app.assistant_memory_v2.search_index import PostgresMemoryV2SearchIndex
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

T0 = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)
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
            application_name="omnix-memory-v2-runtime-tests",
        )
    )


def _reset_authority(database: PostgresDatabase) -> None:
    with database.transaction() as connection:
        connection.execute(
            "UPDATE omnix_memory_v2_authority_current SET current_epoch = 1, "
            "updated_at = CURRENT_TIMESTAMP WHERE singleton = TRUE"
        )
        connection.execute("DELETE FROM omnix_memory_v2_authority_epochs WHERE epoch > 1")


@pytest.fixture(autouse=True)
def _isolate_global_authority_epoch():
    """Do not leak a v2 singleton epoch into unrelated persistence tests."""

    database = _database()
    try:
        apply_migrations(database)
        _reset_authority(database)
    finally:
        database.close()
    yield
    database = _database()
    try:
        apply_migrations(database)
        _reset_authority(database)
    finally:
        database.close()


def _assertion(space: MemorySpaceKey, observation_id: str) -> GraphAssertion:
    return GraphAssertion(
        assertion_id=f"assertion:{observation_id}",
        space=space,
        visibility_scopes=(GLOBAL,),
        subject=GraphEntityRef(entity_id="profile:alice", entity_type="profile"),
        predicate="favorite_game",
        object=GraphValue(kind="literal", literal="Skyrim is my favorite game"),
        domain="preference",
        confidence=0.95,
        valid_from=T0,
        evidence_observation_ids=(observation_id,),
        derivation_version="runtime-test@2",
    )


def _request(space: MemorySpaceKey, *, suffix: str, text: str) -> ObservationAppendRequest:
    return ObservationAppendRequest(
        space=space,
        visibility_scope=GLOBAL,
        event_type="user_said",
        occurred_at=T0,
        provenance=ObservationProvenance(
            source_type="user",
            source_id="user:alice",
            trust_level="user_explicit",
            session_id="session:runtime",
            turn_id=f"turn:{suffix}",
            message_id=f"message:{suffix}",
        ),
        idempotency_key=f"runtime:{space.owner_id}:{suffix}",
        payload={"text": text},
    )


def _prepare(database: PostgresDatabase):
    _reset_authority(database)
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
    runtime = PostgresMemoryV2Runtime(database, authority_store=authority)
    space = MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=f"sofia-{uuid4().hex}",
    )
    first = observations.append(
        _request(space, suffix="1", text="Skyrim is my favorite game")
    )
    authority.advance_authoritative_event_watermark(space, first.authority_sequence)

    def derive(projector_space, window, _existing):
        assert projector_space == space
        return DerivedPlanPayload(
            assertions=tuple(_assertion(space, item.observation_id) for item in window),
            consolidator_version="runtime-test@2",
        )

    prepared = coordinator.prepare(space, derive)
    assert prepared is not None
    assert coordinator.commit(prepared).derived_revision == 1
    search.rebuild(space)
    graph_state = graph.state(space)
    shadow_result = RetrievalResult(
        query_id="shadow:runtime",
        candidates=(
            RetrievalCandidate(
                ref_id=f"assertion:{first.observation_id}",
                item_type="assertion",
                domain="preference",
                content="Skyrim is my favorite game",
                scores=RetrievalScore(semantic=1.0, composite=1.0),
                evidence_observation_ids=(first.observation_id,),
            ),
        ),
        dynamic_context=("Skyrim is my favorite game",),
        observation_watermark=1,
        graph_revision=graph_state.graph_revision,
        index_graph_revision=search.state(space).index_graph_revision,
        elapsed_ms=1.0,
        deadline_ms=50.0,
    )
    shadow_report = compare_shadow_retrieval(
        space=space,
        v1_contents=["Skyrim is my favorite game"],
        v2_result=shadow_result,
        observation_watermark=1,
        graph_revision=graph_state.graph_revision,
        required_recall=0.8,
        required_precision=0.8,
    )
    shadow.record(shadow_report)

    def replay(window):
        return tuple(_assertion(space, item.observation_id) for item in window)

    replay_report = GraphReplayValidator(graph, observations).validate(space, replay)
    receipt = authority.evaluate_space(space, graph_validation=replay_report)
    assert receipt.readiness.ready
    return runtime, authority, space, receipt.receipt_id, first.observation_id


def _query(space: MemorySpaceKey) -> RetrievalQuery:
    return RetrievalQuery(
        query_id="runtime:q",
        space=space,
        visible_scopes=(GLOBAL,),
        text="favorite game",
        authority="final",
        as_of=T0,
    )


def test_runtime_rejects_canonical_reads_and_writes_before_cutover() -> None:
    database = _database()
    try:
        apply_migrations(database)
        runtime, _authority, space, _receipt_id, _observation_id = _prepare(database)
        with pytest.raises(MemoryV2NotAuthoritativeError):
            runtime.retrieve(_query(space))
        with pytest.raises(MemoryV2NotAuthoritativeError):
            runtime.append_authoritative_next(
                _request(space, suffix="2", text="Second event")
            )
    finally:
        database.close()


def test_post_cutover_exact_runtime_enforces_sequence_and_idempotent_retry() -> None:
    database = _database()
    try:
        apply_migrations(database)
        runtime, authority, space, receipt_id, _observation_id = _prepare(database)
        authority.activate_v2((receipt_id,), activated_by="test:runtime")

        request = _request(space, suffix="2", text="Second event")
        committed = runtime.append_authoritative_exact(
            request,
            authoritative_event_sequence=2,
        )
        repeated = runtime.append_authoritative(
            request,
            authoritative_event_sequence=2,
        )
        assert committed.observation_id == repeated.observation_id
        assert committed.authority_sequence == 2
        assert runtime.observation_store.watermark(space) == 2
        assert authority.authoritative_event_watermark(space) == 2

        with pytest.raises(AuthoritativeIngestSequenceError):
            runtime.append_authoritative_exact(
                _request(space, suffix="4", text="Skipped sequence"),
                authoritative_event_sequence=4,
            )
    finally:
        database.close()


def test_post_cutover_next_allocates_sequence_and_idempotent_retry_consumes_none() -> None:
    database = _database()
    try:
        apply_migrations(database)
        runtime, authority, space, receipt_id, _observation_id = _prepare(database)
        authority.activate_v2((receipt_id,), activated_by="test:runtime")

        request = _request(space, suffix="next", text="Next event")
        committed = runtime.append_authoritative_next(request)
        repeated = runtime.append_authoritative_next(request)

        assert committed.observation_id == repeated.observation_id
        assert committed.authority_sequence == 2
        assert authority.authoritative_event_watermark(space) == 2
        third = runtime.append_authoritative_next(
            _request(space, suffix="third", text="Third event")
        )
        assert third.authority_sequence == 3
    finally:
        database.close()


def test_post_cutover_next_serializes_concurrent_writers_without_race_retries() -> None:
    database = _database()
    try:
        apply_migrations(database)
        runtime, authority, space, receipt_id, _observation_id = _prepare(database)
        authority.activate_v2((receipt_id,), activated_by="test:runtime")
        requests = (
            _request(space, suffix="parallel-a", text="Parallel event A"),
            _request(space, suffix="parallel-b", text="Parallel event B"),
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            committed = tuple(executor.map(runtime.append_authoritative_next, requests))

        assert {item.authority_sequence for item in committed} == {2, 3}
        assert len({item.observation_id for item in committed}) == 2
        assert runtime.observation_store.watermark(space) == 3
        assert authority.authoritative_event_watermark(space) == 3
    finally:
        database.close()


def test_operational_status_and_safe_immediate_rollback() -> None:
    database = _database()
    try:
        apply_migrations(database)
        runtime, authority, _space, receipt_id, _observation_id = _prepare(database)
        activated = authority.activate_v2((receipt_id,), activated_by="test:runtime")
        status = runtime.operational_status()
        assert status.authority == "v2"
        assert status.epoch == activated.epoch.epoch
        assert status.legacy_read_only is True
        assert status.v2_writes_allowed is True
        assert status.rollback_safe is True
        assert status.rollback_reasons == ()
        assert status.spaces[0].observation_to_derived_lag == 0
        assert status.spaces[0].derived_to_index_lag == 0

        rolled_back = runtime.rollback_to_v1(
            activated_by="test:rollback",
            reason="immediate validated rollback",
        )
        assert rolled_back.epoch.authority == "v1"
        assert rolled_back.epoch.previous_epoch == activated.epoch.epoch
    finally:
        database.close()


def test_rollback_refuses_to_discard_post_cutover_evidence() -> None:
    database = _database()
    try:
        apply_migrations(database)
        runtime, authority, space, receipt_id, _observation_id = _prepare(database)
        authority.activate_v2((receipt_id,), activated_by="test:runtime")
        runtime.append_authoritative_next(
            _request(space, suffix="2", text="Post-cutover evidence")
        )

        status = runtime.operational_status()
        assert status.rollback_safe is False
        assert status.spaces[0].observation_to_derived_lag == 1
        assert any("observation_log_advanced" in reason for reason in status.rollback_reasons)
        with pytest.raises(UnsafeMemoryRollbackError, match="discard"):
            runtime.rollback_to_v1(
                activated_by="test:rollback",
                reason="must fail",
            )
    finally:
        database.close()


def test_rollback_refuses_to_resurrect_post_cutover_governance_change() -> None:
    database = _database()
    try:
        apply_migrations(database)
        runtime, authority, space, receipt_id, observation_id = _prepare(database)
        authority.activate_v2((receipt_id,), activated_by="test:runtime")
        runtime.observation_store.set_disposition(
            space,
            observation_id,
            state="revoked",
            actor_id="test:privacy",
            reason="post-cutover privacy action",
        )

        status = runtime.operational_status()
        assert status.rollback_safe is False
        assert status.spaces[0].governance_to_derived_lag == 1
        assert any("governance_changed" in reason for reason in status.rollback_reasons)
        with pytest.raises(UnsafeMemoryRollbackError, match="resurrect"):
            runtime.rollback_to_v1(
                activated_by="test:rollback",
                reason="must fail",
            )
    finally:
        database.close()
