from tests.rpg.manual.extractors.base import (
    _extract_combat_narration_contract,
    _extract_current_location_id,
    _extract_location_state,
    _extract_service_debug,
    _extract_travel_result,
)


def test_combat_narration_contract_is_read_from_nested_turn_contract():
    contract = {"raw_combat_result": {"reason": "enemy_defeated"}}
    result = {"result": {"turn_contract": {"combat_narration_contract": contract}}}

    assert _extract_combat_narration_contract(result) == contract


def test_location_and_travel_extractors_prefer_fresh_result_values():
    result = {
        "result": {
            "location_state": {"current_location_id": "fresh-location"},
            "travel_result": {"to_location_id": "fresh-location"},
        },
        "session": {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {
                        "location_state": {"current_location_id": "stale-location"},
                    }
                }
            }
        },
    }

    assert _extract_location_state(result)["current_location_id"] == "fresh-location"
    assert _extract_travel_result(result)["to_location_id"] == "fresh-location"
    assert _extract_current_location_id(result) == "fresh-location"


def test_service_debug_reads_resolved_service_and_presentation_fields():
    result = {
        "result": {
            "turn_contract": {
                "presentation": {"available_actions": ["buy", "leave"]},
                "resolved_action": {
                    "service_result": {
                        "purchase": {
                            "resource_changes": {"gold": -2},
                            "effects": {"items_added": [{"id": "ration"}]},
                        }
                    },
                    "transaction_record": {"id": "txn-1"},
                },
            }
        }
    }

    debug = _extract_service_debug(result)

    assert debug["available_actions"] == ["buy", "leave"]
    assert debug["resource_changes"] == {"gold": -2}
    assert debug["transaction_record"] == {"id": "txn-1"}
    assert debug["inventory_changes"]["items_added"] == [{"id": "ration"}]
