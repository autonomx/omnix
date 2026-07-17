from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.session.genesis.world_forge_contract import CampaignTopicGraph, CampaignTopicNode
from app.rpg.worlds.contracts import (
    ScenarioProjectCreate,
    WorldProjectCreate,
    WorldReleaseDocument,
)
from app.rpg.worlds.generation_coordinator import start_world_generation
from app.rpg.worlds.generation_jobs import WorldTopicGenerationSettings
from app.rpg.worlds.library_service import save_world_topic, start_world_library_generation
from app.rpg.worlds.lifecycle_service import (
    archive_scenario_project,
    archive_world_project,
    restore_scenario_project,
    restore_world_project,
)
from app.rpg.worlds.postgres_service import (
    bind_campaign_world,
    create_scenario_project,
    create_world_project,
    publish_scenario_revision,
    publish_world_release,
    publish_world_revision,
)
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
            application_name="omnix-rpg-world-lifecycle",
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


def _published_fixture(database: PostgresDatabase) -> tuple[str, str, str]:
    world_id = "world:lifecycle"
    scenario_id = "scenario:lifecycle"
    campaign_id = "campaign:lifecycle"
    create_world_project(
        WorldProjectCreate(world_id=world_id, title="Lifecycle World"),
        database=database,
    )
    world = compile_world_revision(
        world_id=world_id,
        revision=1,
        title="Lifecycle World",
        canon={},
        entity_manifest={},
        topology={"locations": ["location:start"], "routes": []},
    )
    publish_world_revision(world, expected_revision=0, database=database)
    release = compile_world_release(
        world,
        release=1,
        certification={"launch_ready": False, "missing_requirements": []},
    )
    stored_release = publish_world_release(release, database=database)
    certified_release = WorldReleaseDocument.model_validate(stored_release["document"])
    create_scenario_project(
        ScenarioProjectCreate(
            scenario_id=scenario_id,
            world_id=world_id,
            title="Lifecycle Opening",
        ),
        database=database,
    )
    scenario = compile_scenario_revision(
        scenario_id=scenario_id,
        revision=1,
        world_revision=world,
        compatible_release=None,
        starting_location_id="location:start",
    )
    publish_scenario_revision(scenario, database=database)
    binding = resolve_campaign_binding(
        campaign_id=campaign_id,
        world_revision=world,
        world_release=certified_release,
        scenario_revision=scenario,
    )
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        work.rpg.create_campaign(
            context,
            campaign_id=campaign_id,
            title="Retained Campaign",
            state={"status": "active"},
            engine_version="lifecycle-test",
            schema_version="rpg-session-v1",
            seed="0",
            metadata={},
        )
        work.commit()
    bind_campaign_world(binding, database=database)
    return world_id, scenario_id, campaign_id


def test_archive_preserves_published_authority_and_blocks_new_writes() -> None:
    database = _database()
    try:
        _reset(database)
        world_id, scenario_id, campaign_id = _published_fixture(database)
        context = bootstrap_local_tenant(database)

        archived_scenario = archive_scenario_project(scenario_id, database=database)
        archived_world = archive_world_project(world_id, database=database)
        repeated_world = archive_world_project(world_id, database=database)

        assert archived_scenario["scenario"]["status"] == "archived"
        assert archived_world["world"]["status"] == "archived"
        assert repeated_world["idempotent"] is True
        with pytest.raises(ValueError, match=f"world_archived:{world_id}"):
            save_world_topic(
                world_id,
                topic_id="realm",
                content={"topic_id": "realm"},
                database=database,
            )
        with pytest.raises(ValueError, match=f"world_archived:{world_id}"):
            start_world_library_generation(
                world_id,
                database=database,
                kick_worker=False,
            )
        with pytest.raises(ValueError, match=f"world_archived:{world_id}"):
            create_scenario_project(
                ScenarioProjectCreate(
                    scenario_id="scenario:blocked",
                    world_id=world_id,
                    title="Blocked",
                ),
                database=database,
            )

        with unit_of_work(database) as work:
            retained_world = work.world_scenarios.get_world_revision(
                context,
                world_id,
                1,
            )
            retained_release = work.world_scenarios.get_world_release(
                context,
                world_id,
                1,
                1,
            )
            retained_scenario = work.world_scenarios.get_scenario_revision(
                context,
                scenario_id,
                1,
            )
            retained_binding = work.world_scenarios.get_campaign_binding(
                context,
                campaign_id,
            )
            retained_campaign = work.rpg.get_campaign(context, campaign_id)
            work.rollback()
        assert retained_world is not None
        assert retained_release is not None
        assert retained_scenario is not None
        assert retained_binding is not None
        assert retained_campaign is not None

        restored_world = restore_world_project(world_id, database=database)
        restored_scenario = restore_scenario_project(scenario_id, database=database)
        assert restored_world["world"]["status"] == "published"
        assert restored_scenario["scenario"]["status"] == "published"
        assert restore_world_project(world_id, database=database)["idempotent"] is True
        assert restore_scenario_project(scenario_id, database=database)["idempotent"] is True
    finally:
        database.close()


def test_world_archive_rejects_active_durable_generation() -> None:
    database = _database()
    try:
        _reset(database)
        world_id = "world:active-generation"
        create_world_project(
            WorldProjectCreate(world_id=world_id, title="Active Generation"),
            database=database,
        )
        graph = CampaignTopicGraph(
            graph_version="lifecycle-test-v1",
            campaign_template="classic_fantasy",
            depth="quick",
            nodes=(
                CampaignTopicNode(
                    topic_id="realm",
                    title="Realm",
                    category="lore",
                    generator_role="realm_architect",
                ),
            ),
        )
        start_world_generation(
            world_id=world_id,
            draft_revision=1,
            graph=graph,
            generation_context={},
            topic_directives={},
            entity_manifest_hash="sha256:manifest",
            settings=WorldTopicGenerationSettings(
                generator_version="test-v1",
                prompt_version="test-v1",
                provider_route="deterministic",
                model="deterministic",
                seed=1,
            ),
            database=database,
        )

        with pytest.raises(ValueError, match="world_generation_active"):
            archive_world_project(world_id, database=database)
    finally:
        database.close()
