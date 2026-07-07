from __future__ import annotations

from typing import Any

from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_overlay_projection import project_dynamic_map_overlay
from app.rpg.map_repository import default_map_repository
from app.rpg.map_projection import initial_map_session_state


def _session() -> dict[str, Any]:
    map_state = initial_map_session_state("rusty_flagon_tavern")
    return {
        "manifest": {"id": "session:test"},
        "state": {
            "world": {
                "time": "Day 2 • 21:00",
                "weather": "Snow",
                "light": "Moonlight",
                "visibility": "Low",
                "hidden_schedule": "do not expose",
            },
            "map_state": map_state,
        },
    }


def test_dynamic_overlay_projects_discovery_visibility_status_and_environment() -> None:
    session = _session()
    map_state = session["state"]["map_state"]
    map_state["visible_object_ids"] = ["building:frost_haven_inn"]
    map_state["object_states"] = {
        "building:frost_haven_inn": {
            "status": "occupied",
            "presentation_hint": "Warm lamplight fills the common room.",
        },
        "building:secret": {"status": "open", "presentation_hint": "must not leak"},
    }
    map_state["fog_polygons"] = [
        {"id": "fog:north", "points": [[5000, 500], [9800, 500], [9800, 2400], [5000, 2400]]}
    ]
    definition = default_map_repository().get(FROST_HAVEN_MAP_ID)

    dynamic = project_dynamic_map_overlay(session, definition)

    inn = next(item for item in dynamic.object_states if item.object_id == "building:frost_haven_inn")
    assert inn.discovered is True
    assert inn.visible is True
    assert inn.status == "occupied"
    assert inn.presentation_hint == "Warm lamplight fills the common room."
    assert all(item.object_id != "building:secret" for item in dynamic.object_states)
    assert dynamic.fog_polygons[0].id == "fog:north"
    assert dynamic.environment == {
        "time": "Day 2 • 21:00",
        "weather": "Snow",
        "light": "Moonlight",
        "visibility": "Low",
    }


def test_dynamic_overlay_normalizes_unknown_status_and_invalid_fog() -> None:
    session = _session()
    map_state = session["state"]["map_state"]
    map_state["object_states"] = {
        "building:frost_haven_inn": {"status": "future-secret", "presentation_hint": "x" * 400}
    }
    map_state["fog_polygons"] = [
        {"id": "fog:bad", "points": [[0, 0], [10, 10]]},
        {"id": "fog:crossed", "points": [[0, 0], [10, 10], [0, 10], [10, 0]]},
    ]
    definition = default_map_repository().get(FROST_HAVEN_MAP_ID)

    dynamic = project_dynamic_map_overlay(session, definition)
    inn = next(item for item in dynamic.object_states if item.object_id == "building:frost_haven_inn")

    assert inn.status == "normal"
    assert len(inn.presentation_hint) == 160
    assert dynamic.fog_polygons == ()
