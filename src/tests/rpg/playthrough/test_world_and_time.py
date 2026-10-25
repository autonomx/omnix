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


@pytest.mark.parametrize("world", in_worlds())
def test_travel_across_three_places_and_back(launch, world) -> None:
    play = launch(world)
    for command, place in JOURNEYS[world]:
        turns = play.turn_count()
        play.turn(command)
        assert play.location() == place, command
        assert play.turn_count() == turns + 1  # a journey is one turn
        assert play.public()["current_location_name"] in play.model.told()  # the arrival is described
        play.clear_the_road()  # the roads of a dangerous region may hold something (encounters.md)
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
    """RQ-5.3: an hour's practice is 5 experience in the skill; rank 1 takes 50 (progression.md)."""
    play = launch(world)
    for _ in range(10):
        play.turn("Practice swordsmanship with a careful training drill.")
    skill = play.player_state()["skills"]["swordsmanship"]
    assert skill["level"] == 1 and skill["xp"] == 0 and skill["xp_to_next"] == 100
    assert "Swordsmanship rises to rank 1." in play.model.told()
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


def test_the_world_map_is_the_worlds_own_and_its_journeys_are_turns(launch) -> None:
    """RQ-2.8 and §3: a published world's visual map shows its own regions (never the built-in fixture maps), and a
    journey chosen on it is a travel turn: the hero moves in the simulation too, and the clock moves."""
    play = launch("aurelia")
    state = play.stored()["state"]
    map_id = state["map_state"]["current_map_id"]
    assert map_id.startswith("region:generated:") and "northern_pass" not in map_id
    overlay = play.client.get(f"/api/rpg/sessions/{play.session_id}/maps/{map_id}/overlay")
    assert overlay.status_code == 200, overlay.text[:300]
    body = overlay.json()
    capability = next(item for item in body["overlay"]["capabilities"] if item["type"] == "travel" and item["enabled"])
    turns = play.turn_count()
    acted = play.client.post(f"/api/rpg/sessions/{play.session_id}/maps/{map_id}/map-actions", json={
        "action": "travel", "target_object_id": capability["target_object_id"], "route_id": capability.get("route_id"),
        "definition_revision": body["definition_revision"], "overlay_revision": body["overlay_revision"]})
    assert acted.status_code == 200, acted.text[:300]
    destination = acted.json()["action_result"]["current_location_id"]
    assert play.location() == destination != "location:aurelia:arrival-grove"
    assert play.turn_count() == turns + 1


def test_the_worlds_people_keep_their_day(launch) -> None:
    """RQ-2.7: routines run on the one clock. Away from the hero, people are where their day puts them; someone in
    the scene with the hero stays until their day turns, and the hero sees who comes and goes."""
    play = launch("starter")  # the Rusty Flagon at 08:00: Bran and Mira in the common room
    assert play.present() == ["npc:bran", "npc:mira"]

    def said(turn: dict) -> str:
        return turn["visible_response"]["plain_text"]

    arrival = play.turn("go to the market")  # 08:05: Mira's day has her at the market now, Aldric out on the road
    assert play.present() == ["npc:mira", "npc:elara", "npc:tomas"]
    assert "Mira (listening to the stallholders)" in said(arrival) and "Aldric" not in said(arrival)
    assert "Location:" not in said(arrival)  # the destination is no speaker, so no lore of a person named for it
    for _ in range(11):  # to 13:35
        play.turn("wait a while")
    assert "npc:aldric" not in play.present()
    waited = play.turn("wait a while")  # 14:05: his patrol over, he keeps order in the square
    assert "Captain Aldric arrives, keeping order in the square." in said(waited)
    assert play.present()[-1] == "npc:aldric"
    aldric = play.simulation()["npc_index"]["npc:aldric"]
    assert (aldric["location_id"], aldric["activity"]) == ("location:market-road:market-square",
                                                            "keeping order in the square")
    for _ in range(3):  # to 15:35: Mira stays while the hero is with her
        play.turn("wait a while")
    assert "npc:mira" in play.present()
    waited = play.turn("wait a while")  # 16:05: her day turns to the evening in the tavern
    assert "Mira leaves for Rusty Flagon Tavern." in said(waited) and "npc:mira" not in play.present()
    back = play.turn("go to the tavern")
    assert play.present() == ["npc:bran", "npc:mira"]
    assert "Mira (watching the common room)" in said(back)
    assert play.stored()["runtime_state"]["current_scene"]["actors"] == ["Bran", "Mira"]


def test_time_passing_on_its_own_is_a_world_tick_turn(launch) -> None:
    """RQ-2.7: ``/spatial-ticks`` lets the world go on with no player action, as a world_tick turn committed like the
    rest; ``/spatial-state`` reads where everyone is from the campaign."""
    from app.apps.rpg.narration.presentation.turn_outcome import TurnOutcome

    play = launch("starter")
    revision, turns, rows, calls = play.revision(), play.turn_count(), len(play.turn_rows()), len(play.model.calls)
    ticked = play.client.post(f"/api/rpg/campaigns/{play.session_id}/spatial-ticks", json={"ticks": 3},
                              headers={"x-omnix-rpg-submission-id": "ticks-1"})
    assert ticked.status_code == 200, ticked.text[:300]
    assert TurnOutcome.model_validate(ticked.json()["outcome"]).kind == "world_tick" and play.model.roles(calls) == []
    assert ticked.json()["visible_response"]["plain_text"].startswith("Time passes in Rusty Flagon Tavern.")
    assert play.revision() == revision + 1 and play.turn_count() == turns and len(play.turn_rows()) == rows + 1
    state = play.client.get(f"/api/rpg/campaigns/{play.session_id}/spatial-state")
    assert state.status_code == 200, state.text[:300]
    body = state.json()
    assert body["absolute_minutes"] == 8 * 60 + 30 and body["present_npc_ids"] == ["npc:bran", "npc:mira"]
    aldric = next(person for person in body["people"] if person["npc_id"] == "npc:aldric")
    assert (aldric["location_name"], aldric["activity"]) == ("Northern Road", "patrolling the road")
    assert play.client.post(f"/api/rpg/campaigns/{play.session_id}/spatial-ticks", json={"ticks": 13}).status_code == 422


def test_a_wizard_campaign_without_world_forge_sets_out_in_the_starter_world(launch) -> None:
    """§4.4: every campaign plays from a world. The creation wizard's campaign with no World Forge was the engine's
    built-in tavern (another copy of the starter town, with no world model, so no mechanic of the pipeline ran in
    it); it is the starter world's opening for the chosen place, with the wizard's hero and genesis attached."""
    play = launch("genesis")
    stored = play.stored()
    assert stored["state"]["world_binding"]["world_id"].startswith("world:the-market-road-")
    assert play.location() == "location:market-road:rusty-flagon" and play.present() == ["npc:bran", "npc:mira"]
    assert stored["state"]["genesis_snapshot"]["identity"]["origin"] == "frontier_village"  # the wizard's hero
    assert stored["state"]["metadata"]["seed"] == 0  # the wizard's own seed, 0 included
    assert stored["runtime_state"]["creation_progress"]["stage"] == "ready_first_turn"
    play.turn("go to the market")  # travel on the pipeline: the world model's roads
    assert play.location() == "location:market-road:market-square"
