from __future__ import annotations

from typing import Any

from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_projection import (
    increment_map_overlay_revision,
    initial_map_session_state,
    project_session_map_overlay,
)


def _session() -> dict[str, Any]:
    return {
        "manifest": {"id": "session:test", "session_id": "session:test"},
        "state": {
            "session_id": "session:test",
            "current_turn": 7,
            "world": {"time": "Day 1 • 08:00", "weather": "Snow", "temperature": -4},
            "map_state": initial_map_session_state("rusty_flagon_tavern"),
        },
    }


def test_initial_map_state_is_explicit_and_revisioned() -> None:
    state = initial_map_session_state("rusty_flagon_tavern")

    assert state["schema_version"] == 1
    assert state["current_map_id"] == FROST_HAVEN_MAP_ID
    assert state["current_location_id"] == "rusty_flagon_tavern"
    assert state["overlay_revision"] == 0
    assert "building:frost_haven_inn" in state["visible_object_ids"]


def test_ready_overlay_projects_player_marker_and_environment() -> None:
    overlay = project_session_map_overlay(_session(), FROST_HAVEN_MAP_ID)

    assert overlay.availability == "ready"
    assert overlay.current_location_id == "rusty_flagon_tavern"
    assert overlay.session_turn_index == 7
    assert overlay.environment == {
        "time": "Day 1 • 08:00",
        "weather": "Snow",
        "temperature": "-4",
    }
    player = next(marker for marker in overlay.markers if marker.kind == "player")
    assert player.object_id == "building:frost_haven_inn"


def test_missing_map_state_returns_typed_unavailable_overlay() -> None:
    session = _session()
    session["state"].pop("map_state")

    overlay = project_session_map_overlay(session, FROST_HAVEN_MAP_ID)

    assert overlay.availability == "unavailable"
    assert overlay.unavailable_reason == "map_state_unavailable"
    assert overlay.current_location_id is None
    assert not overlay.markers


def test_unknown_authoritative_location_is_not_fabricated() -> None:
    session = _session()
    session["state"]["map_state"]["current_location_id"] = "location:missing"

    overlay = project_session_map_overlay(session, FROST_HAVEN_MAP_ID)

    assert overlay.availability == "unavailable"
    assert overlay.unavailable_reason == "current_location_not_in_definition"
    assert overlay.current_location_id is None


def test_route_lock_is_preserved_and_disables_matching_travel() -> None:
    session = _session()
    map_state = session["state"]["map_state"]
    map_state["route_states"]["route:frost_haven:market_inn"] = {
        "status": "locked",
        "known": True,
        "safe": True,
    }

    overlay = project_session_map_overlay(session, FROST_HAVEN_MAP_ID)

    route = next(item for item in overlay.routes if item.route_id == "route:frost_haven:market_inn")
    assert route.status == "locked"
    travel = next(
        item
        for item in overlay.capabilities
        if item.type == "travel" and item.target_object_id == "building:frost_haven_market"
    )
    assert travel.enabled is False
    assert travel.disabled_reason == "route_locked"


def test_increment_overlay_revision_preserves_location() -> None:
    state = _session()["state"]
    current_location = state["map_state"]["current_location_id"]

    revision = increment_map_overlay_revision(state)

    assert revision == 1
    assert state["map_state"]["overlay_revision"] == 1
    assert state["map_state"]["current_location_id"] == current_location
