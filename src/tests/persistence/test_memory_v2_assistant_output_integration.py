from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.assistant_memory_v2 import (
    GraphEntityRef,
    GraphValue,
    MemorySpaceKey,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory_v2.assistant_output import (
    AssistantOutputLifecycleError,
    PostgresMemoryV2AssistantOutputLifecycle,
)
from app.assistant_memory_v2.observation_store import PostgresMemoryV2ObservationStore
from app.assistant_memory_v2.semantic_enrichment import (
    SemanticMemoryProposal,
    VoiceMemDerivedSemanticEnricher,
)
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

T0 = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
GLOBAL = VisibilityScope(kind="global", scope_id="global")
USER = GraphEntityRef(entity_id="user:alice", entity_type="user")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=12,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-assistant-output-tests",
        )
    )


def _space(prefix: str) -> MemorySpaceKey:
    return MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id=f"{prefix}-{uuid4().hex}",
    )


def _assistant_provenance(turn: str = "turn:1") -> ObservationProvenance:
    return ObservationProvenance(
        source_type="assistant",
        source_id="assistant:sofia",
        trust_level="assistant_inference",
        session_id="session:1",
        turn_id=turn,
    )


def _extractor(observation):
    text = str(observation.payload.get("text", ""))
    if "Skyrim" in text:
        yield SemanticMemoryProposal(
            subject=USER,
            predicate="assistant_shared_game",
            domain="relationship",
            effective_at=observation.occurred_at,
            value=GraphValue(kind="literal", literal="Skyrim"),
            confidence=0.9,
        )


def test_interruption_persists_only_experienced_prefix_as_semantic_evidence() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        lifecycle = PostgresMemoryV2AssistantOutputLifecycle(database, observation_store=observations)
        space = _space("sofia")
        correlation_id = f"output:{uuid4().hex}"
        full = "Skyrim is a great game. I also recommend Cyberpunk."
        heard = "Skyrim is a great game."

        lifecycle.record_generated(
            space=space,
            visibility_scope=GLOBAL,
            correlation_id=correlation_id,
            text=full,
            occurred_at=T0,
            provenance=_assistant_provenance(),
        )
        lifecycle.record_delivered(
            space=space,
            correlation_id=correlation_id,
            text=full,
            occurred_at=T0 + timedelta(milliseconds=50),
            provenance=_assistant_provenance(),
        )
        state = lifecycle.update_experienced_prefix(
            space=space,
            correlation_id=correlation_id,
            text=heard,
        )
        assert state.experienced_prefix == heard
        finalized, experienced = lifecycle.finalize_experience(
            space=space,
            correlation_id=correlation_id,
            occurred_at=T0 + timedelta(seconds=1),
            provenance=_assistant_provenance(),
        )

        assert finalized.finalized is True
        assert experienced is not None
        assert experienced.event_type == "assistant_experienced"
        assert experienced.payload["text"] == heard

        events = observations.list(space)
        assert [item.event_type for item in events] == [
            "assistant_generated",
            "assistant_delivered",
            "assistant_experienced",
        ]
        enricher = VoiceMemDerivedSemanticEnricher(_extractor)
        plan = enricher.project(space, tuple(events), ())
        assert len(plan.assertions) == 1
        assert plan.assertions[0].evidence_observation_ids == (experienced.observation_id,)
    finally:
        database.close()


def test_zero_heard_output_finalizes_without_experienced_observation() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        lifecycle = PostgresMemoryV2AssistantOutputLifecycle(database, observation_store=observations)
        space = _space("zero")
        correlation_id = f"output:{uuid4().hex}"

        lifecycle.record_generated(
            space=space,
            visibility_scope=GLOBAL,
            correlation_id=correlation_id,
            text="This was never heard.",
            occurred_at=T0,
            provenance=_assistant_provenance(),
        )
        lifecycle.record_delivered(
            space=space,
            correlation_id=correlation_id,
            text="This was never heard.",
            occurred_at=T0 + timedelta(milliseconds=10),
            provenance=_assistant_provenance(),
        )
        finalized, experienced = lifecycle.finalize_experience(
            space=space,
            correlation_id=correlation_id,
            occurred_at=T0 + timedelta(milliseconds=20),
            provenance=_assistant_provenance(),
        )

        assert finalized.finalized is True
        assert finalized.experienced_prefix == ""
        assert finalized.experienced_observation_id is None
        assert experienced is None
        assert [item.event_type for item in observations.list(space)] == [
            "assistant_generated",
            "assistant_delivered",
        ]
    finally:
        database.close()


def test_prefix_boundaries_and_monotonic_playback_progress_are_enforced() -> None:
    database = _database()
    try:
        apply_migrations(database)
        lifecycle = PostgresMemoryV2AssistantOutputLifecycle(database)
        space = _space("prefix")
        correlation_id = f"output:{uuid4().hex}"
        lifecycle.record_generated(
            space=space,
            visibility_scope=GLOBAL,
            correlation_id=correlation_id,
            text="one two three",
            occurred_at=T0,
            provenance=_assistant_provenance(),
        )
        with pytest.raises(AssistantOutputLifecycleError, match="prefix of generated"):
            lifecycle.record_delivered(
                space=space,
                correlation_id=correlation_id,
                text="two three",
                occurred_at=T0,
                provenance=_assistant_provenance(),
            )

        lifecycle.record_delivered(
            space=space,
            correlation_id=correlation_id,
            text="one two",
            occurred_at=T0,
            provenance=_assistant_provenance(),
        )
        lifecycle.update_experienced_prefix(
            space=space,
            correlation_id=correlation_id,
            text="one",
        )
        with pytest.raises(AssistantOutputLifecycleError, match="cannot move backward"):
            lifecycle.update_experienced_prefix(
                space=space,
                correlation_id=correlation_id,
                text="",
            )
        with pytest.raises(AssistantOutputLifecycleError, match="prefix of delivered"):
            lifecycle.update_experienced_prefix(
                space=space,
                correlation_id=correlation_id,
                text="one three",
            )
    finally:
        database.close()


def test_lifecycle_retries_are_idempotent_and_finalization_is_stable() -> None:
    database = _database()
    try:
        apply_migrations(database)
        lifecycle = PostgresMemoryV2AssistantOutputLifecycle(database)
        space = _space("retry")
        correlation_id = f"output:{uuid4().hex}"
        kwargs = dict(
            space=space,
            visibility_scope=GLOBAL,
            correlation_id=correlation_id,
            text="Skyrim",
            occurred_at=T0,
            provenance=_assistant_provenance(),
        )
        first_state, first_observation = lifecycle.record_generated(**kwargs)
        second_state, second_observation = lifecycle.record_generated(**kwargs)
        assert first_observation.observation_id == second_observation.observation_id
        assert first_state == second_state

        first_delivery = lifecycle.record_delivered(
            space=space,
            correlation_id=correlation_id,
            text="Skyrim",
            occurred_at=T0 + timedelta(milliseconds=10),
            provenance=_assistant_provenance(),
        )
        second_delivery = lifecycle.record_delivered(
            space=space,
            correlation_id=correlation_id,
            text="Skyrim",
            occurred_at=T0 + timedelta(milliseconds=10),
            provenance=_assistant_provenance(),
        )
        assert first_delivery[1].observation_id == second_delivery[1].observation_id

        lifecycle.update_experienced_prefix(
            space=space,
            correlation_id=correlation_id,
            text="Skyrim",
        )
        first_final = lifecycle.finalize_experience(
            space=space,
            correlation_id=correlation_id,
            occurred_at=T0 + timedelta(seconds=1),
            provenance=_assistant_provenance(),
        )
        second_final = lifecycle.finalize_experience(
            space=space,
            correlation_id=correlation_id,
            occurred_at=T0 + timedelta(seconds=1),
            provenance=_assistant_provenance(),
        )
        assert first_final == second_final
    finally:
        database.close()


def test_output_lifecycle_is_character_isolated() -> None:
    database = _database()
    try:
        apply_migrations(database)
        lifecycle = PostgresMemoryV2AssistantOutputLifecycle(database)
        sofia = _space("sofia")
        maya = _space("maya")
        correlation_id = f"output:{uuid4().hex}"
        lifecycle.record_generated(
            space=sofia,
            visibility_scope=GLOBAL,
            correlation_id=correlation_id,
            text="Sofia output",
            occurred_at=T0,
            provenance=_assistant_provenance(),
        )
        assert lifecycle.get(sofia, correlation_id) is not None
        assert lifecycle.get(maya, correlation_id) is None
        with pytest.raises(AssistantOutputLifecycleError, match="generated output"):
            lifecycle.record_delivered(
                space=maya,
                correlation_id=correlation_id,
                text="Sofia output",
                occurred_at=T0,
                provenance=_assistant_provenance(),
            )
    finally:
        database.close()
