from __future__ import annotations

from app.rpg.session.runtime_promotions import (
    apply_climate_survival_turn_effects,
    build_climate_survival_runtime_payload,
)
from app.rpg.session.turn_contract import build_turn_contract


def test_n1231_apply_climate_survival_turn_effects_persists_player_resources() -> None:
    simulation_state = {
        "tick": 0,
        "player_state": {
            "resources": {
                "hunger": 4,
                "thirst": 5,
                "fatigue": 6,
            }
        },
    }
    runtime_state = {"tick": 0}

    result = apply_climate_survival_turn_effects(simulation_state, runtime_state)

    assert result["ok"] is True
    assert simulation_state["climate_survival"]["runtime_enforced"] is True
    assert simulation_state["climate_survival"]["tick"] == 1
    assert simulation_state["player_state"]["resources"]["hunger"] == 5
    assert simulation_state["player_state"]["resources"]["thirst"] == 7
    assert simulation_state["player_state"]["resources"]["fatigue"] == 7
    assert result["resource_changes"]["hunger_delta"] == 1
    assert result["resource_changes"]["thirst_delta"] == 2
    assert result["resource_changes"]["fatigue_delta"] == 1
    assert result["resource_changes"]["source"] == "n1231_climate_survival_tick"


def test_n1231_threshold_warnings_emit_effect_result() -> None:
    simulation_state = {
        "climate_survival": {
            "tick": 7,
            "survival": {
                "hunger": 69,
                "thirst": 68,
                "fatigue": 69,
                "action_count": 7,
            },
        },
        "player_state": {"resources": {}},
    }

    result = apply_climate_survival_turn_effects(simulation_state, {"tick": 7})

    warnings = result["effect_result"]["warnings"]
    assert "hunger_high" in warnings
    assert "thirst_high" in warnings
    assert "fatigue_high" in warnings
    assert result["effect_result"]["applied"] is True
    assert {effect["effect_id"] for effect in result["effect_result"]["effects"]} >= {
        "survival_hunger_high",
        "survival_thirst_high",
        "survival_fatigue_high",
    }


def test_n1231_turn_contract_includes_resource_changes_and_effect_result() -> None:
    simulation_state_before = {
        "tick": 0,
        "player_state": {"resources": {"hunger": 0, "thirst": 0, "fatigue": 0}},
    }
    simulation_state_after = {
        "tick": 0,
        "player_state": {"resources": {"hunger": 0, "thirst": 0, "fatigue": 0}},
    }

    contract = build_turn_contract(
        player_input="I wait and watch the room.",
        action={"action_type": "wait"},
        resolved_action={"summary": "You wait."},
        simulation_state_before=simulation_state_before,
        simulation_state_after=simulation_state_after,
        runtime_state={"tick": 0},
    )

    assert contract["climate_survival"]["runtime_enforced"] is True
    assert contract["resource_changes"]["source"] == "n1231_climate_survival_tick"
    assert contract["resource_changes"]["hunger_delta"] == 1
    assert contract["resource_changes"]["thirst_delta"] == 2
    assert contract["resource_changes"]["fatigue_delta"] == 1
    assert contract["effect_result"]["source"] == "n1231_climate_survival_tick"
    assert contract["resolved_action"]["resource_changes"]["source"] == "n1231_climate_survival_tick"
    assert simulation_state_after["player_state"]["resources"]["thirst"] == 2


def test_n1231_n1222_payload_reflects_persisted_survival_state() -> None:
    simulation_state = {
        "tick": 0,
        "player_state": {"resources": {"hunger": 10, "thirst": 10, "fatigue": 10}},
    }

    apply_climate_survival_turn_effects(simulation_state, {"tick": 0})
    payload = build_climate_survival_runtime_payload(simulation_state, {"tick": 1})

    assert payload["runtime_enforced"] is True
    assert payload["source"] == "deterministic_authoritative_turn_tick"
    assert payload["tick"] == 1
    assert payload["survival"]["hunger"] == 11
    assert payload["survival"]["thirst"] == 12
    assert payload["survival"]["fatigue"] == 11
    assert "resource_changes" in payload["turn_contract_keys"]
    assert "effect_result" in payload["turn_contract_keys"]
