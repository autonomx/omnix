"""The Memory v2 shadow-comparison report reads cutover state per space (WP-8.5)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.assistant_memory.v2 import MemorySpaceKey, RetrievalResult
from app.assistant_memory.v2.graph_store import PostgresMemoryV2GraphStore
from app.assistant_memory.v2.legacy_shadow import (
    LegacyMemoryV2Importer,
    PostgresMemoryV2ShadowEvaluationStore,
    compare_shadow_retrieval,
)
from app.assistant_memory.v2.observation_store import PostgresMemoryV2ObservationStore
from app.assistant_memory.v2.shadow_report import build_shadow_report, main
from app.conversation.memory_contracts import MemoryRecord
from app.persistence.migrations import apply_migrations
from app.persistence.tenant_scope import system_scope
from tests.persistence.test_memory_v2_authority_cutover_integration import (
    _database,
    _prepare_ready_space,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc).isoformat()


def _record(owner_id: str, content: str) -> MemoryRecord:
    return MemoryRecord(
        id=f"v1:{uuid4().hex}",
        owner_type="character",
        owner_id=owner_id,
        scope="global",
        scope_id="profile:alice",
        category="preference",
        kind="preference",
        structured_payload={},
        source="user_saved",
        content=content,
        normalized_content=content.lower(),
        confidence=0.9,
        trust_level="user_approved",
        sensitivity="normal",
        provenance_type="user_message",
        provenance_id="message:legacy",
        status="active",
        revision=1,
        created_at=NOW,
        updated_at=NOW,
    )


def _space_status(database, space: MemorySpaceKey):
    report = build_shadow_report(database)
    return next(
        item for item in report.spaces
        if (item.principal_id, item.owner_type, item.owner_id)
        == (space.principal_id, space.owner_type, space.owner_id)
    )


def _insert_v1(database, record: MemoryRecord) -> None:
    """Store the record in v1 too, so the report sees v2 in step with v1."""
    with system_scope("operator.cli"), database.transaction() as connection:
        workspace_id = connection.execute("SELECT id FROM omnix_workspaces ORDER BY id LIMIT 1").fetchone()[0]
        connection.execute(
            """
            INSERT INTO omnix_memory_records (
                id, workspace_id, owner_type, owner_id, scope, scope_id, category, kind,
                content, normalized_content, source, trust_level, provenance_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (record.id, workspace_id, record.owner_type, record.owner_id, record.scope, record.scope_id,
             record.category, record.kind, record.content, record.normalized_content, record.source,
             record.trust_level, record.provenance_type),
        )


def _delete_v1(database, owner_id: str) -> None:
    with system_scope("operator.cli"), database.transaction() as connection:
        connection.execute("DELETE FROM omnix_memory_records WHERE owner_id = %s", (owner_id,))


def _imported_space(database, content: str = "Skyrim is my favorite game"):
    observations = PostgresMemoryV2ObservationStore(database)
    record = _record(f"sofia-{uuid4().hex}", content)
    observation = LegacyMemoryV2Importer(observations).import_record(principal_id="profile:alice", record=record)
    assert observation is not None
    return observations, observation.space, record


def _record_failing_evaluation(database, observations, space, *, v1_contents) -> None:
    """v2 retrieves nothing, so recall is zero."""
    graph = PostgresMemoryV2GraphStore(database)
    revision = graph.state(space).graph_revision
    result = RetrievalResult(
        query_id="shadow:report",
        candidates=(),
        dynamic_context=(),
        observation_watermark=observations.watermark(space),
        graph_revision=revision,
        index_graph_revision=0,
        elapsed_ms=1.0,
        deadline_ms=50,
    )
    report = compare_shadow_retrieval(
        space=space,
        v1_contents=list(v1_contents),
        v2_result=result,
        observation_watermark=observations.watermark(space),
        graph_revision=revision,
    )
    PostgresMemoryV2ShadowEvaluationStore(
        database, graph_store=graph, observation_store=observations,
    ).record(report)


def test_a_space_with_a_current_ready_receipt_is_ready() -> None:
    database = _database()
    try:
        apply_migrations(database)
        _authority, space, receipt_id, _observation_id = _prepare_ready_space(database)

        status = _space_status(database, space)

        assert status.status == "ready"
        assert status.readiness is not None and status.readiness.receipt_id == receipt_id
        assert status.evaluation is not None and status.evaluation.passed is True
        assert status.evaluation.recall == 1.0
    finally:
        database.close()


def test_a_receipt_behind_the_authoritative_feed_is_not_ready() -> None:
    database = _database()
    try:
        apply_migrations(database)
        authority, space, _receipt_id, _observation_id = _prepare_ready_space(database)
        authority.advance_authoritative_event_watermark(space, 2)

        status = _space_status(database, space)

        assert status.authoritative_event_watermark == 2
        assert status.status == "not_ready"
    finally:
        database.close()


def test_an_imported_space_without_an_evaluation_is_not_evaluated() -> None:
    database = _database()
    try:
        apply_migrations(database)
        _observations, space, _record_value = _imported_space(database)

        status = _space_status(database, space)

        assert status.status == "not_evaluated"
        assert status.evaluation is None and status.readiness is None
        assert status.observation_watermark == 1
    finally:
        database.close()


def test_failed_and_stale_evaluations_are_reported() -> None:
    database = _database()
    space = None
    try:
        apply_migrations(database)
        observations, space, record = _imported_space(database)
        _insert_v1(database, record)
        _record_failing_evaluation(database, observations, space, v1_contents=[record.content])
        assert _space_status(database, space).status == "shadow_failed"

        second = _record(space.owner_id, "Morrowind is my second favorite")
        _insert_v1(database, second)
        LegacyMemoryV2Importer(observations).import_record(principal_id="profile:alice", record=second)
        status = _space_status(database, space)
        assert status.status == "evaluation_stale"
        assert status.evaluation is not None and status.evaluation.observation_watermark == 1
        assert status.observation_watermark == 2
    finally:
        if space is not None:
            _delete_v1(database, space.owner_id)
        database.close()


def test_a_v1_change_after_import_is_reported_before_staleness() -> None:
    database = _database()
    space = None
    try:
        apply_migrations(database)
        observations, space, record = _imported_space(database)
        _insert_v1(database, record)
        _record_failing_evaluation(database, observations, space, v1_contents=[record.content])
        assert _space_status(database, space).status == "shadow_failed"

        _insert_v1(database, _record(space.owner_id, "Oblivion is my third favorite"))
        assert _space_status(database, space).status == "v1_changed"

        _delete_v1(database, space.owner_id)
        assert _space_status(database, space).status == "v1_changed"
    finally:
        if space is not None:
            _delete_v1(database, space.owner_id)
        database.close()


def test_v1_owners_without_a_v2_space_are_listed_as_unimported(capsys) -> None:
    database = _database()
    owner_id = f"maya-{uuid4().hex}"
    try:
        apply_migrations(database)
        with system_scope("operator.cli"), database.transaction() as connection:
            workspace_id = connection.execute("SELECT id FROM omnix_workspaces ORDER BY id LIMIT 1").fetchone()[0]
            connection.execute(
                """
                INSERT INTO omnix_memory_records (
                    id, workspace_id, owner_type, owner_id, scope, scope_id,
                    category, content, normalized_content, source
                ) VALUES (%s, %s, 'character', %s, 'global', 'profile:alice',
                          'preference', 'Tea over coffee', 'tea over coffee', 'user_saved')
                """,
                (f"v1:{uuid4().hex}", workspace_id, owner_id),
            )

        report = build_shadow_report(database)

        unimported = {(owner.owner_type, owner.owner_id): owner for owner in report.unimported_v1_owners}
        if report.unimported_v1_owner_count <= len(report.unimported_v1_owners):
            assert unimported[("character", owner_id)].active_v1_records == 1
        assert report.unimported_v1_owner_count >= 1
        assert report.all_spaces_ready is False
        assert sum(report.status_counts.values()) == len(report.spaces)

        assert main(["--require-ready"]) == 1
        printed = json.loads(capsys.readouterr().out)
        assert printed["authority"] in {"v1", "v2"}
        assert printed["unimported_v1_owner_count"] >= 1
    finally:
        with system_scope("operator.cli"), database.transaction() as connection:
            connection.execute("DELETE FROM omnix_memory_records WHERE owner_id = %s", (owner_id,))
        database.close()
