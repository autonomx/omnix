from __future__ import annotations

from copy import deepcopy

from app.rpg.map_actions import MapActionRequest, apply_map_action
from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_projection import initial_map_session_state, project_session_map_overlay
from app.rpg.map_release import (
    json_round_trip_session,
    map_state_digest,
    persisted_map_state,
    replay_map_projection,
    validate_map_release_session,
)


def _session() -> dict[str, object]:
    return {
        "manifest": {"id": "session:release", "session_id": "session:release"},
        "state": {
            "session_id": "session:release",
            "current_turn": 9,
            "player": {"location_id": "rusty_flagon_tavern"},
            "world": {"time": "Day 3 • 08:30", "weather": "Clear"},
            "map_state": initial_map_session_state("rusty_flagon_tavern"),
        },
    }


def test_json_save_load_round_trip_preserves_map_state_and_projection_digest() -> None:
    session = _session()
    before = replay_map_projection(session)

    loaded = json_round_trip_session(session)
    after = replay_map_projection(loaded)

    assert persisted_map_state(loaded) == persisted_map_state(session)
    assert after == before
    assert validate_map_release_session(loaded).ready is True


def test_browser_viewport_and_selection_are_excluded_from_persisted_digest() -> None:
    session = _session()
    baseline = map_state_digest(session)
    with_browser_state = deepcopy(session)
    with_browser_state["state"]["map_state"].update({
        "viewport": {"zoom": 3.5, "panX": -400, "panY": 80},
        "selected_object_id": "building:frost_haven_market",
        "hover_object_id": "building:frost_haven_inn",
        "ui_state": {"labels": False},
    })

    assert map_state_digest(with_browser_state) == baseline
    assert "viewport" not in persisted_map_state(with_browser_state)
    assert "selected_object_id" not in persisted_map_state(with_browser_state)


def test_authoritative_map_action_changes_save_and_replay_hashes() -> None:
    session = _session()
    overlay = project_session_map_overlay(session, FROST_HAVEN_MAP_ID)
    result = apply_map_action(
        session,
        FROST_HAVEN_MAP_ID,
        MapActionRequest(
            action="travel",
            target_object_id="building:frost_haven_market",
            route_id="route:frost_haven:market_inn",
            definition_revision=overlay.definition_revision,
            overlay_revision=overlay.overlay_revision,
            client_action_id="release:travel",
        ),
    )

    assert map_state_digest(result["session"]) != map_state_digest(session)
    assert replay_map_projection(result["session"]).projection_digest != replay_map_projection(session).projection_digest
    assert validate_map_release_session(result["session"]).ready is True


def test_release_gate_detects_missing_and_mismatched_authoritative_location() -> None:
    missing = _session()
    missing["state"].pop("map_state")
    assert validate_map_release_session(missing).issues == (
        "map_state_unavailable",
        "map_state_schema_unsupported",
        "current_map_id_unavailable",
        "current_location_id_unavailable",
    )

    mismatched = _session()
    mismatched["state"]["player"]["location_id"] = "old_quarry"
    report = validate_map_release_session(mismatched)
    assert report.ready is False
    assert "player_map_location_mismatch" in report.issues
