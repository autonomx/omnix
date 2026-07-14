from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.rpg_campaign_bible_repository import (
    CampaignBibleRevisionConflict,
    campaign_bible_hash,
)
from app.persistence.unit_of_work import unit_of_work


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
            application_name="omnix-rpg-campaign-bible-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_campaign_bible_revisions, "
            "omnix_rpg_campaign_bibles, omnix_rpg_participants, "
            "omnix_rpg_snapshots, omnix_rpg_interactions, omnix_rpg_turns, "
            "omnix_rpg_campaigns, omnix_outbox_events, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def _campaign(work, context) -> None:
    work.rpg.create_campaign(
        context,
        campaign_id="campaign:bible",
        title="Campaign Bible",
        state={"runtime_state": {"state_revision": 0}},
        engine_version="rne-test",
        schema_version="rpg-session-v1",
        seed="fixed",
    )


def test_campaign_bible_is_revisioned_hashed_and_compare_and_swap_guarded() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        document_v1 = {
            "facts": [
                {
                    "id": "fact:bran:occupation",
                    "content": "Bran keeps the Rusty Flagon.",
                    "authority": "canon",
                    "visibility": "public",
                    "entity_refs": ["npc:bran", "location:rusty_flagon"],
                }
            ],
            "entities": {"npc:bran": {"name": "Bran"}},
        }
        with unit_of_work(database) as work:
            _campaign(work, context)
            first = work.campaign_bibles.put(
                context,
                campaign_id="campaign:bible",
                document=document_v1,
                expected_revision=0,
                provenance={"source": "world_forge", "proposal_id": "proposal:1"},
                consistency_report={"passed": True, "issues": []},
                completeness={"required_sections": 4, "completed_sections": 2},
            )
            work.commit()

        assert first["revision"] == 1
        assert first["content_hash"] == campaign_bible_hash(document_v1)
        assert first["provenance"]["proposal_id"] == "proposal:1"

        document_v2 = {
            **document_v1,
            "relationships": [
                {
                    "id": "relationship:bran:flagon",
                    "content": "Bran is responsible for the Rusty Flagon.",
                    "authority": "canon",
                    "visibility": "public",
                    "entity_refs": ["npc:bran", "location:rusty_flagon"],
                }
            ],
        }
        with unit_of_work(database) as work:
            second = work.campaign_bibles.put(
                context,
                campaign_id="campaign:bible",
                document=document_v2,
                expected_revision=1,
            )
            history = work.campaign_bibles.revisions(context, "campaign:bible")
            work.commit()

        assert second["revision"] == 2
        assert [row["revision"] for row in history] == [2, 1]
        assert history[0]["content_hash"] == campaign_bible_hash(document_v2)

        with unit_of_work(database) as work:
            with pytest.raises(CampaignBibleRevisionConflict):
                work.campaign_bibles.put(
                    context,
                    campaign_id="campaign:bible",
                    document={"facts": []},
                    expected_revision=1,
                )
            work.rollback()

        with unit_of_work(database) as work:
            current = work.campaign_bibles.get(context, "campaign:bible")
            work.rollback()
        assert current is not None
        assert current["revision"] == 2
        assert current["document"] == document_v2
    finally:
        database.close()
