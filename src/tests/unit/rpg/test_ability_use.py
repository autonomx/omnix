"""The hero's abilities, used (rules/ability_use.py; docs/rpg/design/combat.md)."""
from __future__ import annotations

from app.apps.rpg.foundation.state import reduce
from app.apps.rpg.foundation.state.changes import TurnCounted
from app.apps.rpg.rules import ability_use

AIMED = {"ability_id": "a:aimed", "name": "Aimed Shot", "resource_cost": {"stamina": 10}, "cooldown_turns": 1,
         "effect_ops": [{"op": "modify_next_check", "check": "ranged_attack", "amount": 2},
                        {"op": "resource_delta", "target": "target", "resource": "hp", "amount": -10}]}
FROST = {"ability_id": "a:frost", "name": "Frost Arrow", "resource_cost": {"mana": 12}, "cooldown_turns": 2,
         "effect_ops": [{"op": "modify_next_check", "check": "enemy_mobility", "amount": -2, "duration_turns": 2}]}
MEND = {"ability_id": "a:mend", "name": "Mend", "resource_cost": {"mana": 5},
        "effect_ops": [{"op": "resource_delta", "target": "self", "resource": "hp", "amount": 15}]}
FLARE = {"ability_id": "a:flare", "name": "Radiant Flare", "effect_ops": [{"op": "reveal_clue", "clue_tag": "x"}]}


def _document(*, stamina: int = 100, mana: int = 30) -> dict:
    return {"manifest": {}, "simulation_state": {"player_state": {}},
            "state": {"turn_count": 4, "hotbar": {"1": "a:aimed"},
                      "player": {"resources": {"stamina": {"current": stamina, "max": 100}, "mana": {"current": mana, "max": 30}}},
                      "ability_tree": {"abilities": [AIMED, FROST, MEND, FLARE, {"ability_id": "a:locked", "name": "Locked"}]},
                      "ability_state": {"unlocked": ["a:aimed", "a:frost", "a:mend", "a:flare"]}}}


def test_an_ability_is_found_by_name_slot_or_id_and_only_when_unlocked() -> None:
    document = _document()
    assert ability_use.find(document, "use aimed shot on the wolf")["ability_id"] == "a:aimed"
    assert ability_use.find(document, "1")["ability_id"] == "a:aimed"
    assert ability_use.find(document, "a:frost")["ability_id"] == "a:frost"
    assert ability_use.find(document, "use Locked") is None


def test_using_one_pays_its_cost_and_cools_it_down_for_its_turns() -> None:
    document = _document()
    spent = ability_use.spend(document, AIMED)
    document, _ = reduce(document, [TurnCounted(turn_count=5), *spent])  # used in turn 5
    assert document["state"]["player"]["resources"]["stamina"]["current"] == 90
    assert document["state"]["ability_state"]["cooldowns"] == {"a:aimed": 1}
    document["state"]["turn_count"] = 5  # the turn it was used in is over
    assert ability_use.not_ready(document, AIMED) == "Aimed Shot is not ready yet (1 more turn)."
    document["state"]["turn_count"] = 6
    assert ability_use.not_ready(document, AIMED) == ""
    assert ability_use.not_ready(_document(mana=4), MEND) == "Mend needs 5 mana; you have 4."


def test_what_an_ability_does_in_a_fight_comes_from_its_effects() -> None:
    aimed, frost, mend = (ability_use.in_fight(row) for row in (AIMED, FROST, MEND))
    assert (aimed.strikes, aimed.damage_bonus, aimed.accuracy_bonus) == (True, 3, 2)
    assert (frost.strikes, frost.hinder, frost.hinder_turns) == (False, 2, 2)
    assert (mend.strikes, mend.heal) == (False, 15)
    assert not ability_use.acts_in_a_fight(FLARE)  # a world effect only: the older path's out of a fight
