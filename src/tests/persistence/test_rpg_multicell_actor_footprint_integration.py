from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.map_actor_footprints import actor_footprint_cells
from app.rpg.map_geometry_patch import ApplyGeometryPatchCommand, GeometryCellPatch
from app.rpg.map_geometry_patch_service import apply_campaign_geometry_patch
from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import (
    ActorMovedEvent,
    CampaignMapInstanceSnapshot,
    MapMovementError,
    MoveActorCommand,
    create_map_instance_snapshot,
    replay_map_events,
)
from app.rpg.map_instance_service import move_actor_on_map
from app.rpg.worlds.service import compile_world_revision

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
            application_name="omnix-rpg-multicell-footprints",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_map_observation_events, "
            "omnix_rpg_map_observer_knowledge, omnix_rpg_npc_spatial_transitions, "
            "omnix_rpg_npc_spatial_tick_runs, omnix_rpg_npc_spatial_routines, "
            "omnix_rpg_npc_spatial_goals, omnix_rpg_campaign_spatial_clocks, "
            "omnix_rpg_world_generation_runs, omnix_rpg_campaign_map_events, "
            "omnix_rpg_campaign_map_instances, omnix_rpg_map_definitions, "
            "omnix_rpg_campaign_world_bindings, omnix_rpg_scenario_revisions, "
            "omnix_rpg_scenarios, omnix_rpg_world_releases, "
            "omnix_rpg_world_revisions, omnix_rpg_world_topics, omnix_rpg_worlds, "
            "omnix_rpg_campaign_genesis_runs, omnix_rpg_narrative_responses, "
            "omnix_rpg_hermes_research, omnix_rpg_world_forge_proposals, "
            "omnix_rpg_campaign_bible_revisions, omnix_rpg_campaign_bibles, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, omnix_job_attempts, "
            "omnix_job_events, omnix_jobs, omnix_outbox_events, omnix_audit_events, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def _definition() -> GridMapDefinition:
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:multicell-pg",
            level="encounter",
            definition_revision=1,
            world_id="world:multicell-pg",
            world_revision=1,
            width=7,
            height=5,
            terrain_palette=(
                TerrainRule(code=".", terrain_id="floor"),
                TerrainRule(
                    code="#",
                    terrain_id="wall",
                    walkable=False,
                    blocks_sight=True,
                ),
            ),
            terrain_rows=("...#...", ".......", ".......", "...#...", "...#..."),
        )
    )


def _seed(database: PostgresDatabase) -> CampaignMapInstanceSnapshot:
    context = bootstrap_local_tenant(database)
    definition = _definition()
    revision = compile_world_revision(
        world_id=definition.world_id,
        revision=1,
        title="Multi-cell World",
        canon={},
        entity_manifest={},
        topology={"locations": ["location:multicell"], "routes": []},
    )
    snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:multicell:map:multicell-pg",
        campaign_id="campaign:multicell",
        location_id="location:multicell",
        definition=definition,
        actors=(
            GridActorPlacement(
                actor_id="actor:large",
                cell=(0, 1),
                footprint_width=2,
                footprint_height=2,
            ),
        ),
    )
    with unit_of_work(database) as work:
        work.world_scenarios.create_world(
            context,
            world_id=revision.world_id,
            title=revision.title,
            source_mode="manual",
        )
        work.world_scenarios.publish_world_revision(
            context,
            world_id=revision.world_id,
            document=revision.model_dump(mode="json"),
            content_hash=revision.content_hash,
            expected_revision=0,
        )
        work.map_instances.put_definition(
            context,
            map_id=definition.map_id,
            definition_revision=definition.definition_revision,
            world_id=revision.world_id,
            world_revision=revision.revision,
            document=definition.model_dump(mode="json"),
            definition_hash=definition.definition_hash,
            semantic_interface_hash=definition.semantic_interface_hash,
        )
        work.rpg.create_campaign(
            context,
            campaign_id=snapshot.campaign_id,
            title="Multi-cell Campaign",
            state={"current_map_instance_id": snapshot.map_instance_id},
            engine_version="multicell-test",
            schema_version="multicell-test",
            seed="1",
            metadata={},
        )
        work.map_instances.create_instance(
            context,
            map_instance_id=snapshot.map_instance_id,
            campaign_id=snapshot.campaign_id,
            location_id=snapshot.location_id,
            map_id=snapshot.map_id,
            definition_revision=snapshot.definition_revision,
            definition_hash=snapshot.definition_hash,
            snapshot=snapshot.model_dump(mode="json"),
        )
        work.commit()
    return snapshot


def test_multicell_actor_move_persists_replays_and_protects_non_anchor_cells() -> None:
    database = _database()
    try:
        _reset(database)
        initial = _seed(database)
        event, moved = move_actor_on_map(
            initial.map_instance_id,
            MoveActorCommand(
                command_id="move:large:wide-opening",
                actor_id="actor:large",
                destination=(5, 1),
                expected_map_state_revision=0,
            ),
            database=database,
        )
        with pytest.raises(MapMovementError, match="geometry_patch_actor_occupied"):
            apply_campaign_geometry_patch(
                initial.map_instance_id,
                ApplyGeometryPatchCommand(
                    command_id="patch:under-large",
                    patch_id="patch:under-large",
                    expected_map_state_revision=1,
                    cells=(GeometryCellPatch(cell=(6, 2), terrain_code="#"),),
                ),
                database=database,
            )

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            row = work.map_instances.get_instance(context, initial.map_instance_id)
            events = work.map_instances.list_events(context, initial.map_instance_id)
            work.rollback()
        assert row is not None
        stored = CampaignMapInstanceSnapshot.model_validate(row["snapshot"])
        assert stored == moved
        assert stored.map_state_revision == 1
        assert actor_footprint_cells(stored.actor("actor:large")) == (
            (5, 1),
            (6, 1),
            (5, 2),
            (6, 2),
        )
        assert len(events) == 1
        replayed = replay_map_events(
            initial,
            (ActorMovedEvent.model_validate(events[0]),),
        )
        assert replayed == stored
        assert event.event_id == events[0]["event_id"]
    finally:
        database.close()
