"""Playthrough: people who act on their goals (evolution roadmap EV-4's gate). Over a 200-turn run in Aurelia, its
people reach at least eight beats of their goals on the days the clock crosses, and the hero hears of each: by asking
the people of the village for news, by paying the guild for it, or by being there."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES

pytestmark = POSTGRES
TURNS = 200
VILLAGE = "location:aurelia:starfall-village"


def _reached(simulation: dict) -> list[str]:
    return [f"beat:{npc}:{goal}:{beat}" for npc, goals in sorted((simulation.get("npc_goal_state") or {}).items())
            for goal, held in sorted(goals.items()) for beat in held.get("beats") or ()]


def test_in_200_turns_people_reach_eight_beats_and_the_hero_hears_of_each(launch) -> None:
    play = launch("aurelia")
    play.turn("go to Starfall Village")
    turns = 1
    while turns < TURNS:
        people = play.simulation()["world_model"]["npcs"]
        asked = [people[npc]["name"] for npc in play.present() if npc in people][:3] if play.location() == VILLAGE else []
        for name in asked:
            play.turn(f"ask {name} for any news")
            turns += 1
        play.turn("wait until tomorrow morning")
        turns += 1
        if play.location() != VILLAGE:
            play.turn("go to Starfall Village")
            turns += 1
    simulation = play.simulation()
    reached = _reached(simulation)
    assert len(reached) >= 8, reached
    heard = {row["rumour_id"].partition("@")[0] for row in simulation["active_rumors"] if row.get("heard")}
    told = {row["text_id"] for row in simulation["active_rumors"]}
    assert [beat for beat in reached if beat in told and beat not in heard] == []  # each one's word reached the hero
    assert play.public()["word_heard"]
