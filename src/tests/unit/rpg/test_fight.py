"""The fight rule (RQ-2.6; docs/rpg/design/combat.md): pure, seeded, and its changes replay the fight."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.state import reduce
from app.apps.rpg.foundation.state.changes import (
    CampaignEnded,
    CombatAdvanced,
    DefeatRecorded,
    ExperienceGained,
    ItemAdded,
    LevelReached,
    LocationChanged,
    PurseChanged,
)
from app.apps.rpg.rules.combat.fight import fight
from app.apps.rpg.session.turn.planning import plan_action
from app.apps.rpg.rules.intent.grammar import IntentCandidate

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
    assert LevelReached(level=2, xp=40, xp_to_next=200, unspent_points=2, unspent_skill_points=1) in turn.changes
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
    assert plan_action(reading("status"), fighting=True).mechanic == "status"
