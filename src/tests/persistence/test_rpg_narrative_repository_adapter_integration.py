from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
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
from app.rpg.narrative_repository import (
    PostgresNarrativeResponseRepositoryAdapter,
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
            application_name="omnix-rpg-narrative-adapter-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_narrative_responses, omnix_rpg_hermes_research, "
            "omnix_rpg_world_forge_proposals, omnix_rpg_campaign_bible_revisions, "
            "omnix_rpg_campaign_bibles, omnix_rpg_participants, omnix_rpg_snapshots, "
            "omnix_rpg_interactions, omnix_rpg_turns, omnix_rpg_campaigns, "
            "omnix_outbox_events, omnix_audit_events, omnix_workspace_memberships, "
            "omnix_workspaces, omnix_users CASCADE"
        )


def _response() -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:phase31:integration",
        request_id="request:phase31:integration",
        turn_id="turn:phase31:integration",
        campaign_id="campaign:phase31:integration",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id="block:phase31:integration",
                beat_id="beat:phase31:integration",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.RESOLVED_ACTION,
                text="The canonical response persists before publication.",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="integration"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def test_adapter_persists_and_reloads_exact_canonical_response() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        response = _response()
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                context,
                campaign_id=response.campaign_id,
                title="Phase 31",
                state={"runtime_state": {"state_revision": 0}},
                engine_version="rne-phase31",
                schema_version="rpg-session-v1",
                seed="fixed",
            )
            work.commit()

        adapter = PostgresNarrativeResponseRepositoryAdapter(
            database,
            context_provider=lambda value: context,
        )
        saved = adapter.save(response)
        replayed = adapter.save(response)
        loaded = adapter.get(response.response_id)
        by_turn = adapter.get_for_turn(response.campaign_id, response.turn_id)
        rows = adapter.list_campaign(response.campaign_id)

        assert saved.as_dict() == response.as_dict()
        assert replayed.as_dict() == response.as_dict()
        assert loaded is not None and loaded.as_dict() == response.as_dict()
        assert by_turn is not None and by_turn.as_dict() == response.as_dict()
        assert [row.response_id for row in rows] == [response.response_id]
    finally:
        database.close()
