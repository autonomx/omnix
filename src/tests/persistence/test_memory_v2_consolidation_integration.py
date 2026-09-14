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
    VisibilityScope,
)
from app.assistant_memory_v2.consolidation import (
    ConsolidationPlan,
    PostgresMemoryV2Consolidator,
)
from app.assistant_memory_v2.graph_store import GraphEvidenceError, PostgresMemoryV2GraphStore
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
            pool_max=24,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-consolidation-tests",
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
            payload={"value": f"value-{index}"},
        )
    )


def _project(space, observations, existing):
    del existing
    assertions = tuple(
        GraphAssertion(
            assertion_id=f"assert:{item.observation_id}",
            space=space,
            visibility_scopes=(item.visibility_scope,),
            subject=GraphEntityRef(entity_id="user:alice", entity_type="user"),
            predicate="test_value",
            object=GraphValue(kind="literal", literal=item.payload["value"]),
            domain="fact",
            confidence=1.0,
            valid_from=item.occurred_at,
            evidence_observation_ids=(item.observation_id,),
            derivation_version="phase3-test@1",
        )
        for item in observations
    )
    return ConsolidationPlan(assertions=assertions)


def test_consolidation_commits_graph_receipt_and_watermark_together() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        consolidator = PostgresMemoryV2Consolidator(database, graph_store=graph, observation_store=observations)
        space = _space("atomic")
        _append(observations, space, 1)
        _append(observations, space, 2)

        receipt = consolidator.consolidate(space, _project, consolidator_version="phase3-test@1")
        assert receipt is not None
        assert (receipt.input_observation_from, receipt.input_observation_through) == (1, 2)
        assert receipt.resulting_graph_revision == 1
        assert len(receipt.created_assertion_ids) == 2
        assert consolidator.watermark(space) == observations.watermark(space) == 2
        assert graph.state(space).source_observation_watermark == 2
        assert len(graph.list_assertions(space)) == 2
        assert consolidator.latest_receipt(space) == receipt
    finally:
        database.close()


def test_retry_with_no_new_observations_is_idempotent() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        consolidator = PostgresMemoryV2Consolidator(database, graph_store=graph, observation_store=observations)
        space = _space("retry")
        _append(observations, space, 1)

        first = consolidator.consolidate(space, _project, consolidator_version="phase3-test@1")
        assert first is not None
        assert consolidator.consolidate(space, _project, consolidator_version="phase3-test@1") is None
        assert graph.state(space).graph_revision == 1
        assert consolidator.latest_receipt(space).receipt_id == first.receipt_id
    finally:
        database.close()


def test_concurrent_consolidators_commit_one_effective_window() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        consolidator = PostgresMemoryV2Consolidator(database, graph_store=graph, observation_store=observations)
        space = _space("race")
        for index in range(1, 11):
            _append(observations, space, index)

        with ThreadPoolExecutor(max_workers=16) as executor:
            receipts = list(
                executor.map(
                    lambda _: consolidator.consolidate(
                        space,
                        _project,
                        consolidator_version="phase3-test@1",
                    ),
                    range(32),
                )
            )
        committed = [item for item in receipts if item is not None]
        assert len(committed) == 1
        assert committed[0].input_observation_through == 10
        assert consolidator.watermark(space) == 10
        assert graph.state(space).graph_revision == 1
        assert len(graph.list_assertions(space)) == 10
    finally:
        database.close()


def test_failed_graph_plan_rolls_back_receipt_graph_and_watermark() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        consolidator = PostgresMemoryV2Consolidator(database, graph_store=graph, observation_store=observations)
        space = _space("rollback")
        observation = _append(observations, space, 1)

        def invalid_projector(target, window, existing):
            del window, existing
            return ConsolidationPlan(
                assertions=(
                    GraphAssertion(
                        assertion_id=f"bad:{uuid4().hex}",
                        space=target,
                        visibility_scopes=(VisibilityScope(kind="global", scope_id="global"),),
                        subject=GraphEntityRef(entity_id="user:alice", entity_type="user"),
                        predicate="bad",
                        object=GraphValue(kind="literal", literal="bad"),
                        domain="fact",
                        confidence=1.0,
                        evidence_observation_ids=(f"missing:{observation.observation_id}",),
                        derivation_version="phase3-test@1",
                    ),
                )
            )

        with pytest.raises(GraphEvidenceError):
            consolidator.consolidate(space, invalid_projector, consolidator_version="phase3-test@1")
        assert consolidator.watermark(space) == 0
        assert graph.state(space).graph_revision == 0
        assert graph.list_assertions(space) == []
        assert consolidator.latest_receipt(space) is None
    finally:
        database.close()


def test_consolidation_spaces_are_isolated() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        consolidator = PostgresMemoryV2Consolidator(database, graph_store=graph, observation_store=observations)
        sofia = _space("sofia")
        maya = _space("maya")
        _append(observations, sofia, 1)
        _append(observations, maya, 1)
        assert consolidator.consolidate(sofia, _project, consolidator_version="phase3-test@1")
        assert consolidator.consolidate(maya, _project, consolidator_version="phase3-test@1")
        assert consolidator.watermark(sofia) == consolidator.watermark(maya) == 1
        assert len(graph.list_assertions(sofia)) == len(graph.list_assertions(maya)) == 1
    finally:
        database.close()
