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
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import create_map_instance_snapshot
from app.rpg.tactical_spatial import TacticalAttackCommand, TacticalMoveCommand
from app.rpg.tactical_spatial_service import attack_tactically, move_actor_tactically
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
            application_name="omnix-rpg-tactical-spatial",
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
            map_id="map:tactical-pg",
            level="encounter",
            definition_revision=1,
            world_id="world:tactical-pg",
            world_revision=1,
            width=7,
            height=5,
            terrain_palette=(
                TerrainRule(code=".", terrain_id="floor"),
                TerrainRule(
                    code="c",
                    terrain_id="low_cover",
                    walkable=False,
                    blocks_sight=False,
                ),
            ),
            terrain_rows=(
                ".......",
                "..c....",
                ".......",
                ".......",
                ".......",
            ),
        )
    )


def _campaign_state() -> dict:
    player = {
        "id": "player:a",
        "name": "Player",
        "resources": {"hp": 20, "max_hp": 20},
        "stats": {"strength": 0, "agility": 0, "endurance": 0},
        "skills": {"brawling": 0, "evasion": 0},
    }
    enemy = {
        "id": "enemy:a",
        "name": "Enemy",
        "resources": {"hp": 12, "max_hp": 12},
        "stats": {"strength": 1, "agility": 0, "endurance": 0},
        "skills": {"brawling": 0, "evasion": 0},
    }
    return {
        "current_map_instance_id": "campaign:tactical:map:tactical-pg",
        "actor_states": [player],
        "npc_states": [enemy],
        "combat_state": {
            "active": True,
            "combat_id": "combat:tactical-pg",
            "round": 1,
            "phase": "active",
            "participants": {
                "player:a": {
                    **player,
                    "combat_team": "party",
                    "movement_budget": 50,
                },
                "enemy:a": {
                    **enemy,
                    "combat_team": "enemy",
                    "movement_budget": 40,
                },
            },
            "turn_order": ["player:a", "enemy:a"],
            "initiative": {"player:a": 20, "enemy:a": 10},
            "turn_index": 0,
            "current_actor_id": "player:a",
            "pending_npc_turn": False,
            "defense_modifiers": {},
            "recent_events": [],
            "force_next_attack_roll": 20,
            "force_next_damage": 3,
        },
    }


def _seed(database: PostgresDatabase) -> str:
    context = bootstrap_local_tenant(database)
    definition = _definition()
    revision = compile_world_revision(
        world_id=definition.world_id,
        revision=1,
        title="Tactical World",
        canon={},
        entity_manifest={},
        topology={"locations": ["location:tactical"], "routes": []},
    )
    map_instance_id = "campaign:tactical:map:tactical-pg"
    snapshot = create_map_instance_snapshot(
        map_instance_id=map_instance_id,
        campaign_id="campaign:tactical",
        location_id="location:tactical",
        definition=definition,
        actors=(
            GridActorPlacement(actor_id="player:a", cell=(1, 2)),
            GridActorPlacement(actor_id="enemy:a", cell=(1, 1)),
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
            title="Tactical Campaign",
            state=_campaign_state(),
            engine_version="tactical-test",
            schema_version="tactical-test",
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


def test_tactical_move_attack_and_idempotency_commit_across_ledgers() -> None:
    database = _database()
    try:
        _reset(database)
        map_instance_id = _seed(database)
        move = move_actor_tactically(
            map_instance_id,
            TacticalMoveCommand(
                submission_id="submission:tactical:move",
                command_id="command:tactical:move",
                actor_id="player:a",
                destination=(5, 2),
                expected_map_state_revision=0,
                expected_campaign_revision=0,
            ),
            database=database,
        )
        assert move["campaign_revision"] == 1
        assert move["map_state_revision"] == 1
        assert move["tactical"]["movement_remaining"] == 10
        assert len(move["tactical"]["reaction_results"]) == 1
        assert move["tactical"]["reaction_results"][0]["resolution"]["target_hp_after"] == 14

        duplicate_move = move_actor_tactically(
            map_instance_id,
            TacticalMoveCommand(
                submission_id="submission:tactical:move",
                command_id="command:tactical:move",
                actor_id="player:a",
                destination=(5, 2),
                expected_map_state_revision=0,
                expected_campaign_revision=0,
            ),
            database=database,
        )
        assert duplicate_move["idempotent_replay"] is True
        assert duplicate_move["campaign_revision"] == 1

        attack = attack_tactically(
            map_instance_id,
            TacticalAttackCommand(
                submission_id="submission:tactical:attack",
                command_id="command:tactical:attack",
                actor_id="player:a",
                target_id="enemy:a",
                action_type="ranged_attack",
                expected_campaign_revision=1,
            ),
            expected_map_state_revision=1,
            database=database,
        )
        assert attack["campaign_revision"] == 2
        assert attack["map_state_revision"] == 1
        assert attack["tactical"]["cover"]["level"] == "full"
        assert attack["tactical"]["cover"]["defense_bonus"] == 5
        assert attack["tactical"]["actions_remaining"] == 0

        duplicate_attack = attack_tactically(
            map_instance_id,
            TacticalAttackCommand(
                submission_id="submission:tactical:attack",
                command_id="command:tactical:attack",
                actor_id="player:a",
                target_id="enemy:a",
                action_type="ranged_attack",
                expected_campaign_revision=1,
            ),
            expected_map_state_revision=1,
            database=database,
        )
        assert duplicate_attack["idempotent_replay"] is True
        assert duplicate_attack["campaign_revision"] == 2

        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            campaign = work.rpg.get_campaign(context, "campaign:tactical")
            instance = work.map_instances.get_instance(context, map_instance_id)
            events = work.map_instances.list_events(context, map_instance_id)
            turns = work.rpg.list_turns(context, "campaign:tactical")
            work.rollback()
        assert campaign is not None
        assert instance is not None
        assert campaign["revision"] == 2
        assert campaign["state"]["actor_states"][0]["resources"]["hp"] == 14
        tactical_state = campaign["state"]["combat_state"]["tactical_state"]
        assert tactical_state["movement_remaining"]["player:a"] == 10
        assert tactical_state["actions_remaining"]["player:a"] == 0
        assert tactical_state["reaction_available"]["enemy:a"] is False
        assert instance["snapshot"]["map_state_revision"] == 1
        assert instance["snapshot"]["actors"][0]["cell"] == [5, 2]
        assert len(events) == 1
        assert events[0]["event_type"] == "actor_moved"
        assert len(turns) == 2
        assert [turn["command"]["type"] for turn in turns] == [
            "tactical_move",
            "tactical_attack",
        ]
    finally:
        database.close()
