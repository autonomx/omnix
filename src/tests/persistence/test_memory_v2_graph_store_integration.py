from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from app.assistant_memory_v2 import (
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemorySpaceKey,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory_v2.graph_store import (
    GraphEvidenceError,
    GraphReplayValidator,
    PostgresMemoryV2GraphStore,
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
            pool_max=10,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-graph-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_memory_v2_assertion_relations, "
            "omnix_memory_v2_assertion_assertion_evidence, "
            "omnix_memory_v2_assertion_observation_evidence, "
            "omnix_memory_v2_graph_assertions, omnix_memory_v2_graph_entities, "
            "omnix_memory_v2_graph_state, omnix_memory_v2_observation_dispositions, "
            "omnix_memory_v2_observations, omnix_memory_v2_authority_streams CASCADE"
        )


def _space(owner: str = "sofia") -> MemorySpaceKey:
    return MemorySpaceKey(principal_id="profile:alice", owner_type="character", owner_id=owner)


def _append(store: PostgresMemoryV2ObservationStore, index: int, space: MemorySpaceKey | None = None):
    return store.append(
        ObservationAppendRequest(
            space=space or _space(),
            visibility_scope=VisibilityScope(kind="global", scope_id="global"),
            event_type="user_said",
            occurred_at=datetime(2026, 9, 13, 12, index, tzinfo=timezone.utc),
            provenance=ObservationProvenance(
                source_type="user", source_id="user:alice", trust_level="user_explicit"
            ),
            idempotency_key=f"turn:{(space or _space()).owner_id}:{index}",
            payload={"predicate": "favorite_game", "value": f"game-{index}"},
        )
    )


def _assertion(observation, *, assertion_id: str | None = None, status: str = "active", supersedes=()):
    return GraphAssertion(
        assertion_id=assertion_id or f"assert:{observation.observation_id}",
        space=observation.space,
        visibility_scopes=(observation.visibility_scope,),
        subject=GraphEntityRef(entity_id="user:alice", entity_type="user"),
        predicate=str(observation.payload["predicate"]),
        object=GraphValue(kind="literal", literal=observation.payload["value"]),
        domain="preference",
        assertion_type="derived",
        confidence=0.95,
        valid_from=observation.occurred_at,
        evidence_observation_ids=(observation.observation_id,),
        derivation_version="test-projector@1",
        supersedes=tuple(supersedes),
        status=status,
    )


def _project(observations):
    return tuple(_assertion(item) for item in observations)


def test_graph_revision_and_evidence_edges_are_durable() -> None:
    database = _database()
    try:
        _reset(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        first = _append(observations, 1)
        second = _append(observations, 2)

        assert graph.put(_assertion(first), source_observation_watermark=1) == 1
        assert graph.put(_assertion(second), source_observation_watermark=2) == 2
        state = graph.state(_space())
        assert state.graph_revision == 2
        assert state.source_observation_watermark == 2
        persisted = graph.list_assertions(_space())
        assert [item.assertion_id for item in persisted] == sorted(
            [f"assert:{first.observation_id}", f"assert:{second.observation_id}"]
        )
        assert graph.dependent_assertion_ids(_space(), first.observation_id) == (
            f"assert:{first.observation_id}",
        )
    finally:
        database.close()


def test_cross_space_and_inactive_evidence_cannot_back_active_assertion() -> None:
    database = _database()
    try:
        _reset(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        _append(observations, 0, _space("sofia"))
        maya_observation = _append(observations, 1, _space("maya"))
        bad = _assertion(maya_observation).model_copy(update={"space": _space("sofia")})
        with pytest.raises(GraphEvidenceError, match="not found"):
            graph.put(bad)

        sofia_observation = _append(observations, 2)
        observations.set_disposition(
            _space(), sofia_observation.observation_id, state="revoked", actor_id="user:alice"
        )
        with pytest.raises(GraphEvidenceError, match="inactive evidence"):
            graph.put(_assertion(sofia_observation))
    finally:
        database.close()


def test_supersession_is_structured_and_historical_state_survives() -> None:
    database = _database()
    try:
        _reset(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        old_obs = _append(observations, 1)
        new_obs = _append(observations, 2)
        old = _assertion(old_obs, assertion_id="favorite:old", status="superseded")
        graph.put(old, source_observation_watermark=1)
        new = _assertion(new_obs, assertion_id="favorite:new", supersedes=("favorite:old",))
        graph.put(new, source_observation_watermark=2)

        persisted = {item.assertion_id: item for item in graph.list_assertions(_space())}
        assert persisted["favorite:old"].status == "superseded"
        assert persisted["favorite:new"].supersedes == ("favorite:old",)
        assert persisted["favorite:new"].evidence_observation_ids == (new_obs.observation_id,)
    finally:
        database.close()


def test_replay_validator_detects_divergence_and_rebuilds_from_observations() -> None:
    database = _database()
    try:
        _reset(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        validator = GraphReplayValidator(graph, observations)
        _append(observations, 1)
        _append(observations, 2)

        before = validator.validate(_space(), _project)
        assert before.matches is False
        assert before.persisted_count == 0
        assert before.replay_count == 2

        after = validator.rebuild(_space(), _project)
        assert after.matches is True
        assert after.persisted_count == after.replay_count == 2
        assert graph.state(_space()).source_observation_watermark == observations.watermark(_space()) == 2

        third = _append(observations, 3)
        assert third.authority_sequence == 3
        diverged = validator.validate(_space(), _project)
        assert diverged.matches is False
        repaired = validator.rebuild(_space(), _project)
        assert repaired.matches is True
        assert repaired.persisted_count == 3
    finally:
        database.close()


def test_graph_replay_is_character_isolated() -> None:
    database = _database()
    try:
        _reset(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        validator = GraphReplayValidator(graph, observations)
        _append(observations, 1, _space("sofia"))
        _append(observations, 1, _space("maya"))
        assert validator.rebuild(_space("sofia"), _project).matches
        assert validator.rebuild(_space("maya"), _project).matches
        assert len(graph.list_assertions(_space("sofia"))) == 1
        assert len(graph.list_assertions(_space("maya"))) == 1
        assert graph.state(_space("sofia")).graph_revision == 1
        assert graph.state(_space("maya")).graph_revision == 1
    finally:
        database.close()
