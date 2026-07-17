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
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import (
    ActorMovedEvent,
    CampaignMapInstanceSnapshot,
    create_map_instance_snapshot,
)
from app.rpg.npc_spatial_campaign_authoring import (
    configure_campaign_spatial_policy,
    read_campaign_spatial_state,
    save_campaign_spatial_goal,
    save_campaign_spatial_routine,
)
from app.rpg.npc_spatial_campaign_contracts import (
    CampaignNpcSpatialGoal,
    CampaignNpcSpatialPolicy,
    CampaignNpcSpatialRoutine,
    CampaignSpatialTickRequest,
    NpcSpatialRoutineStep,
)
from app.rpg.npc_spatial_campaign_runtime import advance_campaign_spatial_tick
from app.rpg.npc_spatial_transition import (
    ActorEnteredMapEvent,
    ActorExitedMapEvent,
    replay_npc_spatial_map_events,
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
            application_name="omnix-rpg-npc-spatial-campaign-runtime",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_rpg_npc_spatial_transitions, "
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


def _definitions() -> tuple[GridMapDefinition, GridMapDefinition]:
    source = with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:tavern",
            level="interior",
            definition_revision=1,
            world_id="world:spatial-runtime",
            world_revision=1,
            width=3,
            height=3,
            terrain_palette=(TerrainRule(code=".", terrain_id="floor"),),
            terrain_rows=("...", "...", "..."),
            portals=(
                GridPortal(
                    portal_id="portal:tavern-road",
                    source=GridPortalEndpoint(map_id="map:tavern", cell=(2, 1)),
                    target=GridPortalEndpoint(map_id="map:road", cell=(0, 1)),
                ),
            ),
        )
    )
    target = with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:road",
            level="encounter",
            definition_revision=1,
            world_id="world:spatial-runtime",
            world_revision=1,
            width=3,
            height=3,
            terrain_palette=(TerrainRule(code=".", terrain_id="road"),),
            terrain_rows=("...", "...", "..."),
        )
    )
    return source, target


def _seed(database: PostgresDatabase) -> tuple[
    CampaignMapInstanceSnapshot,
    CampaignMapInstanceSnapshot,
]:
    context = bootstrap_local_tenant(database)
    source_definition, target_definition = _definitions()
    revision = compile_world_revision(
        world_id="world:spatial-runtime",
        revision=1,
        title="Spatial Runtime World",
        canon={},
        entity_manifest={},
        topology={"locations": ["location:tavern", "location:road"], "routes": []},
    )
    source = create_map_instance_snapshot(
        map_instance_id="campaign:spatial:map:tavern",
        campaign_id="campaign:spatial",
        location_id="location:tavern",
        definition=source_definition,
        actors=(GridActorPlacement(actor_id="npc:bran", cell=(0, 1)),),
    )
    target = create_map_instance_snapshot(
        map_instance_id="campaign:spatial:map:road",
        campaign_id="campaign:spatial",
        location_id="location:road",
        definition=target_definition,
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
            map_id=source_definition.map_id,
            definition_revision=source_definition.definition_revision,
            world_id=revision.world_id,
            world_revision=revision.revision,
            document=source_definition.model_dump(mode="json"),
            definition_hash=source_definition.definition_hash,
            semantic_interface_hash=source_definition.semantic_interface_hash,
        )
        work.map_instances.put_definition(
            context,
            map_id=target_definition.map_id,
            definition_revision=target_definition.definition_revision,
            world_id=revision.world_id,
            world_revision=revision.revision,
            document=target_definition.model_dump(mode="json"),
            definition_hash=target_definition.definition_hash,
            semantic_interface_hash=target_definition.semantic_interface_hash,
        )
        work.rpg.create_campaign(
            context,
            campaign_id="campaign:spatial",
            title="Spatial Campaign",
            state={"current_map_instance_id": source.map_instance_id},
            engine_version="spatial-test",
            schema_version="spatial-test",
            seed="1",
            metadata={},
        )
        work.map_instances.create_instance(
            context,
            map_instance_id=source.map_instance_id,
            campaign_id=source.campaign_id,
            location_id=source.location_id,
            map_id=source.map_id,
            definition_revision=source.definition_revision,
            definition_hash=source.definition_hash,
            snapshot=source.model_dump(mode="json"),
        )
        work.map_instances.create_instance(
            context,
            map_instance_id=target.map_instance_id,
            campaign_id=target.campaign_id,
            location_id=target.location_id,
            map_id=target.map_id,
            definition_revision=target.definition_revision,
            definition_hash=target.definition_hash,
            snapshot=target.model_dump(mode="json"),
        )
        work.commit()
    return source, target


def test_campaign_ticks_persist_portal_routine_replay_and_metrics() -> None:
    database = _database()
    try:
        _reset(database)
        source_initial, target_initial = _seed(database)
        configure_campaign_spatial_policy(
            "campaign:spatial",
            CampaignNpcSpatialPolicy(
                active_actor_budget=2,
                coarse_actor_budget=1,
                coarse_tick_interval=2,
                transition_actor_budget=1,
                max_blocked_attempts=2,
            ),
            expected_world_tick=0,
            database=database,
        )
        save_campaign_spatial_goal(
            CampaignNpcSpatialGoal(
                goal_id="goal:bran-road",
                campaign_id="campaign:spatial",
                actor_id="npc:bran",
                map_instance_id=source_initial.map_instance_id,
                goal_type="transition_via_portal",
                portal_id="portal:tavern-road",
                target_map_instance_id=target_initial.map_instance_id,
                priority=10,
            ),
            database=database,
        )
        save_campaign_spatial_routine(
            CampaignNpcSpatialRoutine(
                routine_id="routine:bran-patrol",
                campaign_id="campaign:spatial",
                actor_id="npc:bran",
                interval_ticks=5,
                next_due_tick=3,
                steps=(
                    NpcSpatialRoutineStep(
                        step_id="walk-road",
                        map_instance_id=target_initial.map_instance_id,
                        goal_type="move_to_cell",
                        target_cell=(2, 1),
                        priority=5,
                    ),
                ),
            ),
            database=database,
        )

        tick1 = advance_campaign_spatial_tick(
            "campaign:spatial",
            CampaignSpatialTickRequest(
                expected_world_tick=0,
                active_map_instance_ids=(source_initial.map_instance_id,),
                coarse_map_instance_ids=(target_initial.map_instance_id,),
            ),
            database=database,
        )
        assert tick1["result"]["decisions"][0]["phase"] == "portal_approach"
        assert tick1["result"]["decisions"][0]["status"] == "moved"
        with pytest.raises(ValueError, match="campaign_spatial_tick_conflict"):
            advance_campaign_spatial_tick(
                "campaign:spatial",
                CampaignSpatialTickRequest(expected_world_tick=0),
                database=database,
            )

        tick2 = advance_campaign_spatial_tick(
            "campaign:spatial",
            CampaignSpatialTickRequest(
                expected_world_tick=1,
                active_map_instance_ids=(source_initial.map_instance_id,),
                coarse_map_instance_ids=(target_initial.map_instance_id,),
            ),
            database=database,
        )
        assert tick2["metrics"]["portal_transitions"] == 1
        assert tick2["result"]["decisions"][0]["phase"] == "portal_transition"

        tick3 = advance_campaign_spatial_tick(
            "campaign:spatial",
            CampaignSpatialTickRequest(
                expected_world_tick=2,
                active_map_instance_ids=(target_initial.map_instance_id,),
                coarse_map_instance_ids=(source_initial.map_instance_id,),
            ),
            database=database,
        )
        assert len(tick3["result"]["routine_goal_ids"]) == 1
        assert tick3["metrics"]["routine_goals_emitted"] == 1
        assert tick3["metrics"]["active_budget_used"] == 1

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            source_row = work.map_instances.get_instance(
                context,
                source_initial.map_instance_id,
            )
            target_row = work.map_instances.get_instance(
                context,
                target_initial.map_instance_id,
            )
            source_events = work.map_instances.list_events(
                context,
                source_initial.map_instance_id,
            )
            target_events = work.map_instances.list_events(
                context,
                target_initial.map_instance_id,
            )
            transition_goal = work.npc_spatial.get_goal(
                context,
                "campaign:spatial",
                "goal:bran-road",
            )
            routine_row = work.connection.execute(
                "SELECT emission_count, next_due_tick FROM "
                "omnix_rpg_npc_spatial_routines WHERE workspace_id = %s "
                "AND campaign_id = %s AND routine_id = %s",
                (context.workspace_id, "campaign:spatial", "routine:bran-patrol"),
            ).fetchone()
            transition_count = work.connection.execute(
                "SELECT COUNT(*) FROM omnix_rpg_npc_spatial_transitions"
            ).fetchone()
            work.rollback()
        assert source_row is not None and target_row is not None
        source_snapshot = CampaignMapInstanceSnapshot.model_validate(source_row["snapshot"])
        target_snapshot = CampaignMapInstanceSnapshot.model_validate(target_row["snapshot"])
        assert source_snapshot.actors == ()
        assert target_snapshot.actor("npc:bran").cell == (2, 1)
        assert transition_goal is not None and transition_goal["status"] == "completed"
        assert tuple(routine_row) == (1, 8)
        assert int(transition_count[0]) == 1

        source_replay = replay_npc_spatial_map_events(
            source_initial,
            (
                ActorMovedEvent.model_validate(source_events[0]),
                ActorExitedMapEvent.model_validate(source_events[1]),
            ),
        )
        target_replay = replay_npc_spatial_map_events(
            target_initial,
            (
                ActorEnteredMapEvent.model_validate(target_events[0]),
                ActorMovedEvent.model_validate(target_events[1]),
            ),
        )
        assert source_replay == source_snapshot
        assert target_replay == target_snapshot

        state = read_campaign_spatial_state(
            "campaign:spatial",
            database=database,
        )
        assert state["clock"]["world_tick"] == 3
        assert state["clock"]["aggregate_metrics"]["total_ticks"] == 3
        assert state["clock"]["aggregate_metrics"]["total_portal_transitions"] == 1
        assert state["clock"]["aggregate_metrics"]["total_routine_goals_emitted"] == 1
        assert [row["world_tick"] for row in state["recent_ticks"]] == [3, 2, 1]
        assert state["goals"] == []
    finally:
        database.close()
