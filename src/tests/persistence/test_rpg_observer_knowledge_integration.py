from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    GridPortal,
    GridPortalEndpoint,
    GridSpawnPoint,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import (
    CampaignMapInstanceSnapshot,
    MoveActorCommand,
    create_map_instance_snapshot,
    resolve_move_command,
)
from app.rpg.map_observer_runtime import ObserverPerceptionPolicy
from app.rpg.map_observer_service import (
    load_campaign_observer_projection,
    observe_campaign_map,
)
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
            application_name="omnix-rpg-observer-knowledge",
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
            map_id="map:observer-pg",
            level="interior",
            definition_revision=1,
            world_id="world:observer-pg",
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
            terrain_rows=(
                "...#...",
                "...#...",
                "...#...",
                "...#...",
                ".......",
            ),
            portals=(
                GridPortal(
                    portal_id="portal:hidden-door",
                    source=GridPortalEndpoint(map_id="map:observer-pg", cell=(2, 1)),
                    target=GridPortalEndpoint(map_id="map:other", cell=(0, 0)),
                    secret=True,
                ),
            ),
            spawn_points=(
                GridSpawnPoint(
                    spawn_point_id="spawn:hidden-cache",
                    cell=(2, 3),
                    secret=True,
                ),
            ),
        )
    )


def _seed(database: PostgresDatabase) -> CampaignMapInstanceSnapshot:
    context = bootstrap_local_tenant(database)
    definition = _definition()
    revision = compile_world_revision(
        world_id="world:observer-pg",
        revision=1,
        title="Observer World",
        canon={},
        entity_manifest={},
        topology={"locations": ["location:observer"], "routes": []},
    )
    snapshot = create_map_instance_snapshot(
        map_instance_id="campaign:observer:map:one",
        campaign_id="campaign:observer",
        location_id="location:observer",
        definition=definition,
        actors=(
            GridActorPlacement(actor_id="player:observer", cell=(1, 2)),
            GridActorPlacement(actor_id="npc:left-hidden", cell=(2, 2), hidden=True),
            GridActorPlacement(actor_id="npc:right-hidden", cell=(5, 2), hidden=True),
        ),
    ).model_copy(update={"hazard_states": {"hazard:secret": {"armed": True}}})
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
            title="Observer Campaign",
            state={"current_map_instance_id": snapshot.map_instance_id},
            engine_version="observer-test",
            schema_version="observer-test",
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


def test_observer_knowledge_is_idempotent_remembered_and_hazard_safe() -> None:
    database = _database()
    try:
        _reset(database)
        initial = _seed(database)
        policy = ObserverPerceptionPolicy(sight_radius=6, detection_radius=2)
        first = observe_campaign_map(
            initial.map_instance_id,
            observer_actor_id="player:observer",
            policy=policy,
            expected_knowledge_revision=0,
            database=database,
        )
        repeated = observe_campaign_map(
            initial.map_instance_id,
            observer_actor_id="player:observer",
            policy=policy,
            expected_knowledge_revision=1,
            database=database,
        )
        assert first["reused"] is False
        assert repeated["reused"] is True
        assert first["knowledge"]["knowledge_revision"] == 1
        assert first["knowledge"]["detected_actor_ids"] == [
            "npc:left-hidden",
            "player:observer",
        ]
        assert "hazard_states" not in first["projection"]

        context = bootstrap_local_tenant(database)
        definition = _definition()
        with unit_of_work(database) as work:
            row = work.map_instances.get_instance(
                context,
                initial.map_instance_id,
                for_update=True,
            )
            assert row is not None
            current = CampaignMapInstanceSnapshot.model_validate(row["snapshot"])
            event, after = resolve_move_command(
                definition,
                current,
                MoveActorCommand(
                    command_id="observer:move:right",
                    actor_id="player:observer",
                    destination=(5, 4),
                    expected_map_state_revision=current.map_state_revision,
                ),
            )
            work.map_instances.append_event(
                context,
                map_instance_id=current.map_instance_id,
                command_id=event.command_id,
                event_id=event.event_id,
                event_type=event.event_type,
                event_sequence=event.event_sequence,
                revision_before=event.map_state_revision_before,
                revision_after=event.map_state_revision_after,
                event=event.model_dump(mode="json"),
                snapshot=after.model_dump(mode="json"),
            )
            work.commit()

        second = observe_campaign_map(
            initial.map_instance_id,
            observer_actor_id="player:observer",
            policy=policy,
            expected_knowledge_revision=1,
            database=database,
        )
        loaded = load_campaign_observer_projection(
            initial.map_instance_id,
            observer_actor_id="player:observer",
            database=database,
        )

        assert second["knowledge"]["knowledge_revision"] == 2
        assert second["knowledge"]["observation_sequence"] == 2
        assert "npc:right-hidden" in second["knowledge"]["detected_actor_ids"]
        assert "npc:left-hidden" not in {
            row["actor_id"] for row in second["projection"]["actors"]
        }
        assert second["knowledge"]["known_portal_ids"] == ["portal:hidden-door"]
        assert second["knowledge"]["known_spawn_point_ids"] == [
            "spawn:hidden-cache"
        ]
        assert set(map(tuple, first["knowledge"]["known_cells"])) < set(
            map(tuple, second["knowledge"]["known_cells"])
        )
        assert loaded["stale"] is False
        assert [row["observation_sequence"] for row in loaded["recent_events"]] == [
            2,
            1,
        ]
        assert "hazard_states" not in loaded["projection"]
        assert any(
            "?" in row for row in loaded["projection"]["grid"]["terrain_rows"]
        )
    finally:
        database.close()
