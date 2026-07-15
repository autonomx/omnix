from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.rpg_world_forge_service import approve_world_forge_proposal
from app.persistence.unit_of_work import unit_of_work
from app.rpg.narrative_engine import WorldForgeProposal, audit_world_forge_proposal, CampaignBibleSnapshot


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
            application_name="omnix-rpg-world-forge-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_outbox_events, "
            "omnix_audit_events, omnix_workspace_memberships, omnix_workspaces, "
            "omnix_users CASCADE"
        )


def test_world_forge_proposal_is_reviewed_and_applied_atomically() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            work.rpg.create_campaign(
                context,
                campaign_id="campaign:forge",
                title="World Forge",
                state={"runtime_state": {"state_revision": 0}},
                engine_version="rne-test",
                schema_version="rpg-session-v1",
                seed="fixed",
            )
            bible = work.campaign_bibles.put(
                context,
                campaign_id="campaign:forge",
                document={
                    "entities": {
                        "npc:bran": {"id": "npc:bran", "name": "Bran"},
                    },
                    "facts": [],
                },
                expected_revision=0,
            )
            proposal = WorldForgeProposal(
                proposal_id="proposal:east-road",
                campaign_id="campaign:forge",
                base_bible_revision=bible["revision"],
                entities=(
                    {"id": "location:east_road", "name": "East Road"},
                ),
                facts=(
                    {
                        "id": "fact:east-road:condition",
                        "content": "The East Road is muddy but passable.",
                        "authority": "generated_proposal",
                        "entity_refs": ["location:east_road"],
                    },
                ),
                provenance={"generator": "world_forge_v1"},
            )
            audit = audit_world_forge_proposal(
                CampaignBibleSnapshot.from_record(bible),
                proposal,
            )
            created = work.world_forge.create(
                context,
                proposal_id=proposal.proposal_id,
                campaign_id=proposal.campaign_id,
                base_bible_revision=proposal.base_bible_revision,
                proposal=proposal.as_dict(),
                consistency_report=audit.as_dict(),
            )
            result = approve_world_forge_proposal(
                work,
                context,
                proposal_id=proposal.proposal_id,
                expected_bible_revision=1,
                decision_note="Approved in integration test.",
            )
            work.commit()

        assert created["status"] == "proposed"
        assert result["approved"] is True
        assert result["proposal"]["status"] == "approved"
        assert result["campaign_bible"]["revision"] == 2
        fact = result["campaign_bible"]["document"]["facts"][0]
        assert fact["authority"] == "objective_canon"
        assert fact["approved_from_proposal"] == "proposal:east-road"

        with database.connection() as connection:
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM omnix_rpg_world_forge_proposals), "
                "(SELECT COUNT(*) FROM omnix_rpg_campaign_bible_revisions)"
            ).fetchone()
        assert tuple(int(value) for value in counts) == (1, 2)
    finally:
        database.close()
