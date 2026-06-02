from copy import deepcopy


def _ready_old_mill_state():
    from app.rpg.locations import OLD_MILL, discover_location, discover_route, unblock_route

    state = {
        "player_state": {
            "inventory_state": {"items": [{"item_id": "ration", "qty": 1}, {"item_id": "water_skin", "qty": 2}]},
            "survival_state": {"hunger": 10, "thirst": 10},
        }
    }
    discover_location(state, location_id=OLD_MILL, reason="scouted_old_road", turn_index=1)
    discover_route(state, edge_id="route:old_road:old_mill", reason="scouted_old_road", turn_index=1)
    unblock_route(state, edge_id="route:old_road:old_mill", reason="bandit_threat_resolved", turn_index=2)
    return state


def test_ci_phase4_runtime_travel_command_resolves_canonical_destination_aliases():
    from app.rpg.locations import OLD_MILL, RUSTY_FLAGON
    from app.rpg.locations.command_routing import resolve_travel_command

    resolved = resolve_travel_command("go to the old mill", current_location_id=RUSTY_FLAGON)

    assert resolved["ok"] is True
    assert resolved["reason"] == "travel_command_resolved"
    assert resolved["start_location_id"] == RUSTY_FLAGON
    assert resolved["end_location_id"] == OLD_MILL
    assert resolved["source"] == "deterministic_phase4_runtime_travel_encounter_routing"


def test_ci_phase4_runtime_travel_command_rejects_non_travel_without_mutation():
    from app.rpg.locations.command_routing import apply_runtime_travel_command

    state = {"player_state": {"inventory_state": {"items": [{"item_id": "ration", "qty": 1}]}}}
    before = deepcopy(state)

    result = apply_runtime_travel_command(state, "ask bran about work", turn_index=3)

    assert result["ok"] is False
    assert result["reason"] == "not_travel_command"
    assert result["travel_result"] is None
    assert result["encounter_result"] is None
    assert result["encounter_runtime_result"] is None
    assert state == before


def test_ci_phase4_runtime_travel_command_uses_guarded_resource_travel_and_records_encounter():
    from app.rpg.locations import OLD_MILL
    from app.rpg.locations.command_routing import apply_runtime_travel_command

    state = _ready_old_mill_state()
    result = apply_runtime_travel_command(state, "travel to the old mill", turn_index=7, encounter_seed="phase4.11-safe")

    assert result["ok"] is True
    assert result["reason"] == "runtime_travel_command_applied"
    assert result["travel_result"]["reason"] == "runtime_travel_resources_consumed"
    assert state["travel_state"]["current_location_id"] == OLD_MILL
    assert state["player_state"]["inventory_state"]["items"] == []
    assert result["encounter_result"]["reason"] == "encounter_recorded"
    assert state["encounter_state"]["last_encounter"] == result["encounter_result"]["encounter_log_entry"]
    assert result["encounter_runtime_result"]["reason"] in {
        "encounter_runtime_noop",
        "encounter_world_event_recorded",
        "combat_candidate_created",
    }


def test_ci_phase4_runtime_travel_command_preserves_combat_candidate_without_starting_combat():
    from app.rpg.locations.command_routing import apply_runtime_travel_command

    state = _ready_old_mill_state()
    result = apply_runtime_travel_command(state, "head to old mill", turn_index=14, encounter_seed="phase4.11")

    assert result["ok"] is True
    assert result["encounter_result"]["encounter_log_entry"]["encounter"]["encounter_id"] == (
        "encounter:old_mill_route:bandit_patrol"
    )
    encounter_runtime = result["encounter_runtime_result"]
    assert encounter_runtime["reason"] == "combat_candidate_created"
    assert encounter_runtime["combat_candidate"]["requires_canonical_combat_start_api"] is True
    assert "combat_state" not in state


def test_ci_phase4_runtime_travel_command_rejects_missing_resources_before_travel_or_encounter():
    from app.rpg.locations import OLD_ROAD, RUSTY_FLAGON
    from app.rpg.locations.command_routing import apply_runtime_travel_command

    state = {"player_state": {"inventory_state": {"items": []}}, "travel_state": {"current_location_id": RUSTY_FLAGON}}
    before_player = deepcopy(state["player_state"])

    result = apply_runtime_travel_command(state, "go to old road", turn_index=4, current_location_id=RUSTY_FLAGON)

    assert result["ok"] is False
    assert result["reason"] == "insufficient_travel_resources"
    assert result["travel_result"]["travel_result"] is None
    assert result["encounter_result"] is None
    assert result["encounter_runtime_result"] is None
    assert state["player_state"] == before_player
    assert state["travel_state"]["current_location_id"] == RUSTY_FLAGON
    assert state["travel_state"]["current_location_id"] != OLD_ROAD


def test_ci_phase4_runtime_travel_command_contract_limits_claims():
    from app.rpg.locations.command_routing import (
        apply_runtime_travel_command,
        build_runtime_travel_command_narration_contract,
    )

    result = apply_runtime_travel_command(_ready_old_mill_state(), "walk to the old mill", turn_index=7)
    contract = build_runtime_travel_command_narration_contract(result)

    assert contract["source"] == "deterministic_phase4_runtime_travel_encounter_routing"
    assert "Runtime travel command result: runtime_travel_command_applied" in contract[
        "allowed_runtime_travel_command_claims"
    ]
    forbidden = "\n".join(contract["forbidden_runtime_travel_command_claims"])
    assert "Do not route travel commands through harness shortcuts" in forbidden
    assert "Do not apply travel unless guarded travel with resource consumption returns ok=true" in forbidden
    assert "Do not claim combat started unless a canonical combat-start API is called" in forbidden
    assert "Do not invent inventory" in forbidden


def test_ci_phase4_runtime_travel_encounter_routing_readiness():
    from app.rpg.locations.command_routing import assert_phase4_runtime_travel_encounter_routing_ready

    readiness = assert_phase4_runtime_travel_encounter_routing_ready()

    assert readiness["ok"] is True
    assert readiness["reason"] == "phase4_runtime_travel_encounter_routing_ready"
    assert readiness["blockers"] == []
    assert readiness["source"] == "deterministic_phase4_runtime_travel_encounter_routing"
