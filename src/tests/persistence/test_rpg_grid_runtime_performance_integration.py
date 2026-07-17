from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work
from app.rpg.grid_runtime_performance import GridRuntimeBudget
from app.rpg.grid_runtime_performance_service import profile_campaign_grid_runtime
from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import (
    MoveActorCommand,
    create_map_instance_snapshot,
)
from app.rpg.map_instance_service import move_actor_on_map
from app.rpg.map_observer_runtime import ObserverPerceptionPolicy
from app.rpg.map_observer_service import observe_campaign_map
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
            application_name="omnix-rpg-grid-runtime-performance",
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
            map_id="map:performance-pg",
            level="encounter",
            definition_revision=1,
            world_id="world:performance-pg",
            world_revision=1,
            width=12,
            height=8,
            terrain_palette=(TerrainRule(code=".", terrain_id="floor"),),
            terrain_rows=tuple("." * 12 for _ in range(8)),
        )
    )


def _seed(database: PostgresDatabase) -> str:
    context = bootstrap_local_tenant(database)
    definition = _definition()
    revision = compile_world_revision(
        world_id=definition.world_id,
        revision=1,
        title="Performance World",
        canon={},
        entity_manifest={},
        topology={"locations": ["location:performance"], "routes": []},
    )
    map_instance_id = "campaign:performance:map:performance-pg"
    snapshot = create_map_instance_snapshot(
        map_instance_id=map_instance_id,
        campaign_id="campaign:performance",
        location_id="location:performance",
        definition=definition,
        actors=(
            GridActorPlacement(actor_id="observer:a", cell=(1, 1)),
            GridActorPlacement(actor_id="npc:a", cell=(5, 4)),
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
            title="Performance Campaign",
            state={"current_map_instance_id": map_instance_id},
            engine_version="performance-test",
            schema_version="performance-test",
            seed="1",
            metadata={},
        )
        work.map_instances.create_instance(
            context,
            map_instance_id=map_instance_id,
            campaign_id=snapshot.campaign_id,
            location_id=snapshot.location_id,
            map_id=snapshot.map_id,
            definition_revision=snapshot.definition_revision,
            definition_hash=snapshot.definition_hash,
            snapshot=snapshot.model_dump(mode="json"),
        )
        work.commit()
    return map_instance_id


def _durable_counts(database: PostgresDatabase, map_instance_id: str) -> dict[str, int]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        campaign = work.rpg.get_campaign(context, "campaign:performance")
        instance = work.map_instances.get_instance(context, map_instance_id)
        map_events = work.map_instances.list_events(context, map_instance_id)
        observation_events = work.observers.list_events(
            context,
            campaign_id="campaign:performance",
            map_instance_id=map_instance_id,
            observer_actor_id="observer:a",
        )
        work.rollback()
    assert campaign is not None
    assert instance is not None
    return {
        "campaign_revision": int(campaign["revision"]),
        "map_state_revision": int(instance["map_state_revision"]),
        "map_events": len(map_events),
        "observation_events": len(observation_events),
    }


def test_persisted_grid_profile_is_read_only_and_evidence_driven() -> None:
    database = _database()
    try:
        _reset(database)
        map_instance_id = _seed(database)
        move_actor_on_map(
            map_instance_id,
            MoveActorCommand(
                command_id="move:performance:observer",
                actor_id="observer:a",
                destination=(2, 1),
                expected_map_state_revision=0,
            ),
            database=database,
        )
        observe_campaign_map(
            map_instance_id,
            observer_actor_id="observer:a",
            policy=ObserverPerceptionPolicy(sight_radius=6, detection_radius=2),
            database=database,
        )
        before = _durable_counts(database, map_instance_id)

        profile = profile_campaign_grid_runtime(
            map_instance_id,
            observer_actor_id="observer:a",
            path_probe_actor_id="observer:a",
            path_probe_destination=(10, 6),
            database=database,
        )
        after = _durable_counts(database, map_instance_id)

        assert before == after == {
            "campaign_revision": 0,
            "map_state_revision": 1,
            "map_events": 1,
            "observation_events": 1,
        }
        assert profile["knowledge_source"] == "durable"
        decision = profile["profile"]["decision"]
        metrics = decision["metrics"]
        assert decision["renderer"] == "svg"
        assert decision["recommendation"] == "retain_svg"
        assert decision["renderer_reasons"] == []
        assert metrics["cells"] == 96
        assert metrics["actors"] == 2
        assert metrics["event_count"] == 1
        assert metrics["visible_cells"] > 0
        assert metrics["known_cells"] >= metrics["visible_cells"]
        assert metrics["projection_bytes"] > 0
        assert metrics["path_probe_status"] == "resolved"
        assert metrics["path_probe_length"] > 1
        assert metrics["path_probe_cost"] > 0
        assert decision["timings"]["projection_ms"] >= 0
        assert decision["timings"]["pathfinding_ms"] is not None

        escalated = profile_campaign_grid_runtime(
            map_instance_id,
            observer_actor_id="observer:a",
            budget=GridRuntimeBudget(max_svg_cells=50),
            database=database,
        )
        escalated_decision = escalated["profile"]["decision"]
        assert escalated_decision["renderer"] == "pixi"
        assert escalated_decision["recommendation"] == "escalate_to_pixi"
        assert escalated_decision["renderer_reasons"] == [
            "cells_exceeds_svg_budget:96>50"
        ]
        assert _durable_counts(database, map_instance_id) == before
    finally:
        database.close()
