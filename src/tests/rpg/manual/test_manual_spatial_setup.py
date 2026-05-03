from __future__ import annotations

from tests.rpg.manual.scenario_setup import apply_manual_scenario_setup_by_session_id
from tests.rpg.manual.scenarios.registry import build_service_scenarios
from tests.rpg.manual.session_helpers import _ensure_manual_session


def test_spatial_setup_persists_graph_to_manual_session():
    scenario = build_service_scenarios()["spatial_closed_door_blocks_movement"]
    session_id = "manual_service_test_spatial_setup"

    session = _ensure_manual_session(session_id)
    assert session

    ok = apply_manual_scenario_setup_by_session_id(
        session_id,
        scenario,
        scenario_name="spatial_closed_door_blocks_movement",
    )
    assert ok is True

    reloaded = _ensure_manual_session(session_id)
    graph = reloaded.get("simulation_state", {}).get("spatial_graph", {})

    assert graph.get("areas")
    assert graph.get("connections")
    assert graph.get("entity_locations", {}).get("player", {}).get("area_id") == "tavern_common_room"