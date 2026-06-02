def test_ci_phase4_command_routing_helpers_export_from_locations_facade():
    from app.rpg.locations import (
        OLD_MILL,
        RUSTY_FLAGON,
        apply_runtime_travel_command,
        assert_phase4_runtime_travel_encounter_routing_ready,
        build_runtime_travel_command_narration_contract,
        resolve_travel_command,
    )

    resolved = resolve_travel_command("go to the old mill", current_location_id=RUSTY_FLAGON)

    assert resolved["ok"] is True
    assert resolved["reason"] == "travel_command_resolved"
    assert resolved["start_location_id"] == RUSTY_FLAGON
    assert resolved["end_location_id"] == OLD_MILL

    result = apply_runtime_travel_command({}, "ask bran about work", turn_index=1)
    assert result["ok"] is False
    assert result["reason"] == "not_travel_command"
    assert result["travel_result"] is None
    assert result["encounter_result"] is None
    assert result["encounter_runtime_result"] is None

    contract = build_runtime_travel_command_narration_contract(result)
    assert contract["source"] == "deterministic_phase4_runtime_travel_encounter_routing"
    forbidden = "\n".join(contract["forbidden_runtime_travel_command_claims"])
    assert "Do not route travel commands through harness shortcuts" in forbidden
    assert "Do not apply travel unless guarded travel with resource consumption returns ok=true" in forbidden

    readiness = assert_phase4_runtime_travel_encounter_routing_ready()
    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_runtime_travel_encounter_routing_ready"
    assert readiness["blockers"] == []


def test_ci_phase4_command_routing_facade_keeps_non_travel_provider_free_and_non_mutating():
    from copy import deepcopy

    from app.rpg.locations import apply_runtime_travel_command

    state = {"player_state": {"inventory_state": {"items": [{"item_id": "ration", "qty": 1}]}}}
    before = deepcopy(state)

    result = apply_runtime_travel_command(state, "tell bran hello", turn_index=2)

    assert result["ok"] is False
    assert result["reason"] == "not_travel_command"
    assert result["command_result"]["source"] == "deterministic_phase4_runtime_travel_encounter_routing"
    assert result["travel_result"] is None
    assert result["encounter_result"] is None
    assert result["encounter_runtime_result"] is None
    assert state == before
