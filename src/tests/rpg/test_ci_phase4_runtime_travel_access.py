def test_ci_phase4_runtime_travel_denies_undiscovered_route_without_mutation():
    from app.rpg.locations import OLD_MILL, RUSTY_FLAGON, apply_runtime_travel

    state = {}
    result = apply_runtime_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL, turn_index=1)

    assert result["ok"] is False
    assert result["reason"] == "undiscovered_location"
    assert result["access_result"]["reason"] == "undiscovered_location"
    assert result["travel_result"] is None
    assert "travel_state" not in state


def test_ci_phase4_runtime_travel_denies_blocked_route_without_mutation():
    from app.rpg.locations import (
        OLD_MILL,
        RUSTY_FLAGON,
        apply_runtime_travel,
        discover_location,
        discover_route,
    )

    state = {}
    discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=2)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted_old_road", turn_index=2)
    result = apply_runtime_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL, turn_index=3)

    assert result["ok"] is False
    assert result["reason"] == "route_blocked"
    assert result["access_result"]["blocked_routes"][0]["edge_id"] == "route:old_road:old_mill"
    assert result["travel_result"] is None
    assert "travel_state" not in state


def test_ci_phase4_runtime_travel_applies_only_after_route_accessible():
    from app.rpg.locations import (
        OLD_MILL,
        RUSTY_FLAGON,
        apply_runtime_travel,
        discover_location,
        discover_route,
        unblock_route,
    )

    state = {}
    discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=2)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted_old_road", turn_index=2)
    unblock_route(state, edge_id="route:old_road:old_mill", reason="bandit_threat_resolved", turn_index=4)
    result = apply_runtime_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL, turn_index=5)

    assert result["ok"] is True
    assert result["reason"] == "runtime_travel_applied"
    assert result["access_result"]["reason"] == "route_accessible"
    assert result["travel_result"]["reason"] == "travel_applied"
    assert state["travel_state"]["current_location_id"] == OLD_MILL
    assert state["travel_state"]["elapsed_minutes"] == 55
    assert state["travel_state"]["fatigue"] == 12
    assert state["travel_state"]["travel_log"][-1]["source"] == "deterministic_phase4_travel_costs"


def test_ci_phase4_runtime_travel_rejects_unknown_destination_before_travel_state_creation():
    from app.rpg.locations import RUSTY_FLAGON, apply_runtime_travel

    state = {}
    result = apply_runtime_travel(state, start_location_id=RUSTY_FLAGON, end_location_id="location:missing", turn_index=1)

    assert result["ok"] is False
    assert result["reason"] == "unknown_location"
    assert result["access_result"]["route"]["reason"] == "unknown_location"
    assert result["travel_result"] is None
    assert "travel_state" not in state


def test_ci_phase4_runtime_travel_narration_contract_limits_claims():
    from app.rpg.locations import (
        OLD_MILL,
        RUSTY_FLAGON,
        apply_runtime_travel,
        build_runtime_travel_narration_contract,
        discover_location,
        discover_route,
        unblock_route,
    )

    state = {}
    discover_location(state, location_id=OLD_MILL, reason="scouted", turn_index=1)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted", turn_index=1)
    unblock_route(state, edge_id="route:old_road:old_mill", reason="cleared", turn_index=2)
    result = apply_runtime_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL, turn_index=3)
    contract = build_runtime_travel_narration_contract(result)

    assert contract["source"] == "deterministic_phase4_runtime_travel_access"
    assert "Runtime travel result: runtime_travel_applied" in contract["allowed_runtime_travel_claims"]
    assert "Route access result: route_accessible" in contract["allowed_runtime_travel_claims"]
    assert "Travel minutes: 55" in contract["allowed_runtime_travel_claims"]
    assert "Do not bypass discovery or route-block validation for runtime travel commands." in contract[
        "forbidden_runtime_travel_claims"
    ]
    assert "Do not invent travel resource consumption or inventory changes." in contract[
        "forbidden_runtime_travel_claims"
    ]


def test_ci_phase4_runtime_travel_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_runtime_travel_access_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_runtime_travel_access_ready"
    assert readiness["blockers"] == []
    assert locations.apply_runtime_travel
    assert locations.build_runtime_travel_narration_contract
    assert locations.assert_phase4_runtime_travel_access_ready
