"""Playthrough: fights won, lost and fled, and the tactical grid (RQ-0.3)."""
from __future__ import annotations

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES, in_worlds

pytestmark = POSTGRES

FOES = {"aurelia": ("Echo Wolf", "Hollow Archon"), "starter": ("Bandit", "Bandit"), "vesper": ("Nullborn", "Kestrel Cerberus Squad")}


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
    play.to_the_wild()  # creatures are met where no one lives (encounters.md)
    for _ in range(3):  # a creature that flees when hurt may get away (encounters.md): then it earned nothing
        xp, turns = int(play.player_state().get("xp") or 0), play.turn_count()
        play.turn(f"I attack the {foe}.")
        combat = play.combat()
        assert combat["active"] is True and combat["current_actor_id"] == "player"
        enemy = next(actor for actor in combat["participants"] if actor.startswith("enemy:"))
        rounds = _fight(play, foe)
        final = play.combat()
        if final["ended_reason"] != "enemy_fled":
            break
        assert int(play.player_state().get("xp") or 0) == xp and "it yields you nothing" in play.model.told()

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
    play.clear_the_road()  # what the road brings is not the fight this is about
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
    play.to_the_wild()
    play.turn(f"I attack the {foe}.")
    _fight(play, foe, limit=60)
    assert play.simulation()["campaign_end"]["reason"] == "defeated"
    assert "Your story ends here." in play.model.told()
    refused = play.post_turn("look around")
    assert refused.status_code == 409 and refused.json()["detail"]["error"] == "rpg_campaign_ended"


@pytest.mark.parametrize("world", in_worlds())
def test_fleeing_ends_the_fight_and_counts(launch, world) -> None:
    play, foe = launch(world), FOES[world][0]
    play.to_the_wild()
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


def _hero_and_foe(play) -> tuple[list[int], str, list[int]]:
    hero = next(actor for actor in play.map_instance()["snapshot"]["actors"] if actor["actor_id"].startswith("player:"))
    foe, row = next((actor, row) for actor, row in play.combat()["participants"].items() if actor.startswith("enemy:"))
    return hero["cell"], foe, row["cell"]


def _apart(left: list[int], right: list[int]) -> int:
    return max(abs(left[0] - right[0]), abs(left[1] - right[1]))


def test_the_fight_stands_on_the_local_map(launch) -> None:
    """RQ-7.7: the local map follows the hero, and a fight's foe stands on it: beside the hero when the fight
    begins, struck from the grid, left behind by the hero's grid move, and closing in again when it acts."""
    play = launch("aurelia")
    opening = play.map_instance()["map_instance_id"]
    play.to_the_wild()
    here = play.map_instance()
    assert here["map_instance_id"] != opening and here["map_instance_id"].endswith("map-aurelia-skybridge-pass:1")
    assert here["location_id"] == "location:aurelia:skybridge-pass"

    play.turn("I attack the Echo Wolf.")
    assert play.combat()["active"] is True
    hero, foe, cell = _hero_and_foe(play)
    assert _apart(hero, cell) == 1  # beside the hero
    attacked = play.tactical_attack(foe)
    assert attacked.status_code == 200, attacked.text[:300]
    if not play.combat().get("active"):
        return  # one blow felled it, or it fled
    hero, foe, cell = _hero_and_foe(play)
    squares = sorted({(hero[0] + dx, hero[1] + dy) for dx in range(-3, 4) for dy in range(-3, 4)}, key=lambda point: point[::-1])
    away = next(target for index, target in enumerate(squares)  # the first open square at least two from the foe
                if _apart(list(target), cell) >= 2
                and play.tactical_move(target, submission_id=f"move-{index}").status_code == 200)
    assert _hero_and_foe(play)[2] == cell  # the foe has not acted yet: it stands where it was
    assert _apart(list(away), cell) >= 2
    refused = play.tactical_attack(foe, submission_id="attack-2")
    assert refused.status_code == 409 and "out_of_reach" in refused.text, refused.text[:300]
    play.turn("I defend myself.")
    if play.combat().get("active"):
        hero, _, cell = _hero_and_foe(play)
        assert _apart(hero, cell) == 1  # it closed in on its turn


def test_no_creature_is_met_where_people_live(launch) -> None:
    """RQ-7.7: a wolf is met on the road, not in the guild hall; a quest sends the hero to its own foes."""
    play = launch("aurelia")
    refused = play.turn("I attack the Echo Wolf.")  # Liora Fen lives in the grove
    assert refused["visible_response"]["plain_text"].startswith("No Echo Wolf is here."), refused
    assert play.combat().get("active") is not True


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


def test_abilities_in_a_fight_cost_cool_down_and_act(launch) -> None:
    """RQ-2.6 part 2: an ability aimed at a foe opens the fight with it; it costs its stamina or mana and cools down
    for its turns; a control ability hinders the foe; the hotbar uses the same rule in a fight; a rest restores the
    pools; and a bare "attack" in a fight strikes the foe in front of the hero."""
    play = launch("aurelia")
    play.to_the_wild()  # a foe that stands its ground (a wolf may flee from the first shot)
    opened = play.turn("use Aimed Shot on the Rootbound Knight")
    text = opened["visible_response"]["plain_text"]
    assert text.startswith("The fight begins: you against the Rootbound Knight.") and "You use Aimed Shot." in text
    assert play.public()["player"]["resources"]["stamina"]["current"] == 90
    assert play.stored()["state"]["ability_state"]["cooldowns"] == {"recon_aimed_shot": 1}
    again = play.turn("use Aimed Shot on the Rootbound Knight")
    assert again["visible_response"]["plain_text"] == "Aimed Shot is not ready yet (1 more turn)."
    frost = play.client.post(f"/api/rpg/sessions/{play.session_id}/loadout-action",
                             json={"action": "use_ability", "ability_name": "Frost Arrow"})
    assert frost.status_code == 200, frost.text[:300]
    assert "The Rootbound Knight is hindered." in frost.json()["event"]["detail"]
    assert play.public()["player"]["resources"]["mana"]["current"] == 18
    struck = play.turn("attack")
    assert struck["outcome"]["planned_action"] == "fight"
    for _ in range(20):
        if not play.combat().get("active"):
            break
        play.turn("attack")
    play.turn("I make camp and sleep for the night.")
    resources = play.public()["player"]["resources"]
    assert resources["stamina"]["current"] == 100 and resources["mana"]["current"] == 30


def test_a_won_fight_raises_a_level_whose_choice_waits_and_then_holds(launch) -> None:
    """RQ-5.3: the one curve levels the hero, with health and a choice that waits without blocking play; the choice
    raises an attribute or teaches an ability, usable from the next turn."""
    from app.apps.rpg.session.service import load_session, save_session

    play = launch("aurelia")
    play.to_the_wild()
    session = load_session(play.session_id)
    session["simulation_state"]["player_state"]["xp"] = 95  # five short of level 2
    session["state"]["player"]["xp"] = {"current": 95, "max": 100}
    save_session(session, compact=False)
    for _ in range(20):
        play.turn("I attack the Echo Wolf.")
        if not play.combat().get("active"):
            break
    player = play.player_state()
    assert player["level"] == 2 and player["level_choices_pending"] == 1
    assert player["resources"]["hp"]["max"] == 105  # 5 more health a level (constitution 10)
    play.turn("look around")  # play goes on while the choice waits
    raised = play.turn("raise my strength")
    assert raised["visible_response"]["plain_text"] == "Your strength rises to 12."
    assert play.player_state()["stats"]["strength"] == 12 and play.player_state()["level_choices_pending"] == 0
    again = play.turn("raise my strength")  # no choice waits now: the older path's own answer
    assert play.player_state()["stats"]["strength"] == 12 and again
