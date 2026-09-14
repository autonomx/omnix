from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.assistant_memory.models import MemoryRecord
from app.assistant_memory_v2 import (
    MemorySpaceKey,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalScore,
)
from app.assistant_memory_v2.graph_store import (
    GraphReplayValidator,
    PostgresMemoryV2GraphStore,
)
from app.assistant_memory_v2.legacy_shadow import (
    LegacyMemoryV2Importer,
    PostgresMemoryV2ShadowEvaluationStore,
    compare_shadow_retrieval,
    legacy_seed_projector,
)
from app.assistant_memory_v2.observation_store import PostgresMemoryV2ObservationStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.migrations import apply_migrations

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc).isoformat()


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=12,
            connect_timeout_seconds=10,
            statement_timeout_ms=60_000,
            lock_timeout_ms=30_000,
            application_name="omnix-memory-v2-shadow-tests",
        )
    )


def _record(
    *,
    record_id: str,
    owner_id: str,
    content: str,
    kind: str = "preference",
    status: str = "active",
    revision: int = 1,
    trust_level: str = "user_approved",
) -> MemoryRecord:
    return MemoryRecord(
        id=record_id,
        owner_type="character",
        owner_id=owner_id,
        scope="global",
        scope_id="profile:alice",
        category="preference" if kind == "preference" else "fact",
        kind=kind,
        structured_payload={"legacy": True},
        source="user_saved",
        content=content,
        normalized_content=content.lower(),
        confidence=0.92,
        trust_level=trust_level,
        sensitivity="normal",
        provenance_type="user_message",
        provenance_id="message:legacy",
        status=status,
        revision=revision,
        created_at=NOW,
        updated_at=NOW,
    )


def test_import_preserves_v1_record_metadata_and_is_idempotent() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        importer = LegacyMemoryV2Importer(observations)
        record = _record(
            record_id=f"v1:{uuid4().hex}",
            owner_id=f"sofia-{uuid4().hex}",
            content="Skyrim is my favorite game",
            revision=4,
        )

        first = importer.import_record(principal_id="profile:alice", record=record)
        second = importer.import_record(principal_id="profile:alice", record=record)
        assert first is not None and second is not None
        assert first.observation_id == second.observation_id
        assert first.authority_sequence == second.authority_sequence == 1
        assert first.event_type == "imported_legacy_memory"
        assert first.payload["legacy_record"] == record.model_dump(mode="json")
        assert first.provenance.source_type == "migration"
        assert first.provenance.trust_level == "user_explicit"
        assert first.visibility_scope.kind == record.scope
        assert first.visibility_scope.scope_id == record.scope_id
    finally:
        database.close()


def test_nonactive_v1_records_are_not_imported() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        importer = LegacyMemoryV2Importer(observations)
        owner_id = f"sofia-{uuid4().hex}"
        archived = _record(
            record_id=f"v1:{uuid4().hex}",
            owner_id=owner_id,
            content="Old preference",
            status="archived",
        )
        assert importer.import_record(principal_id="profile:alice", record=archived) is None
        space = MemorySpaceKey(
            principal_id="profile:alice",
            owner_type="character",
            owner_id=owner_id,
        )
        assert observations.watermark(space) == 0
    finally:
        database.close()


def test_legacy_seed_projection_is_replayable_and_evidence_addressable() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        importer = LegacyMemoryV2Importer(observations)
        record = _record(
            record_id=f"v1:{uuid4().hex}",
            owner_id=f"sofia-{uuid4().hex}",
            content="Skyrim is my favorite game",
        )
        imported = importer.import_record(principal_id="profile:alice", record=record)
        assert imported is not None
        space = imported.space
        expected = legacy_seed_projector((imported,))
        assert len(expected) == 1
        assertion = expected[0]
        assert assertion.assertion_type == "seeded"
        assert assertion.object.literal == record.content
        assert assertion.evidence_observation_ids == (imported.observation_id,)

        graph.replace_space(
            space,
            expected,
            source_observation_watermark=observations.watermark(space),
        )
        replay = GraphReplayValidator(graph, observations).validate(space, legacy_seed_projector)
        assert replay.matches is True
        assert replay.persisted_count == replay.replay_count == 1
    finally:
        database.close()


def test_imported_records_remain_owner_isolated() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        importer = LegacyMemoryV2Importer(observations)
        sofia = _record(
            record_id=f"v1:{uuid4().hex}",
            owner_id=f"sofia-{uuid4().hex}",
            content="Sofia memory",
        )
        maya = _record(
            record_id=f"v1:{uuid4().hex}",
            owner_id=f"maya-{uuid4().hex}",
            content="Maya memory",
        )
        imported = importer.import_records(principal_id="profile:alice", records=[sofia, maya])
        assert len(imported) == 2
        assert imported[0].space != imported[1].space
        assert len(observations.list(imported[0].space)) == 1
        assert len(observations.list(imported[1].space)) == 1
    finally:
        database.close()


def test_shadow_quality_report_is_persisted_with_authority_watermarks() -> None:
    database = _database()
    try:
        apply_migrations(database)
        observations = PostgresMemoryV2ObservationStore(database)
        graph = PostgresMemoryV2GraphStore(database)
        importer = LegacyMemoryV2Importer(observations)
        record = _record(
            record_id=f"v1:{uuid4().hex}",
            owner_id=f"sofia-{uuid4().hex}",
            content="Skyrim is my favorite game",
        )
        observation = importer.import_record(principal_id="profile:alice", record=record)
        assert observation is not None
        space = observation.space
        graph.replace_space(
            space,
            legacy_seed_projector((observation,)),
            source_observation_watermark=observations.watermark(space),
        )
        state = graph.state(space)
        result = RetrievalResult(
            query_id="shadow:q1",
            candidates=(
                RetrievalCandidate(
                    ref_id="legacy:candidate",
                    item_type="assertion",
                    domain="preference",
                    content="profile alice legacy preference Skyrim is my favorite game",
                    scores=RetrievalScore(semantic=1.0, composite=1.0),
                    evidence_observation_ids=(observation.observation_id,),
                ),
            ),
            dynamic_context=("profile alice legacy preference Skyrim is my favorite game",),
            observation_watermark=observations.watermark(space),
            graph_revision=state.graph_revision,
            index_graph_revision=0,
            elapsed_ms=1.0,
            deadline_ms=50,
        )
        report = compare_shadow_retrieval(
            space=space,
            v1_contents=[record.content],
            v2_result=result,
            observation_watermark=observations.watermark(space),
            graph_revision=state.graph_revision,
            similarity_threshold=0.5,
            required_recall=0.8,
        )
        assert report.passed is True
        assert report.recall == 1.0
        store = PostgresMemoryV2ShadowEvaluationStore(
            database,
            graph_store=graph,
            observation_store=observations,
        )
        store.record(report)
        assert store.latest(space) == report
    finally:
        database.close()
