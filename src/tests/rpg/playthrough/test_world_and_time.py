"""Playthrough: travel, practice, time passing, and coming back after time away (RQ-0.3)."""
from __future__ import annotations

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES, in_worlds

pytestmark = POSTGRES

NO_WORLD_MODEL = ("RQ-2.0: a lore-only world (Vesper-9) launches with an empty world model: it has no routes to "
                  "travel")
JOURNEYS = {
    "aurelia": [("go to Starfall Village", "location:aurelia:starfall-village"),
                ("go to Skybridge Pass", "location:aurelia:skybridge-pass"),
                ("go to Moonroot Ruins", "location:aurelia:moonroot-ruins"),
                ("go to Skybridge Pass", "location:aurelia:skybridge-pass"),
                ("go to Starfall Village", "location:aurelia:starfall-village"),
                ("go to Starfall Grove", "location:aurelia:arrival-grove")],
    "starter": [("go to the market", "location:market-road:market-square"),
                ("go to the tavern", "location:market-road:rusty-flagon")],
    "vesper": [("go to Tidebreak Docks", "ent:places:tidebreak-docks"),
               ("go to Black Rain Station", "ent:places:black-rain-station")],
}


@pytest.mark.parametrize("world", in_worlds(vesper=NO_WORLD_MODEL))
def test_travel_across_three_places_and_back(launch, world) -> None:
    play = launch(world)
    for count, (command, place) in enumerate(JOURNEYS[world], start=1):
        play.turn(command)
        assert play.location() == place, command
        assert play.turn_count() == count
        assert play.public()["current_location_name"] in play.model.told()  # the arrival is described
    if world == "aurelia":
        assert "npc:elyra-moonroot" not in play.present() and "npc:liora-fen" in play.present()


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_a_place_no_road_reaches_is_refused(launch, world) -> None:
    play = launch(world)
    play.turn("go to Starfall Village")
    refused = play.turn("go to Moonroot Ruins")  # two roads away
    assert play.location() == "location:aurelia:starfall-village"
    assert "No road leads straight from here to Moonroot Ruins" in refused["visible_response"]["plain_text"]
    refused = play.turn("go to Starfall Village")  # already there: not back out to the grove
    assert play.location() == "location:aurelia:starfall-village"
    assert "You are already in Starfall Village" in refused["visible_response"]["plain_text"]
    assert play.turn_count() == 3


@pytest.mark.parametrize("world", in_worlds())
def test_skill_practice_up_to_a_level(launch, world) -> None:
    play = launch(world)
    for _ in range(3):
        play.turn("Practice swordsmanship with a careful training drill.")
    skill = play.player_state()["skills"]["swordsmanship"]
    assert skill["level"] == 1 and skill["xp"] == 5  # 30 experience: level 1 at 25
    assert "Swordsmanship rises to level 1." in play.model.told()
    assert play.public()["player"]["skills"]["swordsmanship"]["level"] == 1  # the sheet shows it


@pytest.mark.parametrize("world", in_worlds())
def test_waiting_passes_time_on_needs(launch, world) -> None:
    play = launch(world)
    play.turn("wait")
    first = play.survival()
    for _ in range(3):
        play.turn("wait")
    later = play.survival()
    assert later["hunger"] > first["hunger"] and later["thirst"] > first["thirst"] and later["fatigue"] > first["fatigue"]
    assert play.turn_count() == 4


@pytest.mark.parametrize("world", in_worlds())
def test_idle_resume_is_a_turn_with_a_recap(launch, world) -> None:
    """RQ-2.7: the player returning after time away is a world_tick turn: committed with a patch, replayable like
    the rest, the world's clock moved on, no turn of the player's counted, and a recap without a model call."""
    from app.apps.rpg.narration.presentation.turn_outcome import TurnOutcome

    play = launch(world)
    play.turn("look around")
    revision, rows, turns, tick = play.revision(), len(play.turn_rows()), play.turn_count(), play.simulation()["tick"]
    calls = len(play.model.calls)
    resumed = play.client.post(f"/api/rpg/sessions/{play.session_id}/resume", json={"elapsed_seconds": 3600},
                               headers={"x-omnix-rpg-submission-id": "resume-1"})
    assert resumed.status_code == 200, resumed.text[:300]
    outcome = TurnOutcome.model_validate(resumed.json()["outcome"])
    assert outcome.kind == "world_tick" and play.model.roles(calls) == []
    assert "while you were away" in resumed.json()["visible_response"]["plain_text"]
    assert play.revision() == revision + 1 and play.turn_count() == turns
    assert len(play.turn_rows()) == rows + 1  # time away is a world_tick turn, replayable like the rest
    assert play.turn_rows()[-1]["state_delta"]
    assert play.simulation()["tick"] == tick + 12  # an hour away is the most the world catches up on


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_a_night_camped_in_the_wild_is_a_rest(launch, world) -> None:
    play = launch(world)
    for _ in range(3):
        play.turn("wait")
    fatigue = play.survival()["fatigue"]
    play.turn("I make camp and sleep for the night.")
    assert play.survival()["fatigue"] < fatigue
    assert play.player_state().get("rest_point") == play.location()
