"""Playthrough: Valecourt and Cinderhold have maps (evolution roadmap EV-8). Each place the world had left without a
grid now has one, and the hero who arrives stands on it."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES
VALECOURT, CINDERHOLD = "location:aurelia:valecourt", "location:aurelia:cinderhold"


def test_valecourt_and_cinderhold_are_played_on_their_own_maps(launch) -> None:
    play = launch("aurelia")
    places = play.simulation()["world_model"]["locations"]
    assert places[VALECOURT]["map_id"] and places[CINDERHOLD]["map_id"]
    assert not places[VALECOURT]["deferred"] and not places[CINDERHOLD]["deferred"]
    for _ in range(12):
        if play.location() == VALECOURT:
            break
        for _ in range(30):  # whatever bars the road is fought or fled
            if not play.combat().get("active"):
                break
            play.turn("I break away and flee.")
        play.turn("go to Valecourt")
    assert play.location() == VALECOURT
    assert places[VALECOURT]["map_id"] in play.stored()["state"]["current_map_instance_id"]
