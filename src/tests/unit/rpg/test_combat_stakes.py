"""What a lost fight costs, and what a rest restores (RQ-5.1; docs/rpg/design/stakes.md)."""
from __future__ import annotations

from app.apps.rpg.rules.combat.runtime_attacks import _roll_attack
from app.apps.rpg.rules.combat.stakes import apply_defeat, attack_penalty, record_rest

WORLD = {"start_location_id": "loc:gate", "locations": {
    "loc:gate": {"location_id": "loc:gate", "name": "The Gate"},
    "loc:inn": {"location_id": "loc:inn", "name": "The Inn"},
    "loc:pass": {"location_id": "loc:pass", "name": "The Pass"},
}}


def _state(*, items=(), purse=None, hardcore=False, companions=()):
    return {
        "world_model": WORLD,
        "campaign_rules": {"hardcore": hardcore},
        "location_id": "loc:pass",
        "player_state": {
            "location_id": "loc:pass",
            "resources": {"hp": {"current": 0, "max": 40}},
            "currency": purse or {"gold": 1, "silver": 2, "copper": 5},
            "inventory_state": {"currency": purse or {"gold": 1, "silver": 2, "copper": 5},
                                "items": [dict(item) for item in items], "equipment": {"main_hand": "sword"}},
            "party_state": {"companions": [dict(companion) for companion in companions]},
        },
    }


def _combat():
    return {"participants": {"player": {"actor_id": "player", "side": "party", "hp": 0, "max_hp": 40},
                             "enemy:wolf": {"actor_id": "enemy:wolf", "side": "enemy", "name": "Echo Wolf", "hp": 5}}}


ITEMS = ({"item_id": "sword", "name": "Sword", "value": 90},
         {"item_id": "relic", "name": "Gate Relic", "value": 500, "quest_item": True},
         {"item_id": "lamp", "name": "Brass Lamp", "value": 30},
         {"item_id": "bread", "name": "Bread", "value": 1, "qty": 3})


def test_defeat_wakes_the_hero_at_the_last_rest_hurt_battered_and_poorer() -> None:
    state, combat = _state(items=ITEMS, companions=({"npc_id": "npc:liora", "name": "Liora"},)), _combat()
    state["player_state"]["rest_point"] = "loc:inn"
    defeat = apply_defeat(state, combat)
    player = state["player_state"]
    assert defeat["woke_at"] == "loc:inn" and player["location_id"] == "loc:inn" and state["location_id"] == "loc:inn"
    assert defeat["hp"] == 10 and player["resources"]["hp"]["current"] == 10 and combat["participants"]["player"]["hp"] == 10
    assert defeat["coin_lost_copper"] == 25 and player["currency"] == {"gold": 1, "silver": 0, "copper": 0}
    assert player["inventory_state"]["currency"] == player["currency"]
    assert defeat["hours"] == 8 and defeat["defeated_by"] == ["Echo Wolf"] and player["defeats"] == 1
    assert defeat["battered"] == ["player", "npc:liora"]
    assert attack_penalty(state, "player") == 2 and attack_penalty(state, "npc:liora") == 2
    lost = defeat["item_lost"]
    assert lost in ({}, {"item_id": "lamp", "name": "Brass Lamp"})  # never the sword worn or the quest relic
    names = [item["name"] for item in player["inventory_state"]["items"]]
    assert "Sword" in names and "Gate Relic" in names and ("Brass Lamp" in names) == (not lost)


def test_without_a_rest_the_hero_wakes_where_the_campaign_opened() -> None:
    state = _state()
    assert apply_defeat(state, _combat())["woke_at"] == "loc:gate"


def test_a_copper_is_lost_from_a_small_purse_and_nothing_from_an_empty_one() -> None:
    small = _state(purse={"copper": 3})
    assert apply_defeat(small, _combat())["coin_lost_copper"] == 1
    empty = _state(purse={"copper": 0})
    assert apply_defeat(empty, _combat())["coin_lost_copper"] == 0


def test_hardcore_defeat_ends_the_campaign_and_leaves_the_hero_where_they_fell() -> None:
    state = _state(hardcore=True)
    defeat = apply_defeat(state, _combat())
    assert defeat["ended"] and state["campaign_end"]["reason"] == "defeated"
    assert state["player_state"]["location_id"] == "loc:pass"


def test_a_full_rest_records_the_rest_point_and_ends_being_battered() -> None:
    state = _state(companions=({"npc_id": "npc:liora"},))
    apply_defeat(state, _combat())
    assert record_rest(state, kind="rest") == {}  # a short rest is not a night's sleep
    assert attack_penalty(state, "player") == 2
    rested = record_rest(state, kind="inn_lodging")
    assert rested["rest_point"] == "loc:gate"  # where the hero woke, and slept
    assert attack_penalty(state, "player") == 0 and attack_penalty(state, "npc:liora") == 0


def test_battered_takes_two_off_the_attack_roll() -> None:
    state, combat = _state(), _combat()
    combat["participants"]["player"]["hp"] = 10
    fresh = _roll_attack(state, combat, "player", "enemy:wolf", combat["participants"]["enemy:wolf"], {})
    apply_defeat(state, _combat())
    battered = _roll_attack(state, combat, "player", "enemy:wolf", combat["participants"]["enemy:wolf"], {})
    assert battered["condition_penalty"] == 2 and battered["attack_total"] == fresh["attack_total"] - 2
