from __future__ import annotations

from copy import deepcopy

from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_living_overlay import project_living_map_markers
from app.rpg.map_living_state import merge_living_overlay_payload, project_living_map_state
from app.rpg.map_repository import default_map_repository


def _session() -> dict[str, object]:
    definition = default_map_repository().get(FROST_HAVEN_MAP_ID)
    visible = [item.id for item in definition.objects]
    return {
        "state": {
            "map_state": {
                "current_map_id": FROST_HAVEN_MAP_ID,
                "discovered_object_ids": visible,
                "visible_object_ids": visible,
            },
            "world": {
                "time": "Day 8 21:10",
                "weather": "Snow",
                "season": "Winter",
                "light": "Moonlight",
                "visibility": "Low",
            },
            "world_graph": {
                "routes": [
                    {
                        "id": "route:frost_haven:market_inn",
                        "status": "blocked",
                        "known": True,
                        "safe": False,
                        "reason": "avalanche debris",
                    }
                ]
            },
            "map_presence": [
                {
                    "id": "marker:npc:bran",
                    "kind": "npc",
                    "map_id": FROST_HAVEN_MAP_ID,
                    "object_id": "building:frost_haven_inn",
                    "visible_to_player": True,
                    "discovered": True,
                    "label": "Bran",
                },
                {
                    "id": "marker:quest:quarry",
                    "kind": "quest",
                    "map_id": FROST_HAVEN_MAP_ID,
                    "x": 5300,
                    "y": 1200,
                    "visible_to_player": True,
                    "discovered": True,
                    "label": "Follow the bandit trail",
                },
                {
                    "id": "marker:event:hidden",
                    "kind": "event",
                    "map_id": FROST_HAVEN_MAP_ID,
                    "x": 9000,
                    "y": 800,
                    "visible_to_player": False,
                    "discovered": False,
                    "label": "Secret ambush",
                },
            ],
            "map_object_states": [
                {
                    "map_id": FROST_HAVEN_MAP_ID,
                    "object_id": "building:frost_haven_smithy",
                    "status": "closed",
                    "visible_to_player": True,
                    "presentation_hint": "The forge is shuttered for the night.",
                }
            ],
        }
    }


def test_living_markers_are_explicit_redacted_and_stable() -> None:
    session = _session()
    before = deepcopy(session)
    definition = default_map_repository().get(FROST_HAVEN_MAP_ID)

    projection = project_living_map_markers(session, definition)

    assert [item["id"] for item in projection.markers] == [
        "marker:npc:bran",
        "marker:quest:quarry",
    ]
    npc = projection.markers[0]
    inn = next(item for item in definition.objects if item.id == "building:frost_haven_inn")
    assert (npc["x"], npc["y"]) == (inn.x, inn.y)
    assert all(item["id"] != "marker:event:hidden" for item in projection.markers)
    assert session == before


def test_living_route_object_and_environment_state_is_lossless() -> None:
    definition = default_map_repository().get(FROST_HAVEN_MAP_ID)

    living = project_living_map_state(_session(), definition)

    route = next(item for item in living.routes if item["route_id"] == "route:frost_haven:market_inn")
    assert route == {
        "route_id": "route:frost_haven:market_inn",
        "status": "blocked",
        "known": True,
        "safe": False,
        "reason": "avalanche debris",
    }
    assert living.object_states == (
        {
            "object_id": "building:frost_haven_smithy",
            "discovered": True,
            "visible": True,
            "status": "closed",
            "presentation_hint": "The forge is shuttered for the night.",
        },
    )
    assert living.environment == {
        "time": "Day 8 21:10",
        "weather": "Snow",
        "season": "Winter",
        "light": "Moonlight",
        "visibility": "Low",
    }


def test_living_projection_merges_without_removing_player_marker() -> None:
    definition = default_map_repository().get(FROST_HAVEN_MAP_ID)
    session = _session()
    markers = project_living_map_markers(session, definition)
    living = project_living_map_state(session, definition)
    base = {
        "markers": [
            {
                "id": "marker:player",
                "kind": "player",
                "x": 100,
                "y": 200,
                "object_id": "building:frost_haven_inn",
                "label": "You",
            }
        ],
        "object_states": [],
        "routes": [],
        "environment": {"temperature": "-9"},
    }

    payload = merge_living_overlay_payload(base, markers.markers, living)

    assert [item["id"] for item in payload["markers"]] == [
        "marker:npc:bran",
        "marker:player",
        "marker:quest:quarry",
    ]
    assert payload["environment"]["temperature"] == "-9"
    assert payload["environment"]["light"] == "Moonlight"


def test_marker_on_hidden_object_is_redacted() -> None:
    session = _session()
    map_state = session["state"]["map_state"]
    map_state["visible_object_ids"].remove("building:frost_haven_inn")
    definition = default_map_repository().get(FROST_HAVEN_MAP_ID)

    projection = project_living_map_markers(session, definition)

    assert all(item["id"] != "marker:npc:bran" for item in projection.markers)
