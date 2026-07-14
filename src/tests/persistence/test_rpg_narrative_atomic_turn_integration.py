from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.errors import RevisionConflict
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.rpg_turn_service import persist_foreground_turn
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


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=4,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-narrative-turn-atomic-tests",
        )
    )


def _create_campaign(database: PostgresDatabase, campaign_id: str) -> None:
    apply_migrations(database)
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        work.rpg.create_campaign(
            context,
            campaign_id=campaign_id,
            title="Narrative atomicity",
            state={"manifest": {"session_id": campaign_id}},
            engine_version="phase33",
            schema_version="phase33",
            seed="33",
        )
        work.commit()


def _session(campaign_id: str, revision: int) -> dict:
    return {
        "manifest": {
            "session_id": campaign_id,
            "title": "Narrative atomicity",
            "turn_count": revision,
        },
        "state": {"scene": {"location_name": "The Rusty Flagon"}},
        "runtime_state": {
            "state_revision": revision,
            "interaction_seq": revision,
        },
    }


def _event(revision: int) -> dict:
    return {
        "format_version": "rpg_interaction_timeline_v1",
        "interaction_id": f"interaction:phase33:{revision}",
        "sequence": revision,
        "state_revision": revision,
        "stateful": True,
        "player_input": "Listen to the rain.",
        "visible_response": {"plain_text": "Rain taps against the shutters."},
    }


def _canonical(campaign_id: str, revision: int) -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id=f"narrative:{campaign_id}:{revision}",
        request_id=f"request:{campaign_id}:{revision}",
        turn_id=f"runtime-turn:{revision}",
        campaign_id=campaign_id,
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id=f"block:{revision}",
                beat_id=f"beat:{revision}",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.DIRECT_ANSWER,
                text="Rain taps against the shutters.",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="phase33_fixture"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def test_canonical_response_and_turn_commit_in_one_postgresql_transaction() -> None:
    database = _database()
    campaign_id = "campaign:phase33:atomic"
    canonical = _canonical(campaign_id, 1)
    try:
        _create_campaign(database, campaign_id)
        persisted = persist_foreground_turn(
            database=database,
            session_id=campaign_id,
            player_input="Listen to the rain.",
            session=_session(campaign_id, 1),
            result={
                "ok": True,
                "canonical_narrative_response": canonical.as_dict(),
                "canonical_effects": {"observation": "rain"},
            },
            event=_event(1),
            submission_id="submission:phase33:atomic",
        )

        assert persisted["narrative_atomic_with_turn"] is True
        assert persisted["narrative_response_id"] == canonical.response_id
        assert persisted["narrative_content_hash"] == canonical.content_hash
        with database.connection() as connection:
            counts = connection.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM omnix_rpg_turns WHERE campaign_id = %s), "
                "(SELECT COUNT(*) FROM omnix_rpg_narrative_responses WHERE campaign_id = %s)",
                (campaign_id, campaign_id),
            ).fetchone()
            stored = connection.execute(
                "SELECT content_hash FROM omnix_rpg_narrative_responses "
                "WHERE campaign_id = %s AND response_id = %s",
                (campaign_id, canonical.response_id),
            ).fetchone()
        assert tuple(int(value) for value in counts) == (1, 1)
        assert str(stored[0]) == canonical.content_hash
    finally:
        database.close()


def test_turn_revision_failure_rolls_back_staged_canonical_response() -> None:
    database = _database()
    campaign_id = "campaign:phase33:rollback"
    canonical = _canonical(campaign_id, 2)
    try:
        _create_campaign(database, campaign_id)
        with pytest.raises(RevisionConflict):
            persist_foreground_turn(
                database=database,
                session_id=campaign_id,
                player_input="Listen to the rain.",
                session=_session(campaign_id, 2),
                result={
                    "ok": True,
                    "canonical_narrative_response": canonical.as_dict(),
                    "canonical_effects": {"observation": "rain"},
                },
                event=_event(2),
                submission_id="submission:phase33:rollback",
            )

        with database.connection() as connection:
            narrative_count = connection.execute(
                "SELECT COUNT(*) FROM omnix_rpg_narrative_responses WHERE campaign_id = %s",
                (campaign_id,),
            ).fetchone()[0]
            turn_count = connection.execute(
                "SELECT COUNT(*) FROM omnix_rpg_turns WHERE campaign_id = %s",
                (campaign_id,),
            ).fetchone()[0]
        assert int(narrative_count) == 0
        assert int(turn_count) == 0
    finally:
        database.close()
