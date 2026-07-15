from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.rpg_narrative_retirement_repository import (
    NarrativeRetirementConflict,
)
from app.persistence.unit_of_work import unit_of_work
from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    NarrativeBlock,
    ValidationReport,
)
from app.rpg.narrative_engine.legacy_retirement import (
    production_legacy_retirement_audit,
)
from app.rpg.narrative_engine.publisher_guard import CANONICAL_PUBLISHER
from app.rpg.narrative_repository import (
    PostgresNarrativeResponseRepositoryAdapter,
)
from app.rpg.narrative_retirement import (
    PostgresNarrativeRetirementRepositoryAdapter,
)


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-rpg-narrative-retirement-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_narrative_retirement_records, "
            "omnix_rpg_narrative_deliveries, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_outbox_events, "
            "omnix_audit_events, omnix_workspace_memberships, omnix_workspaces, "
            "omnix_users CASCADE"
        )


def _response() -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:phase41:postgres",
        request_id="request:phase41:postgres",
        turn_id="turn:phase41:postgres",
        campaign_id="campaign:phase41:postgres",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id="response:phase41:postgres:block",
                beat_id="beat:phase41:postgres",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.CONTINUATION,
                text="Canonical publication is the sole visible owner.",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="phase41-postgres"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def test_postgresql_retirement_records_are_idempotent_and_release_certifiable() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                context,
                campaign_id="campaign:phase41:postgres",
                title="Phase 41",
                state={"runtime_state": {"state_revision": 0}},
                engine_version="rne-phase41",
                schema_version="rpg-session-v1",
                seed="fixed",
            )
            work.commit()

        responses = PostgresNarrativeResponseRepositoryAdapter(
            database,
            context_provider=lambda value: context,
        )
        retirement = PostgresNarrativeRetirementRepositoryAdapter(
            database,
            context_provider=lambda value: context,
        )
        response = responses.save(_response())
        audit = production_legacy_retirement_audit().as_dict()
        payload = {
            "response_id": response.response_id,
            "content_hash": response.semantic_hash,
            "publisher": CANONICAL_PUBLISHER,
            "canonical_publish_count": 1,
            "alternate_publish_count": 0,
            "rejected_alternate_count": 0,
            "legacy_ownership_retired": True,
            "compatibility_projection_only": True,
            "delivery_mode": "blocking",
            "production_certification": {
                "passed": True,
                "response_id": response.response_id,
                "content_hash": response.semantic_hash,
            },
            "deletion_audit": audit,
            "metadata": {"turn_id": response.turn_id},
        }
        first = retirement.put(**payload)
        replay = retirement.put(**{**payload, "canonical_publish_count": 2})

        assert first["content_hash"] == response.semantic_hash
        assert replay["canonical_publish_count"] == 2
        assert replay["alternate_publish_count"] == 0
        assert replay["legacy_ownership_retired"] is True
        assert replay["deletion_audit"]["passed"] is True
        loaded = retirement.get(response.response_id)
        assert loaded == replay
        snapshot = retirement.release_snapshot()
        assert snapshot["record_count"] == 1
        assert snapshot["canonical_publish_count"] == 2
        assert snapshot["zero_alternate_publishers"] is True
        assert snapshot["legacy_publisher_deletion_certified"] is True

        with pytest.raises(
            NarrativeRetirementConflict,
            match="zero alternate publishers",
        ):
            retirement.put(**{**payload, "alternate_publish_count": 1})
        with pytest.raises(
            NarrativeRetirementConflict,
            match="content hash differs",
        ):
            retirement.put(**{**payload, "content_hash": "sha256:wrong"})
    finally:
        database.close()
