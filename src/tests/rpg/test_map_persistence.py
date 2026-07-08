from __future__ import annotations

from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID, NORTHERN_PASS_MAP_ID
from app.rpg.map_persistence import ensure_session_map_state


def test_explicit_starting_location_initializes_authoritative_map_state() -> None:
    session = {
        "manifest": {"id": "session:test"},
        "setup_payload": {"starting_location": "rusty_flagon_tavern"},
        "state": {"player": {}},
    }

    normalized = ensure_session_map_state(session)

    assert normalized["state"]["map_state"]["current_map_id"] == FROST_HAVEN_MAP_ID
    assert normalized["state"]["map_state"]["current_location_id"] == "rusty_flagon_tavern"
    assert normalized["state"]["current_location_id"] == "rusty_flagon_tavern"
    assert normalized["state"]["player"]["location_id"] == "rusty_flagon_tavern"


def test_demo_preset_initializes_region_map_without_display_label_inference() -> None:
    session = {
        "manifest": {"id": "session:demo", "created_from_preset": "demo_glimmerdeep_pass_lvl14"},
        "setup_payload": {"preset_id": "demo_glimmerdeep_pass_lvl14"},
        "state": {"location": "A translated display label", "player": {}},
    }

    normalized = ensure_session_map_state(session)

    assert normalized["state"]["map_state"]["current_map_id"] == NORTHERN_PASS_MAP_ID
    assert normalized["state"]["map_state"]["current_location_id"] == "glimmerdeep_pass"


def test_display_label_alone_does_not_create_map_state() -> None:
    session = {
        "manifest": {"id": "session:legacy"},
        "state": {"location": "Rusty Flagon Tavern", "current_location": "Rusty Flagon Tavern"},
    }

    normalized = ensure_session_map_state(session)

    assert "map_state" not in normalized["state"]
    assert "current_location_id" not in normalized["state"]


def test_existing_versioned_map_state_is_preserved() -> None:
    map_state = {
        "schema_version": 1,
        "current_map_id": "map:custom",
        "current_location_id": "location:custom",
        "overlay_revision": 9,
    }
    session = {
        "manifest": {"id": "session:test"},
        "setup_payload": {"starting_location": "rusty_flagon_tavern"},
        "state": {"map_state": map_state},
    }

    normalized = ensure_session_map_state(session)

    assert normalized["state"]["map_state"] is map_state
    assert normalized["state"]["map_state"]["overlay_revision"] == 9
