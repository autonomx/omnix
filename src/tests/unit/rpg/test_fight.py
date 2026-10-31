"""The fight rule (RQ-2.6; docs/rpg/design/combat.md): pure, seeded, and its changes replay the fight."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.apps.rpg.foundation.state import reduce
from app.apps.rpg.foundation.state.changes import (
    CampaignEnded,
    CombatAdvanced,
    DefeatRecorded,
    ExperienceGained,
    HpChanged,
    ItemAdded,
    LevelReached,
    LocationChanged,
    PurseChanged,
)
from app.apps.rpg.rules.combat.fight import fight
from app.apps.rpg.session.turn.planning import plan_action
from app.apps.rpg.rules.intent.reading import IntentCandidate

RAT = {"definition_id": "creature:rat", "name": "Rat", "level": 1, "hp": 3, "defense": 1, "damage_min": 1,
       "damage_max": 1, "xp_value": 90, "loot": [{"item_id": "item:tail", "chance": 1.0, "quantity": 2}]}
# A foe the hero cannot hurt and who barely hurts back: a fight that goes on.
TROLL = {"definition_id": "creature:troll", "name": "Troll", "level": 3, "hp": 400, "defense": 45, "damage_min": 1,
         "damage_max": 1, "accuracy_bonus": 0}
OGRE = {"definition_id": "creature:ogre", "name": "Ogre", "level": 9, "hp": 400, "defense": 30, "damage_min": 60,
        "damage_max": 80, "accuracy_bonus": 30, "xp_value": 500}


def _document(*, hp: int = 50, hardcore: bool = False, rest_point: str = "loc:inn") -> dict[str, Any]:
    return {
        "state": {"turn_count": 3, "player": {"xp": {"current": 0, "max": 100}, "level": 1}},
        "manifest": {},
        "runtime_state": {},
        "simulation_state": {
            "location_id": "loc:road",
            "campaign_rules": {"hardcore": hardcore},
            "campaign_mechanics": {"creatures": {"creature:rat": RAT, "creature:ogre": OGRE, "creature:troll": TROLL}},
            "world_model": {
                "items": [{"id": "item:tail", "name": "Rat Tail", "type": "trophy"}],
                "start_location_id": "loc:inn",
                "locations": {"loc:road": {"name": "The Road", "present_npcs": []},
                              "loc:inn": {"name": "The Inn", "present_npcs": [{"id": "npc:keeper", "name": "Keeper"}]}},
            },
            "player_state": {"location_id": "loc:road", "rest_point": rest_point, "hp": hp, "level": 1, "xp": 50,
                             "xp_to_next": 100, "resources": {"hp": {"current": hp, "max": 50}},
                             "inventory_state": {"items": [], "currency": {"gold": 1, "silver": 0, "copper": 0}}},
        },
    }


def _until_over(document: dict[str, Any], creature: str, *, limit: int = 30):
    turn = None
    for count in range(limit):
        turn = fight(document["simulation_state"], action="attack", target_ref=creature, turn_key=str(count))
        assert turn is not None
        document, _ = reduce(document, turn.changes)
        if turn.ended:
            return document, turn
    raise AssertionError("the fight did not end")


def test_a_creature_the_world_does_not_know_is_not_this_rules() -> None:
    assert fight(_document()["simulation_state"], action="attack", target_ref="dragon") is None


def test_a_won_fight_earns_the_creatures_experience_and_drops_and_replays() -> None:
    document, turn = _until_over(_document(), "rat")
    assert turn.ended == "victory"
    assert ExperienceGained(amount=90) in turn.changes
    # One curve (progression.md): level 2 brings 5 health and a choice that waits to be made.
    assert LevelReached(level=2, xp=40, xp_to_next=200, choices_pending=1, max_hp_gain=5) in turn.changes
    assert any(isinstance(change, ItemAdded) and change.item_id == "item:tail" and change.quantity == 2
               for change in turn.changes)
    combat = document["simulation_state"]["combat_state"]
    assert combat["active"] is False and combat["ended_reason"] == "enemy_side_defeated"
    assert document["simulation_state"]["player_state"]["level"] == 2
    assert document["state"]["player"]["level"] == 2  # the sheet shows it
    assert "You gain 90 experience." in turn.lines and "You reach level 2." in turn.lines


def test_the_same_campaign_fights_the_same_way() -> None:
    first = fight(_document()["simulation_state"], action="attack", target_ref="rat", turn_key="1")
    again = fight(_document()["simulation_state"], action="attack", target_ref="rat", turn_key="1")
    assert first is not None and again is not None and first.changes == again.changes


def test_a_lost_fight_is_a_setback_where_the_hero_last_rested() -> None:
    document, turn = _until_over(_document(hp=10), "ogre")
    assert turn.ended == "defeat" and turn.minutes == 8 * 60
    assert DefeatRecorded(defeats=1) in turn.changes
    assert LocationChanged(location_id="loc:inn", location_name="The Inn") in turn.changes
    assert PurseChanged(delta_copper=-20, reason="defeat") in turn.changes
    hero = document["simulation_state"]["player_state"]
    assert hero["location_id"] == "loc:inn" and hero["resources"]["hp"]["current"] == 12  # a quarter of 50
    assert [row["kind"] for row in hero["conditions"]] == ["battered"]
    assert any("the fight is lost" in line for line in turn.lines)


def test_a_hardcore_defeat_ends_the_campaign() -> None:
    document, turn = _until_over(_document(hp=10, hardcore=True), "ogre")
    assert CampaignEnded(reason="defeated", defeated_by=("Ogre",)) in turn.changes
    assert document["simulation_state"]["campaign_end"]["ended"] is True


def test_breaking_away_ends_the_fight_with_nothing_earned() -> None:
    document = _document()
    started = fight(document["simulation_state"], action="attack", target_ref="troll", turn_key="0")
    assert started is not None and not started.ended
    document, _ = reduce(document, started.changes)
    for count in range(1, 20):
        turn = fight(document["simulation_state"], action="flee", turn_key=str(count))
        assert turn is not None
        document, _ = reduce(document, turn.changes)
        if turn.ended:
            break
    assert turn.ended in {"fled", "defeat"}
    assert not any(isinstance(change, ExperienceGained) for change in turn.changes)


def test_a_heal_between_blows_holds_in_the_fight() -> None:
    document = _document(hp=20)
    started = fight(document["simulation_state"], action="attack", target_ref="troll", turn_key="0")
    assert started is not None and not started.ended
    document, _ = reduce(document, started.changes)
    document["simulation_state"]["player_state"]["resources"]["hp"]["current"] = 45  # a potion, say
    passed = fight(document["simulation_state"], action="pass", turn_key="1")
    assert passed is not None
    [advanced] = [change for change in passed.changes if isinstance(change, CombatAdvanced)]
    assert 40 <= advanced.combat_state["participants"]["player"]["hp"] <= 45  # healed, then a troll's blow or two


def test_in_a_fight_the_hero_strikes_flees_or_uses_something_and_nothing_else() -> None:
    def reading(family: str, **fields: Any) -> IntentCandidate:
        return IntentCandidate(family=family, confidence=0.95, reason=family, **fields)

    assert plan_action(reading("attack"), fighting=True).mechanic == "fight"
    assert plan_action(reading("flee"), fighting=True).reason == "flee"
    assert plan_action(reading("use_item", target_id="item:potion", target_kind="item"), fighting=True).reason == "in_fight"
    assert plan_action(reading("move", target_id="loc:inn", target_kind="place"), fighting=True).reason == "busy"
    assert plan_action(reading("use_item"), fighting=True).reason == "nothing_to_use"  # the last potion gone
    assert plan_action(reading("status"), fighting=True).mechanic == "status"


def _with_people(document: dict[str, Any]) -> dict[str, Any]:
    simulation = document["simulation_state"]
    simulation["world_model"]["npcs"] = {"npc:guard": {"name": "Hale", "role": "town guard"},
                                         "npc:baker": {"name": "Wenna", "role": "baker"},
                                         "npc:ally": {"name": "Ash", "role": "scout"}}
    simulation["present_npc_state"] = {"location_id": "loc:road", "present_npc_ids": ["npc:guard", "npc:baker", "npc:ally"]}
    simulation["player_state"]["party_state"] = {"companions": [{"npc_id": "npc:ally", "name": "Ash", "hp": 16}]}
    return document


def test_a_person_present_is_fought_by_what_they_do_and_everyone_who_saw_trusts_less() -> None:
    document = _with_people(_document())
    turn = fight(document["simulation_state"], action="attack", target_ref="npc:guard", turn_key="1")
    assert turn is not None and not turn.refused
    foe = turn.report["combat_state"]["participants"]["npc:guard"]
    assert (foe["kind"], foe["tags"], foe["defense"]) == ("person", ["fighter"], 13)  # a guard fights like one
    regard = {change.npc_id: change.delta for change in turn.changes if change.type == "regard_changed"}
    assert regard == {"npc:guard": -40, "npc:baker": -15}  # the companion is with the hero, not a witness
    after, _ = reduce(document, turn.changes)
    assert after["simulation_state"]["relationship_state"]["npc:baker"]["trust"] == -15
    assert fight(document["simulation_state"], action="attack", target_ref="npc:ally", turn_key="1").refused
    assert fight(document["simulation_state"], action="attack", target_ref="npc:nobody", turn_key="1") is None
    # Someone the world knows, elsewhere at this hour: no blow, the game says so (the route's intent eval: "I attack
    # Dr. Kade" with Kade away played as a free action, "nothing comes of it").
    document["simulation_state"]["world_model"]["npcs"]["npc:smith"] = {"name": "Bryn Hollow", "role": "smith"}
    away = fight(document["simulation_state"], action="attack", target_ref="Bryn Hollow", turn_key="1")
    assert away is not None and away.refused and away.lines == ["Bryn Hollow is not here."] and away.changes == []
    document["simulation_state"]["world_model"]["npcs"]["npc:kit"] = {"name": "Kit", "role": "runner"}
    assert fight(document["simulation_state"], action="attack", target_ref="the kitten", turn_key="1") is None


def test_defending_raises_the_heros_guard_until_their_next_turn() -> None:
    document = _with_people(_document())
    document["simulation_state"]["player_state"]["party_state"] = {"companions": []}  # the hero alone: Ash, a scout, would end it
    assert fight(document["simulation_state"], action="defend", turn_key="1").refused  # no fight to guard against
    started = fight(document["simulation_state"], action="attack", target_ref="npc:baker", turn_key="1")
    document, _ = reduce(document, started.changes)
    guarded = fight(document["simulation_state"], action="defend", turn_key="2")
    assert guarded.lines[0] == "You raise your guard."
    assert guarded.report["combat_state"]["participants"]["player"]["guarding"] is True
    document, _ = reduce(document, guarded.changes)
    struck = fight(document["simulation_state"], action="attack", turn_key="3")
    assert "guarding" not in struck.report["combat_state"]["participants"]["player"]
    assert plan_action(IntentCandidate("defend", confidence=0.85), fighting=True).reason == "defend"


# Stakes in a fight (RQ-5.1; stakes.md), on the fight rule.
def _against_the_troll(hp: int = 50, **foe: Any) -> tuple[dict[str, Any], str]:
    """A fight with the troll begun, then the hero's health and the troll's numbers as given: the document, and the
    troll's id."""
    document = _document()
    started = fight(document["simulation_state"], action="attack", target_ref="troll", turn_key="0")
    assert started is not None and not started.ended
    document, _ = reduce(document, started.changes)
    combat = document["simulation_state"]["combat_state"]
    [troll] = [actor_id for actor_id, row in combat["participants"].items() if row.get("side") == "enemy"]
    combat["participants"][troll].update(foe)
    combat["participants"]["player"]["hp"] = hp
    document["simulation_state"]["player_state"]["resources"]["hp"]["current"] = hp
    return document, troll


def _log(turn: Any, kind: str, actor_id: str) -> list[dict[str, Any]]:
    [advanced] = [change for change in turn.changes if isinstance(change, CombatAdvanced)]
    return [row for row in advanced.combat_state["combat_log"] if row["kind"] == kind and row["actor_id"] == actor_id]


def test_battered_takes_two_off_the_attack_roll() -> None:
    fresh, _ = _against_the_troll()
    battered = deepcopy(fresh)
    battered["simulation_state"]["player_state"]["conditions"] = [
        {"kind": "battered", "attack_penalty": 2, "check_penalty": 2, "until": "full_rest", "actor_id": "player"}]
    blows = [_log(fight(document["simulation_state"], action="attack", target_ref="troll", turn_key="1"),
                  "attack", "player")[-1] for document in (fresh, battered)]
    assert blows[1]["condition_penalty"] == 2 and blows[1]["attack_total"] == blows[0]["attack_total"] - 2


def test_breaking_away_costs_a_parting_blow_at_disadvantage() -> None:
    document, troll = _against_the_troll(initiative_bonus=-10, accuracy_bonus=30, damage_min=2, damage_max=5)
    document["simulation_state"]["combat_state"]["participants"]["player"]["initiative_bonus"] = 20  # always away
    turn = fight(document["simulation_state"], action="flee", turn_key="1")
    assert turn is not None and turn.ended == "fled"
    [blow] = _log(turn, "parting_blow", troll)
    assert blow["hit"] and 2 <= blow["damage_applied"] <= 5  # a sure-handed foe still lands it
    assert HpChanged(delta=-blow["damage_applied"]) in turn.changes
    assert not any(isinstance(change, ExperienceGained) for change in turn.changes)


def test_a_quick_foe_is_hard_to_break_away_from() -> None:
    document, troll = _against_the_troll(initiative_bonus=10)  # the hero needs 30 on a d20
    turn = fight(document["simulation_state"], action="flee", turn_key="1")
    assert turn is not None and not turn.ended
    assert not _log(turn, "parting_blow", troll) and _log(turn, "flee", "player")[-1]["escaped"] is False


def test_cut_down_while_breaking_away_is_a_defeat() -> None:
    document, _ = _against_the_troll(hp=1, initiative_bonus=-10, accuracy_bonus=30)
    document["simulation_state"]["combat_state"]["participants"]["player"]["initiative_bonus"] = 20
    turn = fight(document["simulation_state"], action="flee", turn_key="1")
    assert turn is not None and turn.ended == "defeat"
    assert DefeatRecorded(defeats=1) in turn.changes


def test_the_heros_trained_skills_and_a_companions_calling_count_in_a_fight() -> None:
    """The playtest: swordsmanship and defense chosen at each level counted for nothing, and Liora, a guide, fought
    at +0, so a level-6 knight took seventeen rounds."""
    from app.apps.rpg.rules.combat.fight import _numbers, _start

    def numbers(skills: dict[str, int]) -> tuple[dict[str, int], dict[str, Any]]:
        document = _with_people(_document())
        simulation = document["simulation_state"]
        simulation["player_state"]["skills"] = {name: {"level": rank, "xp": 0} for name, rank in skills.items()}
        combat = _start(simulation, {"actor_id": "enemy:rat", "definition_id": "creature:rat", "name": "Rat",
                                     "side": "enemy", "hp": 5, "max_hp": 5, "defense": 10}, turn_key="1")
        return _numbers(simulation, combat, "player"), combat

    untrained, combat = numbers({})
    trained, trained_combat = numbers({"swordsmanship": 2, "defense": 3})
    assert trained["accuracy_bonus"] == untrained["accuracy_bonus"] + 2  # a blade is fought with swordsmanship
    hero, untrained_hero = trained_combat["participants"]["player"], combat["participants"]["player"]
    assert hero["defense"] == untrained_hero["defense"] + 3
    ash = combat["participants"]["npc:ally"]  # a scout fights as a fighter does
    assert (ash["defense"], ash["armor"]) == (13, 1)
    assert _numbers({**_with_people(_document())["simulation_state"]}, combat, "npc:ally")["accuracy_bonus"] == 3


def test_a_fight_won_together_brings_each_standing_companion_closer() -> None:
    """The playtest: a whole campaign together, and Liora's regard moved only when a quest ended."""
    from app.apps.rpg.foundation.state.changes import RegardChanged
    from app.apps.rpg.rules.combat.fight import FOUGHT_BESIDE_REGARD

    document = _with_people(_document())
    _, turn = _until_over(document, "rat")
    assert turn.ended == "victory"
    assert [(change.npc_id, change.delta) for change in turn.changes if isinstance(change, RegardChanged)] == [
        ("npc:ally", FOUGHT_BESIDE_REGARD)]
