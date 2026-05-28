from __future__ import annotations

import json

from app.rpg.survival import (
    SURVIVAL_EVENT_LIMIT,
    apply_survival_effect,
    ensure_survival_state,
    serialize_survival_state,
    survival_pressure,
    tick_survival_state,
)


def test_bundle_ba_ensure_survival_state_uses_bounded_save_load_safe_shape() -> None:
    simulation_state = {
        "survival": {
            "enabled": "true",
            "hunger": 150,
            "thirst": -20,
            "fatigue": "12",
            "last_food_turn": "7",
            "last_water_turn": "bad",
            "last_rest_turn": None,
            "events": [{"kind": "old"}],
            "llm_invented_unbounded_key": "drop_me",
        }
    }

    state = ensure_survival_state(simulation_state)

    assert state == {
        "enabled": True,
        "hunger": 100,
        "thirst": 0,
        "fatigue": 12,
        "last_food_turn": 7,
        "last_water_turn": None,
        "last_rest_turn": None,
        "events": [{"kind": "old", "source": "runtime_survival_state"}],
    }
    assert simulation_state["survival"] == state
    json.dumps(state)


def test_bundle_ba_tick_survival_state_is_deterministic_and_bounded() -> None:
    simulation_state = {"survival": {"hunger": 98, "thirst": 97, "fatigue": 0}}

    state = tick_survival_state(simulation_state, tick=10, turns=3)

    assert state["hunger"] == 100
    assert state["thirst"] == 100
    assert state["fatigue"] == 3
    assert state["events"][-1]["kind"] == "survival_tick"
    assert state["events"][-1]["source"] == "runtime_survival_state"
    json.dumps(simulation_state)


def test_bundle_ba_apply_survival_effect_records_authoritative_event() -> None:
    simulation_state = {"survival": {"hunger": 60, "thirst": 70, "fatigue": 80}}

    result = apply_survival_effect(simulation_state, kind="drink water", tick=12)

    assert result["ok"] is True
    assert result["action_category"] == "survival"
    assert result["action"] == "drink_water"
    assert result["effects"] == {"thirst_delta": -30}
    assert result["survival_event"]["source"] == "runtime_action_resolver"
    assert simulation_state["survival"]["thirst"] == 40
    assert simulation_state["survival"]["last_water_turn"] == 12


def test_bundle_ba_unknown_survival_effect_does_not_mutate_needs() -> None:
    simulation_state = {"survival": {"hunger": 10, "thirst": 20, "fatigue": 30}}

    result = apply_survival_effect(simulation_state, kind="invent feast", tick=99)

    assert result["ok"] is False
    assert result["reason"] == "unknown_survival_effect"
    assert simulation_state["survival"]["hunger"] == 10
    assert simulation_state["survival"]["thirst"] == 20
    assert simulation_state["survival"]["fatigue"] == 30


def test_bundle_ba_serialization_prunes_events_and_pressure_is_stable() -> None:
    serialized = serialize_survival_state(
        {
            "hunger": 24,
            "thirst": 50,
            "fatigue": 75,
            "events": [{"kind": f"e{i}"} for i in range(SURVIVAL_EVENT_LIMIT + 5)],
        }
    )

    assert len(serialized["events"]) == SURVIVAL_EVENT_LIMIT
    assert serialized["events"][0]["kind"] == "e5"
    assert survival_pressure(serialized) == {
        "hunger": "low",
        "thirst": "high",
        "fatigue": "critical",
    }
    json.dumps(serialized)
