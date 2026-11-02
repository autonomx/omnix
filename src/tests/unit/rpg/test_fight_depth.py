"""Combat depth (evolution roadmap EV-2): weaknesses that work, resistances, boss phases, no escape, a boss left
regaining part of its health, guarding another, and a companion's order in a fight."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.apps.rpg.foundation.state import reduce
from app.apps.rpg.foundation.state.changes import GuardSet, PhaseEntered
from app.apps.rpg.rules.combat.fight import fight

# A foe that barely hurts back and stands a long fight: what each mechanic does is seen in it.
WIGHT = {"definition_id": "creature:wight", "name": "Glass Wight", "level": 2, "hp": 60, "defense": 2,
         "damage_min": 1, "damage_max": 1, "accuracy_bonus": -5,
         "vulnerabilities": [{"trigger_tag": "unpolished iron", "aliases": ["unpolished iron", "raw iron"],
                              "effect": "stun"}]}
ECHO = {"definition_id": "creature:echo", "name": "Echo", "level": 1, "hp": 400, "defense": 1, "damage_min": 1,
        "damage_max": 1, "resists": ["plain steel"]}
ARCHON = {"definition_id": "creature:archon", "name": "Archon", "level": 10, "hp": 100, "defense": 2, "damage_min": 1,
          "damage_max": 1, "accuracy_bonus": -5, "no_escape": True, "recovers": 0.5, "boss": True,
          "phases": [{"at": 0.9, "defense_bonus": 1, "damage_bonus": 1, "told": "It splits into two."},
                     {"at": 0.5, "calls_ally": True, "exposes_weakness": True}],
          "vulnerabilities": [{"trigger_tag": "shared witnessed truth", "aliases": ["shared truth"], "effect": "stun"}]}
TYRANT = {**ARCHON, "definition_id": "creature:tyrant", "name": "Tyrant", "no_escape": False, "phases": []}
SWORD = {"item_id": "item:sword", "name": "Steel Sword", "quantity": 1,
         "equipment": {"slot": "main_hand", "material": "plain steel", "stats": {"damage_min": 6, "damage_max": 6}}}


def _document(*, companion: dict | None = None, weapon: dict | None = None) -> dict[str, Any]:
    items = [weapon] if weapon else []
    return {
        "state": {"turn_count": 3, "player": {"level": 3}}, "manifest": {}, "runtime_state": {},
        "simulation_state": {
            "location_id": "loc:road",
            "campaign_mechanics": {"creatures": {row["definition_id"]: row for row in (WIGHT, ECHO, ARCHON, TYRANT)}},
            "world_model": {"locations": {"loc:road": {"name": "The Road", "present_npcs": []}},
                            "npcs": {"npc:liora": {"name": "Liora Fen"}}},
            "player_state": {"location_id": "loc:road", "hp": 50, "level": 3, "xp": 0, "xp_to_next": 400,
                             "resources": {"hp": {"current": 50, "max": 50}},
                             "party_state": {"companions": [companion]} if companion else {},
                             "inventory_state": {"items": items,
                                                 "equipment": {"main_hand": weapon["item_id"]} if weapon else {}}},
        },
    }


def _turn(document: dict, action: str, target: str, key: int, **kwargs: Any):
    turn = fight(document["simulation_state"], action=action, target_ref=target, turn_key=str(key), **kwargs)
    assert turn is not None
    return reduce(document, turn.changes)[0], turn


def test_a_weakness_used_stuns_the_foe_and_is_told() -> None:
    document, opened = _turn(_document(), "attack", "creature:wight", 0)
    hits = 0
    for key in range(1, 8):
        document, turn = _turn(document, "attack", "creature:wight", key, weakness="raw iron")
        log = document["simulation_state"]["combat_state"]["combat_log"]
        if any(row.get("kind") == "weakness" for row in log):
            hits += 1
            assert any("is its weakness" in line for line in turn.lines)
            break
    assert hits == 1
    # A weakness it does not have is no weakness used.
    document, turn = _turn(_document(), "attack", "creature:wight", 0, weakness="silver")
    assert not any(row.get("kind") == "weakness" for row in document["simulation_state"]["combat_state"]["combat_log"])


def test_what_a_foe_resists_blunts_a_weapon_of_that_material() -> None:
    document, turn = _turn(_document(weapon=SWORD), "attack", "creature:echo", 0)
    blows = [row for row in document["simulation_state"]["combat_state"]["combat_log"]
             if row.get("actor_id") == "player" and row.get("hit")]
    for _ in range(6):
        if blows:
            break
        document, turn = _turn(document, "attack", "creature:echo", len(blows) + 1)
        blows = [row for row in document["simulation_state"]["combat_state"]["combat_log"]
                 if row.get("actor_id") == "player" and row.get("hit")]
    assert blows and blows[0]["resisted"] is True and blows[0]["damage_applied"] == 3  # 6, halved


def test_a_boss_fights_in_phases_and_no_escape_is_had_from_a_finale() -> None:
    document, turn = _turn(_document(weapon={**SWORD, "equipment": {**SWORD["equipment"], "material": ""}}),
                           "attack", "creature:archon", 0)
    phases: list[PhaseEntered] = []
    for key in range(1, 40):
        refused = fight(document["simulation_state"], action="flee", turn_key=str(key))
        assert refused is not None and refused.refused and "no breaking away" in refused.lines[0]
        document, turn = _turn(document, "attack", "creature:archon", key)
        phases += [change for change in turn.changes if isinstance(change, PhaseEntered)]
        if len(phases) == 2 or turn.ended:
            break
    assert [phase.phase for phase in phases] == [1, 2]
    archon = document["simulation_state"]["combat_state"]["participants"]["enemy:creature-archon:1"]
    assert archon["phase"] == 2 and archon["exposed"] is True and archon["defense"] == 3
    assert any(row.get("ally_id") for row in document["simulation_state"]["combat_state"]["combat_log"]
               if row.get("kind") == "phase")  # the second phase called an echo of it


def test_a_boss_left_keeps_part_of_its_wounds() -> None:
    document, _ = _turn(_document(weapon={**SWORD, "equipment": {**SWORD["equipment"], "material": ""}}),
                        "attack", "creature:tyrant", 0)
    for key in range(1, 30):
        document, turn = _turn(document, "attack", "creature:tyrant", key)
        hp = document["simulation_state"]["combat_state"]["participants"]["enemy:creature-tyrant:1"]["hp"]
        if hp <= 70:
            break
    for key in range(30, 60):
        document, turn = _turn(document, "flee", "", key)
        if turn.ended == "fled":
            break
    assert turn.ended == "fled"
    left = document["simulation_state"]["combat_state"]["left"]["creature:tyrant"]
    assert hp < left < 100 and left == hp + round(0.5 * (100 - hp))  # half of what it lost, regained
    again, _ = _turn(document, "attack", "creature:tyrant", 99)
    assert again["simulation_state"]["combat_state"]["participants"]["enemy:creature-tyrant:1"]["hp"] <= left


def test_one_of_the_party_guards_another_and_takes_the_blows_aimed_at_them() -> None:
    liora = {"npc_id": "npc:liora", "name": "Liora Fen", "hp": 30, "max_hp": 30}
    document, _ = _turn(_document(companion=liora), "attack", "creature:wight", 0)
    document, turn = _turn(document, "defend", "npc:liora", 1)
    assert GuardSet(guard_id="player", guarded_id="npc:liora") in turn.changes
    assert turn.lines[0] == "You stand guard over Liora Fen."
    participants = document["simulation_state"]["combat_state"]["participants"]
    assert participants["player"]["guards"] == "npc:liora"
    aimed = [row for row in document["simulation_state"]["combat_state"]["combat_log"] if row.get("guarded_by")]
    assert all(row["target_id"] == "player" for row in aimed)  # what was aimed at her fell on the hero


def test_a_companion_ordered_to_guard_the_hero_or_flank_fights_so() -> None:
    guarding = {"npc_id": "npc:liora", "name": "Liora Fen", "hp": 30, "max_hp": 30, "stance": "guard"}
    document, _ = _turn(_document(companion=guarding), "attack", "creature:wight", 0)
    assert document["simulation_state"]["combat_state"]["participants"]["npc:liora"]["guards"] == "player"
    flanking = {**deepcopy(guarding), "stance": "flank"}
    document, _ = _turn(_document(companion=flanking), "attack", "creature:wight", 0)
    row = document["simulation_state"]["combat_state"]["participants"]["npc:liora"]
    assert row["flanking"] is True and "guards" not in row


def test_the_level_budgets_are_derived_or_authored_and_set_the_road_s_encounters() -> None:
    from app.apps.rpg.rules.budgets import budget, creature_findings, derived, encounter_fits

    simulation = _document()["simulation_state"]
    one, five = derived(1), derived(5)
    assert one.creature.hp.holds(10) and five.creature.hp.holds(28)  # the bestiary's own threat numbers
    assert five.danger.high > one.danger.high and five.group_member.hp.high < five.creature.hp.high
    assert budget(simulation, 3) == derived(3)  # a world that writes none
    authored = {**derived(3).model_dump(), "danger": {"low": 0, "high": 10}}
    simulation["world_model"]["budgets"] = [authored]
    assert budget(simulation, 3).danger.high == 10
    assert not encounter_fits(simulation, [{"budget_cost": 25}], 3) and encounter_fits(simulation, [{"budget_cost": 5}], 3)
    assert creature_findings(simulation, {"definition_id": "creature:x", "level": 1, "hp": 400, "damage_max": 4,
                                          "defense": 10}) == ["creature:x: hp 400 is outside 7-14 for level 1"]
