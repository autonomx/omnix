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
from app.rpg.narrative_engine.certification import certify_narrative_roundtrip


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
            application_name="omnix-rpg-narrative-response-tests",
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
        response_id="response:persisted",
        request_id="request:persisted",
        turn_id="turn:persisted",
        campaign_id="campaign:persisted",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id="block:persisted",
                beat_id="beat:persisted",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.RESOLVED_ACTION,
                text="The lantern catches against the wet stones.",
            ),
        ),
        evidence_used=("evidence:lantern",),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="fixture", beat_count=1),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def test_postgresql_save_load_and_turn_lookup_preserve_canonical_hash() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        response = _response()
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                context,
                campaign_id=response.campaign_id,
                title="Narrative Persistence",
                state={"runtime_state": {"state_revision": 0}},
                engine_version="rne-test",
                schema_version="rpg-session-v1",
                seed="fixed",
            )
            saved = work.narrative_responses.save(context, response)
            replayed = work.narrative_responses.save(context, response)
            work.commit()

        assert saved.content_hash == response.content_hash
        assert replayed.content_hash == response.content_hash
        with unit_of_work(database) as work:
            loaded = work.narrative_responses.get(context, response.response_id)
            by_turn = work.narrative_responses.get_for_turn(
                context,
                response.campaign_id,
                response.turn_id,
            )
            rows = work.narrative_responses.list_campaign(context, response.campaign_id)
            work.rollback()

        assert loaded is not None and by_turn is not None
        assert loaded.as_dict() == response.as_dict()
        assert by_turn.as_dict() == response.as_dict()
        assert [row.response_id for row in rows] == [response.response_id]
        assert certify_narrative_roundtrip(loaded).passed is True
    finally:
        database.close()
