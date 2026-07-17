from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.worlds.contracts import (
    MapInitializationOperation,
    ScenarioProjectCreate,
    WorldProjectCreate,
)
from app.rpg.worlds.map_blueprint_authoring import (
    MapBlueprintDocument,
    latest_ready_blueprint_requirements,
    list_map_blueprints,
    save_map_blueprint,
)
from app.rpg.worlds.map_blueprint_publication import merge_authored_blueprints
from app.rpg.worlds.postgres_service import (
    create_scenario_project,
    create_world_project,
    publish_scenario_revision,
    publish_world_revision,
)
from app.rpg.worlds.service import (
    compile_scenario_revision,
    compile_world_release,
    compile_world_revision,
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
            application_name="omnix-rpg-map-blueprint-authoring",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_map_blueprint_revisions, "
            "omnix_rpg_world_topic_history, omnix_rpg_world_generation_runs, "
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


def test_blueprint_reconciliation_and_publication_provenance() -> None:
    database = _database()
    try:
        _reset(database)
        world_id = "world:blueprint-editor"
        map_id = "map:harbor"
        create_world_project(
            WorldProjectCreate(world_id=world_id, title="Blueprint World"),
            database=database,
        )
        world = compile_world_revision(
            world_id=world_id,
            revision=1,
            title="Blueprint World",
            canon={},
            entity_manifest={},
            topology={"locations": ["location:harbor"], "routes": []},
        )
        publish_world_revision(world, expected_revision=0, database=database)
        create_scenario_project(
            ScenarioProjectCreate(
                scenario_id="scenario:blueprint",
                world_id=world_id,
                title="Harbor Opening",
            ),
            database=database,
        )
        scenario = compile_scenario_revision(
            scenario_id="scenario:blueprint",
            revision=1,
            world_revision=world,
            starting_location_id="location:harbor",
            map_initialization=(
                MapInitializationOperation(
                    operation_id="init:captain",
                    map_id=map_id,
                    type="place_actor",
                    target_id="npc:captain",
                    payload={"spawn_point_id": "spawn:office"},
                ),
                MapInitializationOperation(
                    operation_id="init:gate",
                    map_id=map_id,
                    type="set_object_state",
                    target_id="gate:eastern",
                    payload={"state": "closed"},
                ),
            ),
        )
        publish_scenario_revision(scenario, database=database)

        invalid = save_map_blueprint(
            world_id,
            MapBlueprintDocument(
                map_id=map_id,
                location_id="location:harbor",
                level="settlement",
            ),
            expected_revision=0,
            database=database,
        )["map_blueprint"]
        assert invalid["status"] == "invalid"
        assert {finding["code"] for finding in invalid["findings"]} == {
            "starting_location_spawn_required",
            "scenario_spawn_missing",
            "scenario_object_missing",
        }

        corrected = save_map_blueprint(
            world_id,
            MapBlueprintDocument(
                map_id=map_id,
                location_id="location:harbor",
                level="settlement",
                required_spawn_point_ids=("spawn:arrival", "spawn:office"),
                required_object_ids=("gate:eastern",),
                required_zone_ids=("zone:harbor_core",),
                directives={"style": "storm-battered port"},
            ),
            expected_revision=1,
            database=database,
        )["map_blueprint"]
        assert corrected["status"] == "ready"
        assert corrected["findings"] == []
        assert corrected["blueprint_revision"] == 2
        assert corrected["content_hash"].startswith("sha256:")
        assert corrected["semantic_interface_hash"].startswith("sha256:")
        with pytest.raises(ValueError, match="map_blueprint_revision_conflict"):
            save_map_blueprint(
                world_id,
                MapBlueprintDocument(
                    map_id=map_id,
                    location_id="location:harbor",
                    level="settlement",
                    required_spawn_point_ids=("spawn:arrival",),
                ),
                expected_revision=1,
                database=database,
            )

        latest = list_map_blueprints(world_id, database=database)
        history = list_map_blueprints(
            world_id,
            latest_only=False,
            database=database,
        )
        assert latest == [corrected]
        assert [row["blueprint_revision"] for row in history] == [2, 1]

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            requirements = latest_ready_blueprint_requirements(
                work,
                context,
                world_id,
            )
            work.rollback()
        base_release = compile_world_release(
            world,
            release=1,
            certification={"launch_ready": False, "missing_requirements": []},
        )
        published_world, published_release = merge_authored_blueprints(
            world,
            base_release,
            requirements,
        )
        requirement = published_world.blueprint_requirements[0]
        assert requirement["map_id"] == map_id
        assert requirement["blueprint_revision"] == 2
        assert requirement["blueprint_hash"] == corrected["content_hash"]
        assert requirement["semantic_interface_hash"] == (
            corrected["semantic_interface_hash"]
        )
        assert requirement["required_spawn_point_ids"] == [
            "spawn:arrival",
            "spawn:office",
        ]
        assert published_world.provenance["authored_map_blueprints"][0] == {
            "map_id": map_id,
            "blueprint_revision": 2,
            "blueprint_hash": corrected["content_hash"],
            "semantic_interface_hash": corrected["semantic_interface_hash"],
        }
        assert published_release.world_revision_hash == published_world.content_hash
        assert published_release.certification["authored_map_blueprint_count"] == 1
    finally:
        database.close()
