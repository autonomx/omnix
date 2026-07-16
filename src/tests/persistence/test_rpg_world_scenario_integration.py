from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.worlds.contracts import MapDefinitionBinding
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
    resolve_campaign_binding,
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
            application_name="omnix-rpg-world-scenario-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_campaign_world_bindings, "
            "omnix_rpg_scenario_revisions, omnix_rpg_scenarios, "
            "omnix_rpg_world_releases, omnix_rpg_world_revisions, "
            "omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_outbox_events, "
            "omnix_audit_events, omnix_workspace_memberships, omnix_workspaces, "
            "omnix_users CASCADE"
        )


def test_world_release_scenario_and_campaign_binding_are_transactional() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        world = compile_world_revision(
            world_id="world:shared",
            revision=1,
            title="Shared World",
            canon={"realm": {"name": "Shared World"}},
            entity_manifest={"locations": [{"id": "location:tavern"}]},
            topology={"locations": ["location:tavern"], "routes": []},
            blueprint_requirements=[{"map_id": "interior:tavern"}],
        )
        release = compile_world_release(
            world,
            release=1,
            map_bindings=[
                MapDefinitionBinding(
                    map_id="interior:tavern",
                    blueprint_revision=1,
                    definition_revision=1,
                    definition_hash="sha256:" + "c" * 64,
                    semantic_interface_hash="sha256:" + "d" * 64,
                )
            ],
            certification={"passed": True},
        )
        scenario = compile_scenario_revision(
            scenario_id="scenario:tavern_start",
            revision=1,
            world_revision=world,
            compatible_release=1,
            starting_location_id="location:tavern",
        )
        binding = resolve_campaign_binding(
            campaign_id="campaign:shared:a",
            world_revision=world,
            world_release=release,
            scenario_revision=scenario,
        )

        with unit_of_work(database) as work:
            work.world_scenarios.create_world(
                context,
                world_id="world:shared",
                title="Shared World",
            )
            stored_world = work.world_scenarios.publish_world_revision(
                context,
                world_id="world:shared",
                document=world.model_dump(mode="json"),
                content_hash=world.content_hash,
                expected_revision=0,
            )
            stored_release = work.world_scenarios.publish_world_release(
                context,
                world_id="world:shared",
                world_revision=1,
                document=release.model_dump(mode="json"),
                release_hash=release.release_hash,
            )
            work.world_scenarios.create_scenario(
                context,
                scenario_id="scenario:tavern_start",
                world_id="world:shared",
                title="Tavern Start",
            )
            stored_scenario = work.world_scenarios.publish_scenario_revision(
                context,
                scenario_id="scenario:tavern_start",
                world_id="world:shared",
                world_revision=1,
                document=scenario.model_dump(mode="json"),
                content_hash=scenario.content_hash,
            )
            work.rpg.create_campaign(
                context,
                campaign_id="campaign:shared:a",
                title="Campaign A",
                state={"title": "Campaign A"},
                engine_version="world-scenario-v1",
                schema_version="rpg-session-v1",
                seed="0",
                metadata={},
            )
            stored_binding = work.world_scenarios.bind_campaign(
                context,
                campaign_id=binding.campaign_id,
                world_id=binding.world_id,
                world_revision=binding.world_revision,
                world_release=binding.world_release,
                scenario_id=binding.scenario_id,
                scenario_revision=binding.scenario_revision,
                binding=binding.model_dump(mode="json"),
            )
            work.commit()

        assert stored_world["revision"] == 1
        assert stored_release["release"] == 1
        assert stored_scenario["revision"] == 1
        assert stored_binding["world_revision_hash"] == world.content_hash

        with unit_of_work(database) as work:
            read_binding = work.world_scenarios.get_campaign_binding(
                context, "campaign:shared:a"
            )
            read_world = work.world_scenarios.get_world_revision(
                context, "world:shared", 1
            )
            work.rollback()
        assert read_binding == stored_binding
        assert read_world is not None
        assert read_world["content_hash"] == world.content_hash
    finally:
        database.close()
