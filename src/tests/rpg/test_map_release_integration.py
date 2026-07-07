from __future__ import annotations

from app.rpg.map_actions import MapActionRequest, apply_map_action
from app.rpg.map_fixtures import FROST_HAVEN_MAP_ID
from app.rpg.map_hierarchy_fixtures import FROSTED_FLAGON_INTERIOR_MAP_ID
from app.rpg.map_package_bridge import attach_map_state_to_package, restore_map_state_from_package
from app.rpg.map_projection import initial_map_session_state, project_session_map_overlay
from app.rpg.map_release import (
    json_round_trip_session,
    replay_map_projection,
    validate_map_release_session,
)


def _session() -> dict[str, object]:
    return {
        "manifest": {"id": "session:e2e", "session_id": "session:e2e"},
        "state": {
            "session_id": "session:e2e",
            "current_turn": 12,
            "player": {"location_id": "rusty_flagon_tavern"},
            "world": {"time": "Day 4 • 19:15", "weather": "Snow", "light": "Dusk"},
            "map_state": initial_map_session_state("rusty_flagon_tavern"),
        },
        "simulation_state": {"turn_index": 12},
        "runtime_state": {},
        "installed_packs": [],
    }


def test_definition_overlay_action_hierarchy_save_package_and_replay_flow() -> None:
    session = _session()
    initial_projection = replay_map_projection(session)
    settlement_overlay = project_session_map_overlay(session, FROST_HAVEN_MAP_ID)

    traveled = apply_map_action(
        session,
        FROST_HAVEN_MAP_ID,
        MapActionRequest(
            action="travel",
            target_object_id="building:frost_haven_market",
            route_id="route:frost_haven:market_inn",
            definition_revision=settlement_overlay.definition_revision,
            overlay_revision=settlement_overlay.overlay_revision,
            client_action_id="e2e:travel-market",
        ),
    )
    assert traveled["overlay"].current_location_id == "market_district"

    market_overlay = traveled["overlay"]
    returned = apply_map_action(
        traveled["session"],
        FROST_HAVEN_MAP_ID,
        MapActionRequest(
            action="travel",
            target_object_id="building:frost_haven_inn",
            route_id="route:frost_haven:market_inn",
            definition_revision=market_overlay.definition_revision,
            overlay_revision=market_overlay.overlay_revision,
            client_action_id="e2e:return-inn",
        ),
    )
    assert returned["overlay"].current_location_id == "rusty_flagon_tavern"

    entered = apply_map_action(
        returned["session"],
        FROST_HAVEN_MAP_ID,
        MapActionRequest(
            action="enter",
            target_object_id="building:frost_haven_inn",
            definition_revision=returned["overlay"].definition_revision,
            overlay_revision=returned["overlay"].overlay_revision,
            client_action_id="e2e:enter-inn",
        ),
    )
    assert entered["map_id"] == FROSTED_FLAGON_INTERIOR_MAP_ID
    assert entered["overlay"].availability == "ready"

    loaded = json_round_trip_session(entered["session"])
    loaded_projection = replay_map_projection(loaded)
    assert loaded_projection == replay_map_projection(entered["session"])
    assert loaded_projection.projection_digest != initial_projection.projection_digest
    assert validate_map_release_session(loaded).ready is True

    package = attach_map_state_to_package({"simulation_state": {"turn_index": 12}}, loaded)
    restored = restore_map_state_from_package(
        {
            "manifest": loaded["manifest"],
            "state": {"session_id": "session:e2e", "player": {}},
            "simulation_state": {"turn_index": 12},
        },
        package,
    )
    restored["state"]["current_turn"] = 12
    assert replay_map_projection(restored) == loaded_projection
    assert validate_map_release_session(restored).ready is True
