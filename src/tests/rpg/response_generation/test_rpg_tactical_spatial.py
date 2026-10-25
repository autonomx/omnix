"""The tactical grid's own rules (RQ-2.6; docs/rpg/design/combat.md): movement in a fight, cover and the grid's view.

The grid's commands are turns through the turn pipeline (``session/turn/tactical.py``; the playthrough's
``test_the_fight_stands_on_the_local_map`` plays them); these are the rules they read.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.apps.rpg.edge.api.feature_routes.rpg_tactical_spatial_routes import register_rpg_tactical_spatial_routes
from app.apps.rpg.world.map_grid_contracts import (
    GridActorPlacement,
    GridMapDefinition,
    TerrainRule,
    with_grid_definition_hashes,
)
from app.apps.rpg.world.map_instance_runtime import create_map_instance_snapshot
from app.apps.rpg.world.tactical_spatial import (
    evaluate_cover,
    foes_on_grid,
    foes_take_the_field,
    grid_turn_summary,
    movement_left,
)
from tests.support.routers import include_router_registrar


def _definition(*, low_cover: bool = False) -> GridMapDefinition:
    rows = ["......." for _ in range(5)]
    palette = [TerrainRule(code=".", terrain_id="floor")]
    if low_cover:
        rows[2] = "..c...."
        palette.append(TerrainRule(code="c", terrain_id="low_cover", walkable=False, blocks_sight=False))
    return with_grid_definition_hashes(GridMapDefinition(
        map_id="map:tactical", level="encounter", definition_revision=1, world_id="world:tactical", world_revision=1,
        width=7, height=5, terrain_palette=tuple(palette), terrain_rows=tuple(rows)))


def _snapshot(definition: GridMapDefinition, *, player=(1, 2), enemy=(1, 1)):
    return create_map_instance_snapshot(
        map_instance_id="campaign:a:map:tactical", campaign_id="campaign:a", location_id="location:tactical",
        definition=definition,
        actors=(GridActorPlacement(actor_id="player:a", cell=player), GridActorPlacement(actor_id="enemy:a", cell=enemy)))


def test_low_cover_between_attacker_and_target_is_full_cover() -> None:
    definition = _definition(low_cover=True)
    cover = evaluate_cover(definition, _snapshot(definition, player=(1, 2), enemy=(3, 2)),
                           attacker_id="player:a", target_id="enemy:a")
    assert (cover.level, cover.defense_bonus, cover.line_of_sight) == ("full", 5, True)
    open_ground = evaluate_cover(_definition(), _snapshot(_definition()), attacker_id="player:a", target_id="enemy:a")
    assert (open_ground.level, open_ground.defense_bonus) == ("none", 0)


def test_the_heros_movement_is_fresh_each_time_their_turn_comes_round() -> None:
    combat = {"round": 2, "turn_index": 0}
    tactical, left = movement_left(combat)
    assert left == 60 and tactical == {"turn": [2, 0], "movement_remaining": 60}
    spent = {**combat, "tactical_state": {"turn": [2, 0], "movement_remaining": 20}}
    assert movement_left(spent)[1] == 20  # the same turn: what is left of it
    assert movement_left({**spent, "round": 3})[1] == 60  # the next round's turn: a fresh allowance


def test_the_grid_shows_whose_turn_it_is_and_who_can_be_attacked() -> None:
    assert grid_turn_summary({}, "s1", "player:s1") == {"combat_active": False}
    simulation = {"combat_state": {
        "active": True, "round": 2, "turn_index": 0, "current_actor_id": "player",
        "participants": {"player": {"side": "party", "hp": 10}, "npc:liora": {"side": "party", "hp": 9},
                         "enemy:wolf:1": {"side": "enemy", "hp": 4, "name": "Echo Wolf"},
                         "enemy:wolf:2": {"side": "enemy", "hp": 0, "name": "Echo Wolf"}},
    }}
    assert grid_turn_summary(simulation, "s1", "player:s1") == {
        "combat_active": True, "round": 2, "current_actor_id": "player:s1", "your_turn": True,
        "movement_remaining": 60, "actions_remaining": 1, "hostile_actor_ids": ["enemy:wolf:1"],
        "actor_names": {"enemy:wolf:1": "Echo Wolf", "enemy:wolf:2": "Echo Wolf"}}  # the foes by name, not id
    assert grid_turn_summary(simulation, "s1", "enemy:wolf:1")["your_turn"] is False


def test_tactical_routes_are_documented() -> None:
    app = FastAPI()
    include_router_registrar(app, register_rpg_tactical_spatial_routes)
    assert {"/api/rpg/map-instances/{map_instance_id}/tactical/move",
            "/api/rpg/map-instances/{map_instance_id}/tactical/attack"} <= app.openapi()["paths"].keys()


def test_observer_responses_name_the_campaign_revision_and_tactical_turn() -> None:
    from app.apps.rpg.world.map_observer_service import _campaign_turn

    class Rpg:
        def __init__(self, campaign):
            self.campaign = campaign

        def get_campaign(self, _context, campaign_id):
            return self.campaign if campaign_id == "s1" else None

    class Work:
        def __init__(self, campaign):
            self.rpg = Rpg(campaign)

    assert _campaign_turn(Work({"revision": 7, "state": {}}), None, "s1", "player:s1") == ({
        "campaign_revision": 7, "tactical": {"combat_active": False}}, {})
    assert _campaign_turn(Work(None), None, "s1", "player:s1") == ({
        "campaign_revision": None, "tactical": {"combat_active": False}}, {})


def _fight(**wolf) -> dict:
    return {"active": True, "participants": {"player": {"side": "party", "hp": 10},
                                             "enemy:wolf:1": {"side": "enemy", "hp": 4, "name": "Echo Wolf", **wolf}}}


def test_a_foe_takes_the_square_nearest_the_hero_and_closes_in_when_it_acts() -> None:
    """RQ-7.7: the fight's foes stand on the local map, where the fight keeps them (never the map's own actors)."""
    definition = _definition()
    hero_only = create_map_instance_snapshot(
        map_instance_id="campaign:a:map:tactical", campaign_id="campaign:a", location_id="location:tactical",
        definition=definition, actors=(GridActorPlacement(actor_id="player:a", cell=(3, 2)),))
    placed = foes_take_the_field(definition, hero_only, _fight(), hero_id="player:a", foes_act=True)
    assert placed["participants"]["enemy:wolf:1"]["cell"] == [2, 1]  # beside the hero, the first free square
    assert foes_take_the_field(definition, hero_only, placed, hero_id="player:a", foes_act=True) is None  # stays

    far = _fight(cell=[6, 4])
    assert foes_take_the_field(definition, hero_only, far, hero_id="player:a", foes_act=False) is None  # hero's move
    closed = foes_take_the_field(definition, hero_only, far, hero_id="player:a", foes_act=True)
    assert closed["participants"]["enemy:wolf:1"]["cell"] == [4, 3]  # the square beside the hero nearest it
    seen = foes_on_grid(hero_only, closed)
    assert [actor.actor_id for actor in seen.actors] == ["player:a", "enemy:wolf:1"]
    assert [actor.actor_id for actor in hero_only.actors] == ["player:a"]  # the map itself is unchanged
    fallen = _fight(cell=[4, 3], hp=0)
    assert foes_on_grid(hero_only, fallen).actors == hero_only.actors  # a fallen foe leaves the grid

