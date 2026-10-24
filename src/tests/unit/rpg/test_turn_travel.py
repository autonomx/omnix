"""Travel on the pipeline (RQ-2.1): roads, their time, who is there, quests advanced; refusals change nothing."""
from __future__ import annotations

from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules.quest.arrival import arrival_changes
from app.apps.rpg.session.turn.planning import PlannedAction
from app.apps.rpg.session.turn.travel import resolve_travel

WORLD = {
    "start_location_id": "loc:grove",
    "locations": {
        "loc:grove": {"name": "The Grove", "exits": {"east": "loc:village"}, "present_npcs": [{"id": "npc:liora", "name": "Liora"}]},
        "loc:village": {"name": "The Village", "description": "Farms and gate scars.", "region_id": "region:march",
                        "exits": {"west": "loc:grove", "north": "loc:ruins"},
                        "present_npcs": [{"id": "npc:orik", "name": "Orik"}]},
        "loc:ruins": {"name": "The Ruins", "exits": {"south": "loc:village"}},
    },
    "routes": [{"from": "loc:grove", "to": "loc:village", "travel_time": "20 minutes"},
               {"from": "loc:village", "to": "loc:ruins", "travel_time": "2 hours"}],
    "npcs": {"npc:orik": {"name": "Orik"}, "npc:liora": {"name": "Liora"}},
    "items": [{"id": "item:sigil", "name": "Wayfarer Sigil", "type": "trinket"}],
}


def _campaign(quests=()):
    return {
        "manifest": {"turn_count": 2}, "state": {"turn_count": 2, "title": "Wren in The Grove",
                                                 "current_location_name": "The Grove", "world": {}},
        "runtime_state": {"current_scene": {"present_npc_ids": ["npc:liora"]}},
        "simulation_state": {
            "world_model": WORLD, "tick": 3,
            "player_state": {"location_id": "loc:grove", "currency": {"gold": 0, "silver": 0, "copper": 5},
                             "inventory_state": {"currency": {"gold": 0, "silver": 0, "copper": 5}, "items": []},
                             "party_state": {"companions": [{"npc_id": "npc:liora", "name": "Liora"}]}},
            "quest_state": {"quests": [dict(quest) for quest in quests]},
        },
    }


def test_a_journey_moves_the_party_says_who_is_there_and_takes_the_roads_time() -> None:
    campaign = _campaign()
    travel = resolve_travel(PlannedAction(mechanic="travel", target_id="loc:village"), campaign)
    assert not travel.refused and travel.minutes == 20
    assert [change.type for change in travel.changes] == ["turn_counted", "location_changed", "presence_changed",
                                                          "time_advanced", "experience_gained"]  # a first visit
    assert travel.lines == ["You travel to The Village; the road takes 20 minutes.", "Here: Orik, Liora.",
                            "You gain 15 experience."]
    document, _ = reduce(campaign, travel.changes)
    simulation = document["simulation_state"]
    assert simulation["player_state"]["location_id"] == "loc:village" and simulation["previous_location"] == "loc:grove"
    assert simulation["location_state"]["current_location_id"] == "loc:village"
    assert simulation["player_state"]["party_state"]["companions"][0]["location_id"] == "loc:village"
    assert document["state"]["title"] == "Wren in The Village" and document["state"]["current_location_id"] == "loc:village"
    scene = document["runtime_state"]["current_scene"]
    assert scene["location_id"] == "loc:village" and scene["summary"] == "Farms and gate scars."
    assert scene["present_npc_ids"] == ["npc:orik", "npc:liora"]


def test_a_place_no_road_reaches_and_the_place_the_hero_is_in_are_refused_and_change_nothing_else() -> None:
    far = resolve_travel(PlannedAction(mechanic="travel", target_id="loc:ruins"), _campaign())
    assert far.refused and [change.type for change in far.changes] == ["turn_counted"]
    assert far.lines == ["No road leads straight from here to The Ruins. Available routes: The Village"]
    here = resolve_travel(PlannedAction(mechanic="travel", target_id="loc:grove"), _campaign())
    assert here.refused and here.lines[0].startswith("You are already in The Grove.")


def test_reaching_a_quests_last_place_completes_it_and_pays_its_rewards() -> None:
    quest = {"id": "quest:first-night", "title": "First Night", "status": "active",
             "locations": ["loc:grove", "loc:village"], "visited_locations": ["loc:grove"],
             "rewards": ["item:sigil", "20 silver", "companion trust"]}
    changes, lines = arrival_changes(_campaign([quest])["simulation_state"], "loc:village")
    assert [change.type for change in changes] == ["quest_place_reached", "quest_status_changed", "purse_changed",
                                                   "item_added", "experience_gained", "level_reached"]
    assert lines[:2] == ["Quest complete: First Night. You receive 20 silver, Wayfarer Sigil.",
                         "You gain 100 experience."]  # fifty for each of its places (progression.md, tuned)
    assert changes[2].delta_copper == 200
    halfway = {**quest, "visited_locations": []}
    changes, lines = arrival_changes(_campaign([halfway])["simulation_state"], "loc:village")
    assert [change.type for change in changes] == ["quest_place_reached"]
    assert lines == ["Progress on First Night: 1 of 2 places reached."]
