from copy import deepcopy


def _old_mill_ready_state():
    from app.rpg.locations import OLD_MILL, discover_location, discover_route, unblock_route

    state = {
        "player_state": {
            "inventory_state": {
                "items": [
                    {"item_id": "ration", "qty": 1},
                    {"item_id": "water_skin", "qty": 2},
                ]
            },
            "survival_state": {"hunger": 10, "thirst": 10},
        }
    }
    discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=1)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted_old_road", turn_index=1)
    unblock_route(state, edge_id="route:old_road:old_mill", reason="bandit_threat_resolved", turn_index=2)
    return state


def test_ci_phase4_travel_resource_preflight_counts_canonical_items():
    from app.rpg.locations import validate_travel_resources_available

    state = {
        "player_state": {
            "inventory_state": {
                "items": [
                    {"item_id": "ration", "qty": 1},
                    {"item_id": "trail_ration", "qty": 2},
                    {"item_id": "water_skin", "qty": 1},
                ]
            }
        }
    }

    enough = validate_travel_resources_available(state, ration_units=3, water_units=1)
    missing = validate_travel_resources_available(state, ration_units=4, water_units=2)

    assert enough["ok"] is True
    assert enough["reason"] == "travel_resources_available"
    assert enough["available"] == {"ration_units": 3, "water_units": 1}
    assert missing["ok"] is False
    assert missing["reason"] == "insufficient_travel_resources"
    assert {row["kind"] for row in missing["missing"]} == {"ration_units", "water_units"}
    assert missing["source"] == "deterministic_phase4_travel_resource_consumption"


def test_ci_phase4_travel_resource_rejects_before_travel_without_mutation():
    from app.rpg.locations import OLD_ROAD, RUSTY_FLAGON, apply_runtime_travel_with_resource_consumption

    state = {"player_state": {"inventory_state": {"items": []}}}
    before = deepcopy(state)

    result = apply_runtime_travel_with_resource_consumption(
        state,
        start_location_id=RUSTY_FLAGON,
        end_location_id=OLD_ROAD,
        turn_index=4,
    )

    assert result["ok"] is False
    assert result["reason"] == "insufficient_travel_resources"
    assert result["travel_result"] is None
    assert "travel_state" not in state
    assert state == before


def test_ci_phase4_travel_resource_consumes_after_guarded_runtime_travel():
    from app.rpg.locations import OLD_MILL, RUSTY_FLAGON, apply_runtime_travel_with_resource_consumption

    state = _old_mill_ready_state()
    result = apply_runtime_travel_with_resource_consumption(
        state,
        start_location_id=RUSTY_FLAGON,
        end_location_id=OLD_MILL,
        turn_index=5,
    )

    assert result["ok"] is True
    assert result["reason"] == "runtime_travel_resources_consumed"
    assert result["travel_result"]["reason"] == "runtime_travel_applied"
    assert state["travel_state"]["current_location_id"] == OLD_MILL
    assert state["travel_state"]["last_travel"]["ration_units"] == 1
    assert state["travel_state"]["last_travel"]["water_units"] == 2
    assert state["player_state"]["inventory_state"]["items"] == []
    survival_log = state["economy_state"]["survival_log"]
    assert [row["action_type"] for row in survival_log] == ["consume_food", "consume_water", "consume_water"]
    assert state["economy_state"]["travel_resource_log"][-1]["source"] == "deterministic_phase4_travel_resource_consumption"


def test_ci_phase4_travel_resource_consumption_contract_limits_claims():
    from app.rpg.locations import (
        OLD_MILL,
        RUSTY_FLAGON,
        apply_runtime_travel_with_resource_consumption,
        build_travel_resource_narration_contract,
    )

    result = apply_runtime_travel_with_resource_consumption(
        _old_mill_ready_state(),
        start_location_id=RUSTY_FLAGON,
        end_location_id=OLD_MILL,
        turn_index=6,
    )
    contract = build_travel_resource_narration_contract(result)

    assert contract["source"] == "deterministic_phase4_travel_resource_consumption"
    assert "Travel resource result: runtime_travel_resources_consumed" in contract["allowed_travel_resource_claims"]
    assert "Consumed travel resources: ration_units=1, water_units=2" in contract["allowed_travel_resource_claims"]
    assert any("Do not claim ration or water was consumed" in row for row in contract["forbidden_travel_resource_claims"])
    assert any("Do not mutate inventory directly" in row for row in contract["forbidden_travel_resource_claims"])


def test_ci_phase4_travel_resource_consumption_readiness_and_exports():
    from app.rpg import locations

    readiness = locations.assert_phase4_travel_resource_consumption_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_travel_resource_consumption_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase4_travel_resource_consumption"
    assert locations.apply_runtime_travel_with_resource_consumption
    assert locations.apply_travel_resource_consumption
    assert locations.validate_travel_resources_available
    assert locations.build_travel_resource_narration_contract
