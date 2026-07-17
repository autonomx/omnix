from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
    resolve_campaign_binding,
)
from app.rpg.worlds.starter_bubble_service import promote_starter_bubble

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
            application_name="omnix-rpg-starter-bubble-promotion",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_world_generation_runs, "
            "omnix_rpg_campaign_map_events, omnix_rpg_campaign_map_instances, "
            "omnix_rpg_map_definitions, omnix_rpg_campaign_world_bindings, "
            "omnix_rpg_scenario_revisions, omnix_rpg_scenarios, "
            "omnix_rpg_world_releases, omnix_rpg_world_revisions, "
            "omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_job_attempts, "
            "omnix_job_events, omnix_jobs, omnix_outbox_events, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def test_promotion_creates_future_revision_without_rebinding_existing_campaign() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        source_revision = compile_world_revision(
            world_id="world:starter",
            revision=1,
            title="Starter World",
            canon={"campaign_template": "classic_fantasy"},
            entity_manifest={"locations": ["location:harbor"]},
            topology={"locations": ["location:harbor"], "routes": []},
        )
        source_release = compile_world_release(
            source_revision,
            release=1,
            certification={"launch_ready": True, "missing_requirements": []},
        )
        source_scenario = compile_scenario_revision(
            scenario_id="scenario:source",
            revision=1,
            world_revision=source_revision,
            compatible_release=1,
            starting_location_id="location:harbor",
        )
        source_binding = resolve_campaign_binding(
            campaign_id="campaign:source",
            world_revision=source_revision,
            world_release=source_release,
            scenario_revision=source_scenario,
        )

        with unit_of_work(database) as work:
            work.world_scenarios.create_world(
                context,
                world_id="world:starter",
                title="Starter World",
                source_mode="hybrid",
                genre="classic_fantasy",
                tone="heroic adventure",
                metadata={"starting_location": "location:harbor"},
            )
            work.world_scenarios.publish_world_revision(
                context,
                world_id="world:starter",
                document=source_revision.model_dump(mode="json"),
                content_hash=source_revision.content_hash,
                expected_revision=0,
            )
            work.world_scenarios.publish_world_release(
                context,
                world_id="world:starter",
                world_revision=1,
                document=source_release.model_dump(mode="json"),
                release_hash=source_release.release_hash,
            )
            work.world_scenarios.create_scenario(
                context,
                scenario_id="scenario:source",
                world_id="world:starter",
                title="Source Scenario",
                metadata={},
            )
            work.world_scenarios.publish_scenario_revision(
                context,
                scenario_id="scenario:source",
                world_id="world:starter",
                world_revision=1,
                document=source_scenario.model_dump(mode="json"),
                content_hash=source_scenario.content_hash,
            )
            work.rpg.create_campaign(
                context,
                campaign_id="campaign:source",
                title="Pinned Source Campaign",
                state={},
                engine_version="test",
                schema_version="test",
                seed="1",
                metadata={},
            )
            work.world_scenarios.bind_campaign(
                context,
                campaign_id="campaign:source",
                world_id=source_binding.world_id,
                world_revision=source_binding.world_revision,
                world_release=source_binding.world_release,
                scenario_id=source_binding.scenario_id,
                scenario_revision=source_binding.scenario_revision,
                binding=source_binding.model_dump(mode="json"),
            )
            work.commit()

        promoted = promote_starter_bubble(
            world_id="world:starter",
            source_world_revision=1,
            starting_location_id="location:harbor",
            neighboring_location_id="location:old-road",
            database=database,
        )
        repeated = promote_starter_bubble(
            world_id="world:starter",
            source_world_revision=1,
            starting_location_id="location:harbor",
            neighboring_location_id="location:old-road",
            database=database,
        )

        assert promoted["ok"] is True
        assert promoted["status"] == "ready"
        assert promoted["reused"] is False
        promotion = promoted["promotion"]
        assert promotion["world_revision"] == 2
        assert promotion["world_release"] == 1
        assert len(promotion["map_bindings"]) == 3
        assert all(
            binding["simulation_readiness"] == "navigable"
            for binding in promotion["map_bindings"]
        )
        assert promotion["certification"]["starter_bubble"]["simulation_certified"] is True
        assert promotion["certification"]["presentation_readiness"] == "assets_pending"
        assert promotion["certification"]["optional_art_blocks_gameplay"] is False
        assert repeated["reused"] is True
        assert repeated["promotion"]["world_revision"] == 2

        with unit_of_work(database) as work:
            original_revision = work.world_scenarios.get_world_revision(
                context,
                "world:starter",
                1,
            )
            future_revision = work.world_scenarios.get_world_revision(
                context,
                "world:starter",
                2,
            )
            future_release = work.world_scenarios.get_world_release(
                context,
                "world:starter",
                2,
                1,
            )
            campaign_binding = work.world_scenarios.get_campaign_binding(
                context,
                "campaign:source",
            )
            definition_count = work.connection.execute(
                "SELECT COUNT(*) FROM omnix_rpg_map_definitions "
                "WHERE workspace_id = %s AND world_id = %s AND world_revision = 2",
                (context.workspace_id, "world:starter"),
            ).fetchone()[0]
            work.rollback()

        assert original_revision is not None
        assert original_revision["content_hash"] == source_revision.content_hash
        assert future_revision is not None
        assert future_release is not None
        assert len(future_release["document"]["map_bindings"]) == 3
        assert definition_count == 3
        assert campaign_binding is not None
        assert campaign_binding["world_revision"] == 1
        assert campaign_binding["world_release"] == 1
        assert campaign_binding["map_definition_pins"] == {}
    finally:
        database.close()
