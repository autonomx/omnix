from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.map_grid_contracts import (
    GridMapDefinition,
    GridSpawnPoint,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.session.service import archive_session
from app.rpg.worlds.contracts import (
    MapDefinitionBinding,
    MapInitializationOperation,
    ScenarioProjectCreate,
    WorldProjectCreate,
    WorldReleaseDocument,
)
from app.rpg.worlds.postgres_service import (
    create_scenario_project,
    create_world_project,
    publish_scenario_revision,
    publish_world_release,
    publish_world_revision,
)
from app.rpg.worlds.published_launch import launch_published_scenario
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
            application_name="omnix-rpg-published-map-initialization",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_campaign_map_events, "
            "omnix_rpg_campaign_map_instances, omnix_rpg_map_definitions, "
            "omnix_rpg_campaign_world_bindings, omnix_rpg_scenario_revisions, "
            "omnix_rpg_scenarios, omnix_rpg_world_releases, "
            "omnix_rpg_world_revisions, omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_outbox_events, "
            "omnix_audit_events, omnix_workspace_memberships, omnix_workspaces, "
            "omnix_users CASCADE"
        )


def test_published_launch_applies_scenario_state_and_persists_starting_map() -> None:
    database = _database()
    session_id = ""
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        create_world_project(
            WorldProjectCreate(
                world_id="world:published-map",
                title="Published Map World",
                metadata={"starting_location": "rusty_flagon_tavern"},
            ),
            database=database,
        )
        world = compile_world_revision(
            world_id="world:published-map",
            revision=1,
            title="Published Map World",
            canon={"campaign_template": "classic_fantasy"},
            entity_manifest={},
            topology={"locations": ["rusty_flagon_tavern"], "routes": []},
            blueprint_requirements=(
                {
                    "map_id": "map:published-tavern",
                    "simulation_readiness": "navigable",
                },
            ),
        )
        stored_world = publish_world_revision(
            world,
            expected_revision=0,
            database=database,
        )
        definition = with_grid_definition_hashes(
            GridMapDefinition(
                map_id="map:published-tavern",
                level="interior",
                definition_revision=1,
                world_id=world.world_id,
                world_revision=1,
                width=5,
                height=5,
                terrain_palette=(
                    TerrainRule(code=".", terrain_id="floor", walkable=True),
                ),
                terrain_rows=(".....",) * 5,
                spawn_points=(
                    GridSpawnPoint(
                        spawn_point_id="spawn:arrival",
                        cell=(1, 1),
                        tags=("arrival", "player"),
                    ),
                    GridSpawnPoint(spawn_point_id="spawn:bran", cell=(2, 1)),
                ),
                metadata={
                    "location_id": "rusty_flagon_tavern",
                    "semantic_object_ids": ["object:front_door"],
                },
            )
        )
        with unit_of_work(database) as work:
            work.map_instances.put_definition(
                context,
                map_id=definition.map_id,
                definition_revision=definition.definition_revision,
                world_id=definition.world_id,
                world_revision=definition.world_revision,
                document=definition.model_dump(mode="json"),
                definition_hash=definition.definition_hash,
                semantic_interface_hash=definition.semantic_interface_hash,
            )
            work.commit()
        release = compile_world_release(
            world,
            release=1,
            map_bindings=(
                MapDefinitionBinding(
                    map_id=definition.map_id,
                    blueprint_revision=1,
                    definition_revision=definition.definition_revision,
                    definition_hash=definition.definition_hash,
                    semantic_interface_hash=definition.semantic_interface_hash,
                    simulation_readiness="navigable",
                ),
            ),
            certification={"launch_ready": True, "missing_requirements": []},
        )
        stored_release = publish_world_release(release, database=database)
        certified_release = WorldReleaseDocument.model_validate(stored_release["document"])
        assert certified_release.certification["semantic_validation"]["passed"] is True

        create_scenario_project(
            ScenarioProjectCreate(
                scenario_id="scenario:published-map",
                world_id=world.world_id,
                title="Published Tavern Opening",
            ),
            database=database,
        )
        scenario = compile_scenario_revision(
            scenario_id="scenario:published-map",
            revision=1,
            world_revision=world,
            compatible_release=1,
            starting_location_id="rusty_flagon_tavern",
            initial_npc_ids=("npc:bran",),
            map_initialization=(
                MapInitializationOperation(
                    operation_id="init:bran",
                    map_id=definition.map_id,
                    type="place_actor",
                    target_id="npc:bran",
                    payload={"spawn_point_id": "spawn:bran"},
                ),
                MapInitializationOperation(
                    operation_id="init:door",
                    map_id=definition.map_id,
                    type="set_object_state",
                    target_id="object:front_door",
                    payload={"state": "closed"},
                ),
            ),
        )
        publish_scenario_revision(scenario, database=database)

        launched = launch_published_scenario(
            world_id=world.world_id,
            world_revision=int(stored_world["revision"]),
            world_release=int(stored_release["release"]),
            scenario_id=scenario.scenario_id,
            scenario_revision=scenario.revision,
            player={"name": "Alyndra"},
            database=database,
        )
        session_id = str(launched["session_id"])
        map_instance_id = str(launched["map_instance"]["map_instance_id"])

        with unit_of_work(database) as work:
            binding = work.world_scenarios.get_campaign_binding(context, session_id)
            instance = work.map_instances.get_instance(context, map_instance_id)
            work.rollback()
        assert binding is not None
        assert instance is not None
        snapshot = instance["snapshot"]
        actors = {row["actor_id"]: row for row in snapshot["actors"]}
        assert actors[f"player:{session_id}"]["cell"] == [1, 1]
        assert actors["npc:bran"]["cell"] == [2, 1]
        assert snapshot["object_states"]["object:front_door"] == {"state": "closed"}
        assert snapshot["initialization_operation_ids"] == ["init:bran", "init:door"]
        assert snapshot["map_state_revision"] == 0
        assert snapshot["applied_event_sequence"] == 0
    finally:
        if session_id:
            archive_session(session_id)
        database.close()
