from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.gateway.rpg_tactical_spatial_routes import register_rpg_tactical_spatial_routes
from app.rpg.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.rpg.map_instance_runtime import create_map_instance_snapshot
from app.rpg.tactical_spatial import (
    TacticalAttackCommand,
    TacticalMoveCommand,
    TacticalSpatialError,
    evaluate_cover,
    resolve_tactical_attack,
    resolve_tactical_move,
)


def _definition(*, low_cover: bool = False) -> GridMapDefinition:
    rows = ["......." for _ in range(5)]
    palette = [TerrainRule(code=".", terrain_id="floor")]
    if low_cover:
        rows[2] = "..c...."
        palette.append(
            TerrainRule(
                code="c",
                terrain_id="low_cover",
                walkable=False,
                blocks_sight=False,
            )
        )
    return with_grid_definition_hashes(
        GridMapDefinition(
            map_id="map:tactical",
            level="encounter",
            definition_revision=1,
            world_id="world:tactical",
            world_revision=1,
            width=7,
            height=5,
            terrain_palette=tuple(palette),
            terrain_rows=tuple(rows),
        )
    )


def _state(*, movement_budget: int = 50) -> dict:
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
        "actor_states": [player],
        "npc_states": [enemy],
        "combat_state": {
            "active": True,
            "combat_id": "combat:tactical",
            "round": 1,
            "phase": "active",
            "participants": {
                "player:a": {
                    **player,
                    "combat_team": "party",
                    "movement_budget": movement_budget,
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


def _snapshot(definition: GridMapDefinition, *, player=(1, 2), enemy=(1, 1)):
    return create_map_instance_snapshot(
        map_instance_id="campaign:a:map:tactical",
        campaign_id="campaign:a",
        location_id="location:tactical",
        definition=definition,
        actors=(
            GridActorPlacement(actor_id="player:a", cell=player),
            GridActorPlacement(actor_id="enemy:a", cell=enemy),
        ),
    )


def test_tactical_move_consumes_budget_and_resolves_path_reaction() -> None:
    definition = _definition()
    snapshot = _snapshot(definition)
    event, moved, next_state, tactical = resolve_tactical_move(
        definition,
        snapshot,
        _state(),
        TacticalMoveCommand(
            submission_id="submission:move:1",
            command_id="command:move:1",
            actor_id="player:a",
            destination=(5, 2),
            expected_map_state_revision=0,
            expected_campaign_revision=0,
        ),
    )

    assert event.movement_cost == 40
    assert moved.actor("player:a").cell == (5, 2)
    assert tactical["movement_remaining"] == 10
    assert len(tactical["reaction_results"]) == 1
    reaction = tactical["reaction_results"][0]
    assert reaction["opportunity"]["reactor_id"] == "enemy:a"
    assert reaction["opportunity"]["trigger_path_index"] == 2
    assert reaction["resolution"]["hit"] is True
    assert reaction["resolution"]["target_hp_after"] == 14
    assert next_state["actor_states"][0]["resources"]["hp"] == 14
    assert (
        next_state["combat_state"]["tactical_state"]["reaction_available"]["enemy:a"]
        is False
    )


def test_tactical_move_enforces_current_actor_and_movement_budget() -> None:
    definition = _definition()
    snapshot = _snapshot(definition)
    with pytest.raises(TacticalSpatialError, match="tactical_actor_not_current"):
        resolve_tactical_move(
            definition,
            snapshot,
            _state(),
            TacticalMoveCommand(
                submission_id="submission:wrong-actor",
                command_id="command:wrong-actor",
                actor_id="enemy:a",
                destination=(2, 1),
                expected_map_state_revision=0,
                expected_campaign_revision=0,
            ),
        )

    with pytest.raises(TacticalSpatialError, match="tactical_movement_budget_exceeded"):
        resolve_tactical_move(
            definition,
            snapshot,
            _state(movement_budget=20),
            TacticalMoveCommand(
                submission_id="submission:over-budget",
                command_id="command:over-budget",
                actor_id="player:a",
                destination=(5, 2),
                expected_map_state_revision=0,
                expected_campaign_revision=0,
            ),
        )


def test_tactical_ranged_attack_applies_low_cover_and_action_budget() -> None:
    definition = _definition(low_cover=True)
    snapshot = _snapshot(definition, player=(1, 2), enemy=(3, 2))
    state = _state()
    state["combat_state"]["force_next_attack_roll"] = 10
    cover = evaluate_cover(
        definition,
        snapshot,
        attacker_id="player:a",
        target_id="enemy:a",
    )
    assert cover.level == "full"
    assert cover.defense_bonus == 5
    assert cover.line_of_sight is True

    next_state, tactical = resolve_tactical_attack(
        definition,
        snapshot,
        state,
        TacticalAttackCommand(
            submission_id="submission:attack:1",
            command_id="command:attack:1",
            actor_id="player:a",
            target_id="enemy:a",
            action_type="ranged_attack",
            expected_campaign_revision=0,
        ),
    )
    assert tactical["cover"]["level"] == "full"
    assert tactical["resolution"]["defense_total"] == 15
    assert tactical["resolution"]["hit"] is False
    assert tactical["actions_remaining"] == 0

    with pytest.raises(TacticalSpatialError, match="tactical_action_budget_exhausted"):
        resolve_tactical_attack(
            definition,
            snapshot,
            next_state,
            TacticalAttackCommand(
                submission_id="submission:attack:2",
                command_id="command:attack:2",
                actor_id="player:a",
                target_id="enemy:a",
                action_type="ranged_attack",
                expected_campaign_revision=1,
            ),
        )


def test_tactical_routes_are_hidden_and_installed_on_gateway() -> None:
    paths = {
        "/api/rpg/map-instances/{map_instance_id}/tactical/move",
        "/api/rpg/map-instances/{map_instance_id}/tactical/attack",
    }
    app = FastAPI()
    register_rpg_tactical_spatial_routes(app)
    assert paths <= {route.path for route in app.routes}
    assert paths.isdisjoint(app.openapi()["paths"])

    gateway = FastAPI(title="Omnix Web Gateway")
    gateway_paths = {
        route_path
        for route in gateway.routes
        if (route_path := getattr(route, "path", None)) is not None
    }
    assert paths <= gateway_paths
    assert paths.isdisjoint(gateway.openapi()["paths"])
