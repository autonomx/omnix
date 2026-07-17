from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.map_geometry_patch import (
    ApplyGeometryPatchCommand,
    GeometryCellPatch,
    MapGeometryPatchedEvent,
    replay_campaign_map_events,
)
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
)
from app.rpg.map_instance_service import move_actor_on_map
from app.rpg.map_observer_runtime import has_line_of_sight
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
            application_name="omnix-rpg-campaign-geometry-patch",
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
            map_id="map:shared-wall",
            level="interior",
            definition_revision=1,
            world_id="world:geometry-pg",
            world_revision=1,
            width=5,
            height=3,
            terrain_palette=(
                TerrainRule(code=".", terrain_id="floor"),
                TerrainRule(
                    code="#",
                    terrain_id="wall",
                    walkable=False,
                    blocks_sight=True,
                ),
            ),
            terrain_rows=("..#..", "..#..", "..#.."),
        )
    )


def _seed(database: PostgresDatabase) -> dict[str, CampaignMapInstanceSnapshot]:
    context = bootstrap_local_tenant(database)
    definition = _definition()
    revision = compile_world_revision(
        world_id=definition.world_id,
        revision=1,
        title="Geometry Patch World",
        canon={},
        entity_manifest={},
        topology={"locations": ["location:wall"], "routes": []},
    )
    snapshots = {
        campaign_id: create_map_instance_snapshot(
            map_instance_id=f"{campaign_id}:map:shared-wall",
            campaign_id=campaign_id,
            location_id="location:wall",
            definition=definition,
            actors=(
                GridActorPlacement(
                    actor_id=f"player:{campaign_id}",
                    cell=(0, 1),
                ),
            ),
        )
        for campaign_id in ("campaign:geometry-a", "campaign:geometry-b")
    }
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
        for campaign_id, snapshot in snapshots.items():
            work.rpg.create_campaign(
                context,
                campaign_id=campaign_id,
                title=campaign_id,
                state={"current_map_instance_id": snapshot.map_instance_id},
                engine_version="geometry-test",
                schema_version="geometry-test",
                seed="1",
                metadata={},
            )
            work.map_instances.create_instance(
                context,
                map_instance_id=snapshot.map_instance_id,
                campaign_id=campaign_id,
                location_id=snapshot.location_id,
                map_id=snapshot.map_id,
                definition_revision=snapshot.definition_revision,
                definition_hash=snapshot.definition_hash,
                snapshot=snapshot.model_dump(mode="json"),
            )
        work.commit()
    return snapshots


def test_geometry_patch_is_campaign_owned_persisted_and_replayable() -> None:
    database = _database()
    try:
        _reset(database)
        initial = _seed(database)
        definition = _definition()
        patch_event, patched = apply_campaign_geometry_patch(
            initial["campaign:geometry-a"].map_instance_id,
            ApplyGeometryPatchCommand(
                command_id="geometry:open-a",
                patch_id="patch:open-a",
                expected_map_state_revision=0,
                cells=tuple(
                    GeometryCellPatch(cell=(2, row), terrain_code=".")
                    for row in range(3)
                ),
            ),
            database=database,
        )
        move_event, moved = move_actor_on_map(
            initial["campaign:geometry-a"].map_instance_id,
            MoveActorCommand(
                command_id="move:a-through-wall",
                actor_id="player:campaign:geometry-a",
                destination=(4, 1),
                expected_map_state_revision=1,
            ),
            database=database,
        )
        with pytest.raises(MapMovementError, match="destination_unreachable"):
            move_actor_on_map(
                initial["campaign:geometry-b"].map_instance_id,
                MoveActorCommand(
                    command_id="move:b-through-wall",
                    actor_id="player:campaign:geometry-b",
                    destination=(4, 1),
                    expected_map_state_revision=0,
                ),
                database=database,
            )

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            row_a = work.map_instances.get_instance(
                context,
                initial["campaign:geometry-a"].map_instance_id,
            )
            row_b = work.map_instances.get_instance(
                context,
                initial["campaign:geometry-b"].map_instance_id,
            )
            events_a = work.map_instances.list_events(
                context,
                initial["campaign:geometry-a"].map_instance_id,
            )
            definition_row = work.map_instances.get_definition(
                context,
                definition.map_id,
                definition.definition_revision,
            )
            work.rollback()
        assert row_a is not None and row_b is not None and definition_row is not None
        snapshot_a = CampaignMapInstanceSnapshot.model_validate(row_a["snapshot"])
        snapshot_b = CampaignMapInstanceSnapshot.model_validate(row_b["snapshot"])
        assert snapshot_a == moved
        assert snapshot_b == initial["campaign:geometry-b"]
        assert snapshot_a.terrain_overrides == {
            "2,0": ".",
            "2,1": ".",
            "2,2": ".",
        }
        assert snapshot_b.terrain_overrides == {}
        assert definition_row["document"]["terrain_rows"] == [
            "..#..",
            "..#..",
            "..#..",
        ]
        assert has_line_of_sight(
            definition,
            (0, 1),
            (4, 1),
            snapshot=snapshot_a,
        ) is True
        assert has_line_of_sight(
            definition,
            (0, 1),
            (4, 1),
            snapshot=snapshot_b,
        ) is False
        replayed = replay_campaign_map_events(
            initial["campaign:geometry-a"],
            (
                MapGeometryPatchedEvent.model_validate(events_a[0]),
                ActorMovedEvent.model_validate(events_a[1]),
            ),
        )
        assert replayed == snapshot_a
        assert patch_event.event_id == events_a[0]["event_id"]
        assert move_event.event_id == events_a[1]["event_id"]
    finally:
        database.close()
