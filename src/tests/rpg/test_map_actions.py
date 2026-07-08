from __future__ import annotations

from dataclasses import replace

import pytest

from app.rpg.map_actions import MapActionError, MapActionRequest, apply_map_action
from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_projection import initial_map_session_state, project_session_map_overlay
from app.rpg.map_repository import default_map_repository


def _session() -> dict[str, object]:
    return {
        "manifest": {"id": "session:test", "session_id": "session:test"},
        "state": {
            "session_id": "session:test",
            "current_turn": 3,
            "player": {"location_id": "rusty_flagon_tavern"},
            "map_state": initial_map_session_state("rusty_flagon_tavern"),
        },
    }


def _request(action: str, target: str, *, route_id: str | None = None, action_id: str | None = None) -> MapActionRequest:
    overlay = project_session_map_overlay(_session(), FROST_HAVEN_MAP_ID)
    return MapActionRequest(
        action=action,  # type: ignore[arg-type]
        target_object_id=target,
        definition_revision=overlay.definition_revision,
        overlay_revision=overlay.overlay_revision,
        route_id=route_id,
        client_action_id=action_id,
    )


def test_safe_travel_updates_authoritative_location_and_revision() -> None:
    session = _session()
    request = _request(
        "travel",
        "building:frost_haven_market",
        route_id="route:frost_haven:market_inn",
        action_id="action:travel-market",
    )

    result = apply_map_action(session, FROST_HAVEN_MAP_ID, request)
    state = result["session"]["state"]

    assert result["ok"] is True
    assert result["action_result"]["changed"] is True
    assert state["map_state"]["current_location_id"] == "market_district"
    assert state["map_state"]["overlay_revision"] == 1
    assert state["player"]["location_id"] == "market_district"
    assert session["state"]["map_state"]["current_location_id"] == "rusty_flagon_tavern"
    assert result["overlay"].current_location_id == "market_district"


def test_inspect_returns_object_truth_without_moving_player() -> None:
    session = _session()
    request = _request("inspect", "building:frost_haven_inn", action_id="action:inspect-inn")

    result = apply_map_action(session, FROST_HAVEN_MAP_ID, request)

    assert result["action_result"]["changed"] is False
    assert result["action_result"]["label"] == "The Frosted Flagon"
    assert result["session"]["state"]["map_state"]["current_location_id"] == "rusty_flagon_tavern"
    assert result["overlay"].overlay_revision == 0


def test_stale_definition_and_overlay_are_rejected() -> None:
    request = _request("inspect", "building:frost_haven_inn")

    with pytest.raises(MapActionError, match="stale_definition_revision") as definition_error:
        apply_map_action(_session(), FROST_HAVEN_MAP_ID, replace(request, definition_revision="sha256:stale"))
    assert definition_error.value.status_code == 409

    with pytest.raises(MapActionError, match="stale_overlay_revision") as overlay_error:
        apply_map_action(_session(), FROST_HAVEN_MAP_ID, replace(request, overlay_revision=99))
    assert overlay_error.value.status_code == 409


def test_locked_unsafe_unknown_and_expansion_reasons_are_truthful() -> None:
    cases = (
        ("locked", True, True, "", "route_locked"),
        ("open", True, False, "", "route_requires_encounter_check"),
        ("open", False, True, "", "route_unknown"),
        ("blocked", True, True, "target_requires_expansion", "target_requires_expansion"),
    )
    for status, known, safe, reason, expected in cases:
        session = _session()
        session["state"]["map_state"]["route_states"]["route:frost_haven:market_inn"] = {
            "status": status,
            "known": known,
            "safe": safe,
            "reason": reason,
        }
        overlay = project_session_map_overlay(session, FROST_HAVEN_MAP_ID)
        request = MapActionRequest(
            action="travel",
            target_object_id="building:frost_haven_market",
            definition_revision=overlay.definition_revision,
            overlay_revision=overlay.overlay_revision,
            route_id="route:frost_haven:market_inn",
        )
        with pytest.raises(MapActionError) as error:
            apply_map_action(session, FROST_HAVEN_MAP_ID, request)
        assert error.value.code == expected


def test_client_action_id_is_idempotent() -> None:
    first = apply_map_action(
        _session(),
        FROST_HAVEN_MAP_ID,
        _request("inspect", "building:frost_haven_inn", action_id="action:same"),
    )
    repeated_request = MapActionRequest(
        action="inspect",
        target_object_id="building:frost_haven_inn",
        definition_revision=first["overlay"].definition_revision,
        overlay_revision=first["overlay"].overlay_revision,
        client_action_id="action:same",
    )

    repeated = apply_map_action(first["session"], FROST_HAVEN_MAP_ID, repeated_request)

    assert repeated["idempotent"] is True
    assert repeated["action_result"]["target_object_id"] == "building:frost_haven_inn"
