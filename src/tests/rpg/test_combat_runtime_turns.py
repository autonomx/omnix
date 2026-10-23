"""A fight goes round by round: creatures take their turns, and the player is never left waiting on one."""
from __future__ import annotations

from app.apps.rpg.rules.combat.exchange_lines import describe_combat_exchange
from app.apps.rpg.rules.interactions.interaction_runtime import resolve_general_interaction


def _state(initiative_bonus: int) -> dict:
    return {
        "session_id": "rpg:test",
        "player_state": {"hp": 20, "max_hp": 20, "resources": {"hp": {"current": 100, "max": 100}}},
        "campaign_mechanics": {
            "creatures": {
                "creature:echo-wolf": {
                    "definition_id": "creature:echo-wolf",
                    "name": "Echo Wolf",
                    "hp": 10,
                    "defense": 8,
                    "damage_min": 2,
                    "damage_max": 3,
                    "accuracy_bonus": 20,
                    "initiative_bonus": initiative_bonus,
                }
            }
        },
    }


def _attacks(state: dict) -> list[dict]:
    return [row for row in state["combat_state"]["combat_log"] if row.get("kind") == "attack"]


def test_a_creature_that_wins_initiative_strikes_first_and_then_it_is_the_players_turn():
    state = _state(initiative_bonus=40)

    opened = resolve_general_interaction(state, player_input="I attack the Echo Wolf", tick=1)

    assert opened["combat_result"]["reason"] == "combat_started"
    wolf_id = "enemy:creature-echo-wolf:1"
    assert [row["actor_id"] for row in _attacks(state)] == [wolf_id]
    assert state["combat_state"]["current_actor_id"] == "player"
    hp = state["player_state"]["resources"]["hp"]["current"]
    assert 90 < hp < 100  # the hero fights with the hit points the player sees
    assert describe_combat_exchange(opened["combat_result"]) == [
        "The fight begins: you against the Echo Wolf.",
        f"The Echo Wolf hits you for {100 - hp} ({hp} of 100 left).",
    ]
    assert opened["combat_state"]["current_actor_id"] == "player"


def test_a_fight_left_waiting_on_the_creature_goes_on_when_the_player_acts():
    state = _state(initiative_bonus=40)
    resolve_general_interaction(state, player_input="I attack the Echo Wolf", tick=1)
    wolf_id = "enemy:creature-echo-wolf:1"
    combat = state["combat_state"]
    combat["turn_index"] = next(i for i, row in enumerate(combat["initiative_order"]) if row["actor_id"] == wolf_id)
    combat["current_actor_id"] = wolf_id  # saved before creatures took their own turns

    struck = resolve_general_interaction(state, player_input="I strike the echo wolf", tick=2)

    assert struck["combat_result"]["resolved"] is True
    assert [turn["actor_id"] for turn in struck["combat_result"]["earlier_turns"]] == [wolf_id]
    assert state["combat_state"]["participants"][wolf_id]["hp"] <= 10
    assert state["combat_state"]["current_actor_id"] == "player"


def test_each_attack_is_answered_by_the_creature_named():
    state = _state(initiative_bonus=-40)
    resolve_general_interaction(state, player_input="I attack the Echo Wolf", tick=1)
    assert state["combat_state"]["current_actor_id"] == "player"

    struck = resolve_general_interaction(state, player_input="I strike the echo wolf with my dagger", tick=2)

    wolf_id = "enemy:creature-echo-wolf:1"
    assert struck["combat_result"]["resolved"] is True
    assert struck["combat_result"]["target_id"] == wolf_id
    assert [row["actor_id"] for row in _attacks(state)] == ["player", wolf_id]
    assert [turn["actor_id"] for turn in struck["combat_result"]["other_turns"]] == [wolf_id]
    assert state["combat_state"]["current_actor_id"] == "player"
    lines = describe_combat_exchange(struck["combat_result"])
    assert len(lines) == 2 and lines[0].startswith(("You hit the Echo Wolf", "You miss the Echo Wolf"))
    assert lines[1].startswith(("The Echo Wolf hits you", "The Echo Wolf misses you"))


def test_the_hero_fights_with_the_weapon_their_sheet_lists_while_they_carry_it():
    from app.apps.rpg.rules.interactions.equipment_runtime import project_equipment_stats
    from app.apps.rpg.session.public_state_bridge import hydrate_simulation_player

    dagger = {"id": "iron_dagger", "item_id": "iron_dagger", "name": "Iron Dagger", "type": "weapon", "quantity": 1}
    session = hydrate_simulation_player({
        "state": {"player": {"inventory": [dagger], "equipment": [{"name": "Iron Dagger", "slot": "Weapon"}]}},
        "simulation_state": {},
    })
    simulation = session["simulation_state"]

    assert simulation["player_state"]["inventory"]["equipment"] == {"main_hand": "iron_dagger"}
    assert project_equipment_stats(simulation)["stats"]["damage_max"] == 5  # bare hands 0-1, plus the blade 1-4

    simulation["player_state"]["inventory_state"]["items"] = []  # sold
    assert project_equipment_stats(simulation)["stats"]["damage_max"] == 1


def test_a_lost_fight_leaves_the_hero_hurt_but_alive():
    state = _state(initiative_bonus=40)
    state["player_state"]["resources"]["hp"]["current"] = 1
    opened = resolve_general_interaction(state, player_input="I attack the Echo Wolf", tick=1)

    assert state["combat_state"]["active"] is False
    assert state["combat_state"]["ended_reason"] == "party_side_defeated"
    assert state["player_state"]["resources"]["hp"]["current"] == 10
    assert describe_combat_exchange(opened["combat_result"])[-1] == (
        "You fall, and the fight is lost. When you come to, your foe is gone; you are badly hurt (10 of 100 left)."
    )


def test_a_stage_carries_only_what_it_changed_onto_the_authoritative_state():
    from app.apps.rpg.session.public_state_bridge import carry_stage_changes

    start = {"tick": 4, "player_state": {"resources": {"hp": {"current": 100}, "stamina": {"current": 90}},
                                         "survival": {"hunger": 10}}, "combat_state": {"active": False, "stale": 1}}
    combat_stage = {"tick": 4, "player_state": {"resources": {"hp": {"current": 96}, "stamina": {"current": 90}},
                                                "survival": {"hunger": 10}}, "combat_state": {"active": True}}
    authoritative = {"tick": 5, "player_state": {"resources": {"hp": {"current": 100}, "stamina": {"current": 85}},
                                                 "survival": {"hunger": 12}}, "combat_state": {"active": False, "stale": 1}}

    merged = carry_stage_changes(start, combat_stage, authoritative)

    assert merged == {"tick": 5, "player_state": {"resources": {"hp": {"current": 96}, "stamina": {"current": 85}},
                                                  "survival": {"hunger": 12}}, "combat_state": {"active": True}}


def test_the_hero_can_break_away_from_a_fight():
    state = _state(initiative_bonus=-40)
    resolve_general_interaction(state, player_input="I attack the Echo Wolf", tick=1)

    fled = resolve_general_interaction(state, player_input="I flee from the Echo Wolf", tick=2)

    result = fled["combat_result"]
    assert result["reason"] in {"combat_fled", "combat_flee_failed"}
    lines = describe_combat_exchange(result)
    if result["escaped"]:
        assert state["combat_state"]["active"] is False and state["combat_state"]["ended_reason"] == "party_fled"
        assert lines == ["You break away from the Echo Wolf and escape; the fight is over."]
    else:
        assert state["combat_state"]["current_actor_id"] == "player"  # the wolf has had its turn
        assert lines[0] == "You try to break away, but the Echo Wolf cuts you off."
