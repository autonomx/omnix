"""Playthrough: creatures act like themselves (RQ-5.6; docs/rpg/design/encounters.md). The starter world authors its
bestiary's behaviours: the Bandit Archer shoots from ambush, the Quarry Husk keeps its post."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES


def test_an_ambusher_strikes_before_the_hero_and_a_guardian_lets_them_go(launch) -> None:
    play = launch("starter")
    play.to_the_wild()  # the road north, where no one lives
    play.turn("I attack the Bandit Archer.")
    combat = play.combat()
    archer = next(actor for actor in combat["participants"] if actor.startswith("enemy:"))
    assert combat["initiative_order"][0]["actor_id"] == archer
    log = [row for row in combat["combat_log"] if row.get("kind") == "attack"]
    assert log[0]["actor_id"] == archer  # the first blow is the archer's, before the hero's
    for _ in range(10):  # away from the archer, on the hero's own roll
        if not play.combat().get("active"):
            break
        play.turn("I break away and flee.")

    play.turn("I attack the Quarry Husk.")
    play.turn("I break away and flee.")  # once is enough: it keeps its post, and does not pursue
    combat = play.combat()
    assert combat["active"] is False and combat["ended_reason"] == "party_fled"
    assert not [row for row in combat["combat_log"] if row.get("kind") == "parting_blow"]
    assert "and escape; the fight is over" in play.model.told()


def test_on_a_dangerous_road_something_bars_the_way_and_can_be_slipped_past(launch) -> None:
    """Aurelia's roads are dangerous from the start (severity 70: a 30% chance where no one lives)."""
    play = launch("aurelia")
    play.turn("go to Starfall Village")
    for trip in range(24):
        arrived = play.turn("go to Skybridge Pass" if trip % 2 == 0 else "go to Starfall Village")
        if play.combat().get("active"):
            break
    else:
        raise AssertionError("no encounter in 24 journeys")
    assert play.location() == "location:aurelia:skybridge-pass"  # only where no one lives
    combat = play.combat()
    assert combat["current_actor_id"] == "player" and not [row for row in combat["combat_log"] if row.get("kind") == "attack"]
    assert "bars your way" in arrived["visible_response"]["plain_text"] or "bars your way" in play.model.told()
    play.turn("I sneak past it.")
    combat = play.combat()
    assert combat["active"] is False and combat["ended_reason"] == "evaded"
    assert "You go on your way; no blow was struck." in play.model.told()
    assert play.location() == "location:aurelia:skybridge-pass"
