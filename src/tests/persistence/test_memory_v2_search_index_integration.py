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
from app.assistant_memory_v2.graph_store import PostgresMemoryV2GraphStore
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


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=12,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-search-index-tests",
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


def _assertion(
    space: MemorySpaceKey,
    observation_id: str,
    value: str,
    *,
    assertion_id: str,
    scope: VisibilityScope | None = None,
):
    return GraphAssertion(
        assertion_id=assertion_id,
        space=space,
        visibility_scopes=(scope or VisibilityScope(kind="global", scope_id="global"),),
        subject=GraphEntityRef(entity_id="user:alice", entity_type="user"),
        predicate="favorite_game",
        object=GraphValue(kind="literal", literal=value),
        domain="preference",
        confidence=0.95,
        evidence_observation_ids=(observation_id,),
        derivation_version="phase9-test@1",
    )


def test_rebuild_projects_active_graph_and_searches_by_scope() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        index = PostgresMemoryV2SearchIndex(database)
        space = _space("search")
        first = _append(observations, space, 1)
        second = _append(observations, space, 2)
        graph.put(
            _assertion(
                space,
                first.observation_id,
                "Cyberpunk 2077",
                assertion_id="assert:cyberpunk",
            ),
            source_observation_watermark=2,
        )
        graph.put(
            _assertion(
                space,
                second.observation_id,
                "Skyrim",
                assertion_id="assert:project-only",
                scope=VisibilityScope(kind="project", scope_id="project:secret"),
            ),
            source_observation_watermark=2,
        )

        state = index.rebuild(space)
        assert state.index_graph_revision == graph.state(space).graph_revision
        assert state.source_observation_watermark == observations.watermark(space) == 2
        assert state.entry_count == 2
        assert index.status(space).stale is False

        hits = index.search(
            space,
            "cyberpunk",
            visible_scopes=(VisibilityScope(kind="global", scope_id="global"),),
        )
        assert [item.ref_id for item in hits] == ["assert:cyberpunk"]
        hidden = index.search(
            space,
            "skyrim",
            visible_scopes=(VisibilityScope(kind="global", scope_id="global"),),
        )
        assert hidden == []
    finally:
        database.close()


def test_graph_change_marks_index_stale_until_rebuild() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        index = PostgresMemoryV2SearchIndex(database)
        space = _space("stale-graph")
        first = _append(observations, space, 1)
        graph.put(
            _assertion(space, first.observation_id, "Skyrim", assertion_id="assert:one"),
            source_observation_watermark=1,
        )
        index.rebuild(space)
        assert index.status(space).stale is False

        second = _append(observations, space, 2)
        graph.put(
            _assertion(space, second.observation_id, "Cyberpunk", assertion_id="assert:two"),
            source_observation_watermark=2,
        )
        status = index.status(space)
        assert status.stale is True
        assert "graph_revision_mismatch" in status.reasons
        assert "observation_watermark_mismatch" in status.reasons

        index.rebuild(space)
        assert index.status(space).stale is False
    finally:
        database.close()


def test_governance_change_is_immediately_fail_closed_and_marks_index_stale() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        index = PostgresMemoryV2SearchIndex(database)
        space = _space("governance")
        observation = _append(observations, space, 1)
        graph.put(
            _assertion(
                space,
                observation.observation_id,
                "Cyberpunk",
                assertion_id="assert:revoked",
            ),
            source_observation_watermark=1,
        )
        index.rebuild(space)
        assert index.search(
            space,
            "cyberpunk",
            visible_scopes=(VisibilityScope(kind="global", scope_id="global"),),
        )

        observations.set_disposition(
            space,
            observation.observation_id,
            state="revoked",
            actor_id="privacy:alice",
        )
        status = index.status(space)
        assert status.stale is True
        assert status.reasons == ("governance_changed",)
        assert index.search(
            space,
            "cyberpunk",
            visible_scopes=(VisibilityScope(kind="global", scope_id="global"),),
        ) == []

        rebuilt = index.rebuild(space)
        assert rebuilt.entry_count == 0
        assert index.status(space).stale is False
    finally:
        database.close()


def test_search_index_spaces_are_character_isolated() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        index = PostgresMemoryV2SearchIndex(database)
        sofia = _space("sofia")
        maya = _space("maya")
        sofia_observation = _append(observations, sofia, 1)
        maya_observation = _append(observations, maya, 1)
        graph.put(
            _assertion(
                sofia,
                sofia_observation.observation_id,
                "Cyberpunk",
                assertion_id="assert:sofia",
            ),
            source_observation_watermark=1,
        )
        graph.put(
            _assertion(
                maya,
                maya_observation.observation_id,
                "Cyberpunk",
                assertion_id="assert:maya",
            ),
            source_observation_watermark=1,
        )
        index.rebuild(sofia)
        index.rebuild(maya)

        scopes = (VisibilityScope(kind="global", scope_id="global"),)
        assert [item.ref_id for item in index.search(sofia, "cyberpunk", visible_scopes=scopes)] == [
            "assert:sofia"
        ]
        assert [item.ref_id for item in index.search(maya, "cyberpunk", visible_scopes=scopes)] == [
            "assert:maya"
        ]
    finally:
        database.close()
