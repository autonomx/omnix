from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.session.genesis.compiler import compile_campaign_genesis
from app.rpg.session.genesis.contract import CampaignGenesisContract
from app.rpg.session.genesis.materialization import persist_campaign_genesis
from app.rpg.session.genesis.world_forge_pipeline import run_campaign_world_forge


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
            application_name="omnix-rpg-campaign-genesis-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_outbox_events, "
            "omnix_audit_events, omnix_workspace_memberships, omnix_workspaces, "
            "omnix_users CASCADE"
        )


def test_campaign_genesis_materializes_bible_and_ready_gate_atomically() -> None:
    database = _database()
    try:
        _reset(database)
        contract = CampaignGenesisContract.model_validate(
            {
                "campaign_template": "summoned_heroes",
                "genre": "portal_fantasy",
                "tone": "fractured mythic fantasy",
                "world_options": {"starting_location": "vanta_gate", "seed": 17},
                "world_forge": {"depth": "quick"},
            }
        )
        compiled = compile_campaign_genesis(contract)
        world_forge = run_campaign_world_forge(
            contract,
            campaign_id="campaign:genesis",
            compiled_genesis=compiled,
        )
        assert world_forge.launch_ready is True
        session = {
            "manifest": {
                "session_id": "campaign:genesis",
                "title": "Genesis",
                "schema_version": "rpg-session-v1",
            },
            "state": {"title": "Genesis", "runtime_state": {"state_revision": 0}},
        }
        persisted = persist_campaign_genesis(
            session,
            contract,
            world_forge,
            database=database,
            required=True,
        )
        assert persisted["persisted"] is True
        assert persisted["campaign_bible"]["revision"] == 1
        assert persisted["genesis"]["status"] == "ready"
        assert persisted["genesis"]["progress"]["launch_ready"] is True

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            bible = work.campaign_bibles.get(context, "campaign:genesis")
            genesis = work.campaign_genesis.get(context, "campaign:genesis")
            campaign = work.rpg.get_campaign(context, "campaign:genesis")
            work.rollback()
        assert campaign is not None
        assert bible is not None and bible["document"]["entities"]["npc:vexira_umbra"]
        assert genesis is not None and genesis["bible_content_hash"] == bible["content_hash"]
    finally:
        database.close()
