"""The play screen's "Here": who is present and where the paths lead, by name, and nothing else of the world."""
from __future__ import annotations

import json

from app.apps.rpg.edge.api.payloads.player_view import player_session_view
from app.apps.rpg.rules.routines import paths_from


def _campaign() -> dict:
    return {
        "state": {},
        "runtime_state": {},
        "simulation_state": {
            "player_state": {"location_id": "place:docks"},
            "present_npc_state": {"location_id": "place:docks", "present_npc_ids": ["npc:helix", "npc:gone", "npc:helix"]},
            "world_model": {
                "npcs": {"npc:helix": {"name": "Helix", "secrets": ["sold the cargo"]}},
                "locations": {
                    "place:docks": {"name": "Tidebreak Docks", "exits": {
                        "the market": "place:market", "market": "place:market", "the gate": "place:gate", "nowhere": "place:none"}},
                    "place:market": {"name": "Night Market"},
                    "place:gate": {"name": "Flood Gate", "description": "Its keeper is the traitor."},
                },
            },
        },
    }


def test_here_names_the_people_present_and_the_paths_from_this_place() -> None:
    assert player_session_view(_campaign())["here"] == {"people": ["Helix"], "exits": ["Night Market", "Flood Gate"]}


def test_here_carries_no_secret_of_the_world() -> None:
    shown = json.dumps(player_session_view(_campaign()))
    assert "sold the cargo" not in shown
    assert "traitor" not in shown
    assert "world_model" not in shown


def test_a_campaign_with_no_world_model_has_no_one_and_nowhere_to_show() -> None:
    assert player_session_view({"state": {}, "simulation_state": {}})["here"] == {"people": [], "exits": []}


def test_paths_from_leaves_out_a_place_the_world_does_not_name() -> None:
    world = {"locations": {"a": {"exits": {"north": "b", "south": "c"}}, "b": {"name": "B"}, "c": {}}}
    assert paths_from(world, "a") == ["B"]
    assert paths_from(world, "unknown") == []
