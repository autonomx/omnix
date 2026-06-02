def test_ci_phase4_travel_costs_validate_all_canonical_route_costs():
    from app.rpg.locations import ROUTE_TRAVEL_COSTS, validate_route_travel_costs

    validation = validate_route_travel_costs()

    assert validation["ok"] is True
    assert validation["reason"] == "route_travel_costs_valid"
    assert validation["route_cost_count"] == 5
    assert validation["blockers"] == []
    assert set(ROUTE_TRAVEL_COSTS) == {
        "route:rusty_flagon:old_road",
        "route:rusty_flagon:market",
        "route:market:old_road",
        "route:old_road:old_mill",
        "route:old_road:nearby_wilderness",
    }
    assert all(row["source"] == "deterministic_phase4_travel_costs" for row in ROUTE_TRAVEL_COSTS.values())


def test_ci_phase4_travel_costs_calculate_required_old_mill_totals():
    from app.rpg.locations import OLD_MILL, OLD_ROAD, RUSTY_FLAGON, calculate_route_travel_cost

    result = calculate_route_travel_cost(RUSTY_FLAGON, OLD_MILL)

    assert result["ok"] is True
    assert result["reason"] == "route_travel_cost_calculated"
    assert result["path"] == [RUSTY_FLAGON, OLD_ROAD, OLD_MILL]
    assert [row["edge_id"] for row in result["edge_costs"]] == [
        "route:rusty_flagon:old_road",
        "route:old_road:old_mill",
    ]
    assert result["totals"] == {"minutes": 55, "fatigue": 12, "ration_units": 1, "water_units": 2}
    assert result["risk_flags"] == ["low", "bandit_risk"]
    assert result["source"] == "deterministic_phase4_travel_costs"


def test_ci_phase4_travel_costs_apply_travel_mutates_only_travel_state():
    from app.rpg.locations import OLD_MILL, RUSTY_FLAGON, apply_travel

    state = {
        "player_state": {"inventory_state": {"items": [{"item_id": "item:ration", "quantity": 2}]}}
    }
    result = apply_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL, turn_index=12)

    assert result["ok"] is True
    assert result["reason"] == "travel_applied"
    assert result["before"] == {"location_id": RUSTY_FLAGON, "elapsed_minutes": 0, "fatigue": 0}
    assert result["after"] == {"location_id": OLD_MILL, "elapsed_minutes": 55, "fatigue": 12}
    assert state["travel_state"]["current_location_id"] == OLD_MILL
    assert state["travel_state"]["elapsed_minutes"] == 55
    assert state["travel_state"]["fatigue"] == 12
    assert state["travel_state"]["travel_log"][-1]["ration_units"] == 1
    assert state["travel_state"]["travel_log"][-1]["water_units"] == 2
    assert state["player_state"]["inventory_state"]["items"] == [{"item_id": "item:ration", "quantity": 2}]


def test_ci_phase4_travel_costs_reject_start_mismatch_and_unknown_destination():
    from app.rpg.locations import MARKET, OLD_MILL, RUSTY_FLAGON, apply_travel

    state = {"travel_state": {"current_location_id": MARKET}}
    mismatch = apply_travel(state, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL, turn_index=3)
    unknown = apply_travel(state, start_location_id=MARKET, end_location_id="location:imagined_castle", turn_index=4)

    assert mismatch["ok"] is False
    assert mismatch["reason"] == "travel_start_mismatch"
    assert mismatch["current_location_id"] == MARKET
    assert state["travel_state"]["current_location_id"] == MARKET
    assert unknown["ok"] is False
    assert unknown["reason"] == "unknown_destination"
    assert unknown["destination_id"] == "location:imagined_castle"


def test_ci_phase4_travel_costs_narration_contract_is_source_backed():
    from app.rpg.locations import OLD_MILL, RUSTY_FLAGON, apply_travel, build_travel_narration_contract

    result = apply_travel({}, start_location_id=RUSTY_FLAGON, end_location_id=OLD_MILL, turn_index=5)
    contract = build_travel_narration_contract(result)

    assert contract["source"] == "deterministic_phase4_travel_costs"
    assert "Travel path: location:rusty_flagon -> location:old_road -> location:old_mill" in contract["allowed_travel_claims"]
    assert "Travel minutes: 55" in contract["allowed_travel_claims"]
    assert "Fatigue increased by 12" in contract["allowed_travel_claims"]
    assert "Resource costs: ration_units=1, water_units=2" in contract["allowed_travel_claims"]
    assert "Do not invent travel time, fatigue, or resource costs." in contract["forbidden_travel_claims"]
    assert "Do not claim inventory items were consumed; this phase records travel resource costs only." in contract["forbidden_travel_claims"]


def test_ci_phase4_travel_costs_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_travel_costs_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_travel_costs_ready"
    assert readiness["blockers"] == []
    assert readiness["old_mill_cost"]["totals"] == {"minutes": 55, "fatigue": 12, "ration_units": 1, "water_units": 2}
    assert locations.apply_travel
    assert locations.calculate_route_travel_cost
    assert locations.build_travel_narration_contract
