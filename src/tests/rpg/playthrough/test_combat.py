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


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_fight_to_defeat_leaves_the_hero_hurt(launch, world) -> None:
    """Today's defeat: the fight ends and the hero is left at a tenth of their strength."""
    play, foe = launch(world), FOES[world][1]
    play.turn(f"I attack the {foe}.")
    _fight(play, foe, limit=60)
    assert play.combat()["participants"]["player"]["hp"] <= play.hp()
    assert play.hp() == max(1, 100 // 10)
    assert not play.combat().get("active")


@pytest.mark.parametrize("world", in_worlds("aurelia", aurelia=(
    "RQ-5.1: no defeat model (Q-1): a lost fight leaves the hero where they fell, with their coin and pack, and "
    "no time passes; the setback (wake where you last rested, hurt, something lost, time passed) is not built")))
def test_fight_to_defeat_is_a_setback(launch, world) -> None:
    play, foe = launch(world), FOES[world][1]
    play.turn("go to Starfall Village")
    play.turn("I rent a room for the night from Orik Stonewake.")
    play.turn("I go to my room and sleep for the night.")
    play.turn("go to Skybridge Pass")
    purse, pack, clock = play.purse(), play.inventory(), play.stored()["runtime_state"].get("campaign_calendar")
    play.turn(f"I attack the {foe}.")
    _fight(play, foe, limit=60)
    assert play.location() == "location:aurelia:starfall-village"  # back where they last rested
    assert play.purse() < purse or play.inventory() != pack  # something was lost
    assert play.stored()["runtime_state"].get("campaign_calendar") != clock


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
        assert not play.combat().get("active")
        assert not (play.stored()["runtime_state"].get("combat_state") or {}).get("active")
    assert play.survival()["hunger"] >= hunger  # time passes in a fight too


@pytest.mark.parametrize("world", in_worlds("aurelia", aurelia=(
    "RQ-2.6: the tactical routes read combat_state at the top of the campaign document while the turn engine "
    "keeps the fight under simulation_state, and the fight's 'player' is not the map's player:<session> actor, "
    "so a grid move mid-fight is refused with tactical_combat_not_active")))
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
