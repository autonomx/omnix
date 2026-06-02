def test_ci_phase4_discovery_state_seeds_known_starter_locations_and_routes():
    from app.rpg.locations import (
        MARKET,
        OLD_ROAD,
        RUSTY_FLAGON,
        ensure_discovery_state,
    )

    state = {}
    discovery_state = ensure_discovery_state(state)

    assert discovery_state["source"] == "deterministic_phase4_discovery_route_blocking"
    assert discovery_state["discovered_locations"] == [RUSTY_FLAGON, MARKET, OLD_ROAD]
    assert discovery_state["discovered_routes"] == [
        "route:rusty_flagon:old_road",
        "route:rusty_flagon:market",
        "route:market:old_road",
    ]
    assert discovery_state["route_blocks"]["route:old_road:old_mill"]["blocked"] is True
    assert discovery_state["discovery_log"] == []
    assert state["discovery_state"] is discovery_state


def test_ci_phase4_discovery_blocks_undiscovered_old_mill_then_blocked_route_then_accessible():
    from app.rpg.locations import (
        OLD_MILL,
        RUSTY_FLAGON,
        discover_location,
        discover_route,
        unblock_route,
        validate_route_access,
    )

    state = {}
    initial = validate_route_access(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL)
    found_location = discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=2)
    found_route = discover_route(state, edge_id="route:old_road:old_mill", reason="scouted_old_road", turn_index=2)
    blocked = validate_route_access(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL)
    unblocked = unblock_route(state, edge_id="route:old_road:old_mill", reason="bandit_threat_resolved", turn_index=8)
    accessible = validate_route_access(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL)

    assert initial["ok"] is False
    assert initial["reason"] == "undiscovered_location"
    assert initial["unknown_locations"] == [OLD_MILL]
    assert found_location["ok"] is True
    assert found_location["reason"] == "location_discovered"
    assert found_route["ok"] is True
    assert found_route["reason"] == "route_discovered"
    assert blocked["ok"] is False
    assert blocked["reason"] == "route_blocked"
    assert blocked["blocked_routes"][0]["edge_id"] == "route:old_road:old_mill"
    assert blocked["blocked_routes"][0]["reason"] == "bandit_threat_unresolved"
    assert unblocked["ok"] is True
    assert unblocked["reason"] == "route_unblocked"
    assert accessible["ok"] is True
    assert accessible["reason"] == "route_accessible"
    assert accessible["route"]["path"] == [RUSTY_FLAGON, "location:old_road", OLD_MILL]


def test_ci_phase4_discovery_route_blocking_can_reblock_accessible_route():
    from app.rpg.locations import (
        OLD_MILL,
        RUSTY_FLAGON,
        block_route,
        discover_location,
        discover_route,
        unblock_route,
        validate_route_access,
    )

    state = {}
    discover_location(state, location_id=OLD_MILL, reason="scouted", turn_index=1)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted", turn_index=1)
    unblock_route(state, edge_id="route:old_road:old_mill", reason="cleared", turn_index=2)
    open_access = validate_route_access(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL)
    blocked_result = block_route(
        state,
        edge_id="route:old_road:old_mill",
        reason="bridge_collapse",
        summary="A collapsed bridge blocks the mill spur.",
        turn_index=3,
    )
    blocked_access = validate_route_access(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL)

    assert open_access["ok"] is True
    assert blocked_result["ok"] is True
    assert blocked_result["route_block"]["blocked"] is True
    assert blocked_result["route_block"]["reason"] == "bridge_collapse"
    assert blocked_access["ok"] is False
    assert blocked_access["reason"] == "route_blocked"
    assert blocked_access["blocked_routes"][0]["summary"] == "A collapsed bridge blocks the mill spur."


def test_ci_phase4_discovery_accessible_map_marks_discovered_and_blocked_exits():
    from app.rpg.locations import (
        OLD_MILL,
        OLD_ROAD,
        RUSTY_FLAGON,
        build_accessible_location_map_payload,
        discover_location,
        discover_route,
    )

    state = {}
    discover_location(state, location_id=OLD_MILL, reason="rumor", turn_index=2)
    discover_route(state, edge_id="route:old_road:old_mill", reason="rumor", turn_index=2)
    payload = build_accessible_location_map_payload(state, current_location_id=OLD_ROAD)
    mill_exit = [row for row in payload["visible_exits"] if row["destination_id"] == OLD_MILL][0]

    assert payload["source"] == "deterministic_phase4_discovery_route_blocking"
    assert payload["current_location_id"] == OLD_ROAD
    assert OLD_MILL in payload["discovered_locations"]
    assert "route:old_road:old_mill" in payload["discovered_routes"]
    assert mill_exit["discovered"] is True
    assert mill_exit["blocked"] is True
    assert mill_exit["block"]["reason"] == "bandit_threat_unresolved"
    assert RUSTY_FLAGON in payload["discovered_locations"]


def test_ci_phase4_discovery_narration_contract_limits_claims():
    from app.rpg.locations import OLD_MILL, RUSTY_FLAGON, build_discovery_narration_contract, validate_route_access

    result = validate_route_access({}, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL)
    contract = build_discovery_narration_contract(result)

    assert contract["source"] == "deterministic_phase4_discovery_route_blocking"
    assert "Route access result: undiscovered_location" in contract["allowed_discovery_claims"]
    assert "Undiscovered locations: location:old_mill" in contract["allowed_discovery_claims"]
    assert "Do not reveal undiscovered locations as known to the player." in contract["forbidden_discovery_claims"]
    assert "Do not claim a blocked route is passable unless validate_route_access returned ok=true." in contract[
        "forbidden_discovery_claims"
    ]


def test_ci_phase4_discovery_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_discovery_route_blocking_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_discovery_route_blocking_ready"
    assert readiness["blockers"] == []
    assert locations.validate_route_access
    assert locations.discover_location
    assert locations.discover_route
    assert locations.block_route
    assert locations.unblock_route
    assert locations.build_accessible_location_map_payload
