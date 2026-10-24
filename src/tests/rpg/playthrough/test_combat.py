"""Playthrough: fights won, lost and fled, and the tactical grid (RQ-0.3)."""
from __future__ import annotations

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES, in_worlds

pytestmark = POSTGRES

FOES = {"aurelia": ("Echo Wolf", "Hollow Archon"), "starter": ("Bandit", "Bandit"), "vesper": ("Kestrel drone", "Kestrel drone")}


def _fight(play, foe: str, *, limit: int = 40) -> int:
    """Attack until the fight ends; the number of turns it took."""
    for count in range(1, limit + 1):
        play.turn(f"I attack the {foe}.")
        if not play.combat().get("active"):
            return count
    raise AssertionError(f"the fight with {foe} did not end in {limit} turns: {play.combat()}")


@pytest.mark.parametrize("world", in_worlds())
def test_fight_to_victory(launch, world) -> None:
    play, foe = launch(world), FOES[world][0]
    play.turn("look around")
    xp, turns = int(play.player_state().get("xp") or 0), play.turn_count()

    play.turn(f"I attack the {foe}.")
    combat = play.combat()
    assert combat["active"] is True and combat["current_actor_id"] == "player"
    enemy = next(actor for actor in combat["participants"] if actor.startswith("enemy:"))
    rounds = _fight(play, foe)

    final = play.combat()
    assert final["participants"][enemy]["hp"] <= 0  # the creature fell, the hero did not
    assert play.hp() > 0 and play.hp() == final["participants"]["player"]["hp"]
    assert int(play.player_state().get("xp") or 0) > xp  # a won fight earns experience
    assert play.turn_count() == turns + 1 + rounds  # every blow is a turn
    assert "falls" in play.model.told().lower() or "defeat" in play.model.told().lower(), play.model.told()


def _minutes(play) -> int:
    return int((play.simulation().get("environment") or {}).get("absolute_minutes") or 0)


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_fight_to_defeat_is_a_setback(launch, world) -> None:
    """A lost fight (docs/rpg/design/stakes.md): the hero wakes where they last rested, eight hours later, at a
    quarter of their strength and battered, a fifth of the purse gone; a night's rest ends being battered."""
    play, foe = launch(world), FOES[world][1]
    play.turn("go to Starfall Village")
    play.turn("I rent a room for the night from Orik Stonewake.")
    play.turn("I go to my room and sleep for the night.")
    assert play.player_state().get("rest_point") == "location:aurelia:starfall-village"
    play.turn("go to Skybridge Pass")
    purse, minutes = play.purse(), _minutes(play)
    play.turn(f"I attack the {foe}.")
    _fight(play, foe, limit=60)

    state = play.player_state()
    assert not play.combat().get("active") and play.combat()["ended_reason"] == "party_side_defeated"
    assert play.location() == "location:aurelia:starfall-village"  # back where they last rested
    assert play.hp() == 100 // 4
    assert [condition["kind"] for condition in state.get("conditions") or ()] == ["battered"]
    assert play.purse() == purse - max(1, purse // 5)
    assert _minutes(play) >= minutes + 8 * 60
    assert state.get("defeats") == 1
    told = play.model.told()
    assert "the fight is lost" in told and "8 hours later" in told, told

    play.turn("I rent a room for the night from Orik Stonewake.")  # a full rest ends being battered
    play.turn("I go to my room and sleep for the night.")
    assert not play.player_state().get("conditions")


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_hardcore_defeat_ends_the_campaign(launch, world) -> None:
    play, foe = launch(world, gameplay={"permadeath": True}), FOES[world][1]
    play.turn(f"I attack the {foe}.")
    _fight(play, foe, limit=60)
    assert play.simulation()["campaign_end"]["reason"] == "defeated"
    assert "Your story ends here." in play.model.told()
    refused = play.post_turn("look around")
    assert refused.status_code == 409 and refused.json()["detail"]["error"] == "rpg_campaign_ended"


@pytest.mark.parametrize("world", in_worlds())
def test_fleeing_ends_the_fight_and_counts(launch, world) -> None:
    play, foe = launch(world), FOES[world][0]
    play.turn(f"I attack the {foe}.")
    assert play.combat()["active"] is True
    hunger, turns = play.survival()["hunger"], play.turn_count()
    play.turn(f"I flee from the {foe}.")
    told = play.model.told()
    assert "You break away" in told or "cuts you off" in told, told
    assert play.turn_count() == turns + 1
    if "You break away" in told:
        assert "parting blow" in told, told  # breaking away costs a blow from each foe standing (RQ-5.1)
        assert not play.combat().get("active")
        assert not (play.stored()["runtime_state"].get("combat_state") or {}).get("active")
    assert play.survival()["hunger"] >= hunger  # time passes in a fight too


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_tactical_move_and_attack_in_a_fight(launch, world) -> None:
    play = launch(world)
    play.turn("I attack the Echo Wolf.")
    assert play.combat()["active"] is True
    before = play.map_instance()["snapshot"]
    hero = next(actor for actor in before["actors"] if actor["actor_id"].startswith("player:"))
    target = (hero["cell"][0] - 1, hero["cell"][1])
    moved = play.tactical_move(target)
    assert moved.status_code == 200, moved.text[:300]
    assert moved.json()["actor_cell"] == list(target)
    assert play.map_instance()["snapshot"]["map_state_revision"] == before["map_state_revision"] + 1
    enemy = next(actor for actor in play.combat()["participants"] if actor.startswith("enemy:"))
    attacked = play.tactical_attack(enemy)
    assert attacked.status_code == 200, attacked.text[:300]


def test_fighting_a_person_costs_trust_and_earns_nothing(launch) -> None:
    """RQ-2.6 part 2: a person present can be fought, by numbers from what they do; the one attacked and everyone
    who sees it trust the hero less; beaten, they yield, for no experience or spoils; and a companion is not turned on."""
    play = launch("starter")  # Bran and Mira in the common room
    xp = int(play.player_state().get("xp") or 0)
    started = play.turn("I attack Bran.")
    combat = play.combat()
    assert combat["active"] is True and combat["participants"]["npc:bran"]["kind"] == "person"
    assert "The fight begins: you against Bran." in started["visible_response"]["plain_text"]
    regard = play.simulation()["relationship_state"]
    assert regard["npc:bran"]["trust"] == -40 and regard["npc:mira"]["trust"] == -15
    assert {row["name"]: row["stance"] for row in play.public()["relationships"]}["Bran"] == "Wary"

    guarded = play.turn("I defend myself.")
    assert guarded["visible_response"]["plain_text"].startswith("You raise your guard.")
    last = guarded
    for _ in range(30):
        if not play.combat().get("active"):
            break
        last = play.turn("attack")
    combat = play.combat()
    assert combat.get("active") is not True and combat["ended_reason"] == "enemy_side_defeated"
    assert "and Bran yields." in last["visible_response"]["plain_text"]
    assert int(play.player_state().get("xp") or 0) == xp  # no experience for beating people


def test_a_companion_is_not_turned_on(launch) -> None:
    play = launch("aurelia")
    play.turn("I ask Liora Fen to join my party as a companion.")
    assert "npc:liora-fen" in play.party()
    refused = play.turn("I attack Liora Fen.")
    assert "You will not turn on Liora Fen." in refused["visible_response"]["plain_text"]
    assert play.combat().get("active") is not True
