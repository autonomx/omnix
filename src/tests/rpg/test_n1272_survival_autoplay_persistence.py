from __future__ import annotations

from app.rpg.session.survival_autoplay_persistence import (
    calibrate_turn_survival_state,
    extract_turn_survival_state,
    merge_survival_accumulator_into_session,
    mirror_survival_state_into_session,
    persist_result_survival_state,
    reset_survival_autoplay_accumulator,
)


def _result():
    return {
        "turn_contract": {
            "climate_survival": {
                "format_version": "n1231_climate_survival_state_v1",
                "runtime_enforced": True,
                "source": "deterministic_authoritative_turn_tick",
                "tick": 72,
                "survival": {
                    "hunger": 72,
                    "thirst": 74,
                    "fatigue": 71,
                    "action_count": 72,
                    "warnings": ["hunger_high", "thirst_high", "fatigue_high"],
                },
            }
        },
        "session": {
            "simulation_state": {
                "player_state": {
                    "resources": {"hunger": 2, "thirst": 3, "fatigue": 2},
                    "inventory_state": {"items": []},
                },
                "needs": {"hunger": 2, "thirst": 3, "fatigue": 2},
            },
            "runtime_state": {},
            "state": {},
            "setup_payload": {"metadata": {}},
        },
    }


def _prior_session(*, hunger=68, thirst=69, fatigue=68, action_count=68):
    climate = {
        "format_version": "n1231_climate_survival_state_v1",
        "runtime_enforced": True,
        "source": "deterministic_authoritative_turn_tick",
        "tick": action_count,
        "survival": {
            "hunger": hunger,
            "thirst": thirst,
            "fatigue": fatigue,
            "action_count": action_count,
            "warnings": [],
        },
    }
    return {
        "simulation_state": {
            "climate_survival": climate,
            "needs": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue},
            "player_state": {
                "resources": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue, "action_count": action_count},
                "inventory_state": {"items": []},
            },
        },
        "runtime_state": {"climate_survival": climate},
        "state": {},
        "setup_payload": {"metadata": {}},
    }


def _regressed_result():
    result = _result()
    result["turn_contract"]["climate_survival"]["tick"] = 1
    result["turn_contract"]["climate_survival"]["survival"] = {
        "hunger": 2,
        "thirst": 3,
        "fatigue": 2,
        "action_count": 1,
        "warnings": [],
    }
    return result


def test_n1272_extracts_authoritative_turn_survival_state() -> None:
    climate = extract_turn_survival_state(_result())

    assert climate["tick"] == 72
    assert climate["survival"]["hunger"] == 72
    assert climate["survival"]["thirst"] == 74
    assert climate["survival"]["fatigue"] == 71
    assert climate["runtime_enforced"] is True


def test_n1272_mirrors_survival_state_into_all_session_roots() -> None:
    result = _result()
    climate = extract_turn_survival_state(result)
    session = mirror_survival_state_into_session(result["session"], climate)

    assert session["simulation_state"]["needs"] == {"hunger": 72, "thirst": 74, "fatigue": 71}
    assert session["simulation_state"]["player_state"]["resources"]["thirst"] == 74
    assert session["runtime_state"]["climate_survival"]["survival"]["fatigue"] == 71
    assert session["state"]["needs"] == {"hunger": 72, "thirst": 74, "fatigue": 71}
    assert session["setup_payload"]["metadata"]["needs"] == {"hunger": 72, "thirst": 74, "fatigue": 71}


def test_n1272_persist_result_survival_state_updates_return_payload_without_save() -> None:
    result = persist_result_survival_state(_result(), save=False)

    assert result["survival_autoplay_persistence"]["applied"] is True
    assert result["session"]["simulation_state"]["needs"]["hunger"] == 72
    assert result["simulation_state"]["needs"]["thirst"] == 74


def test_n1273_calibrates_regressed_turn_from_prior_session() -> None:
    climate, meta = calibrate_turn_survival_state(_regressed_result(), prior_session=_prior_session())

    assert meta["calibrated"] is True
    assert meta["reason"] == "current_action_count_regressed"
    assert climate["source"] == "n1273_long_run_survival_pressure_calibration"
    assert climate["survival"]["hunger"] == 69
    assert climate["survival"]["thirst"] == 71
    assert climate["survival"]["fatigue"] == 69
    assert climate["survival"]["action_count"] == 69
    assert "thirst_high" in climate["survival"]["warnings"]


def test_n1273_patches_return_payload_and_resource_deltas_for_calibrated_turn() -> None:
    result = persist_result_survival_state(_regressed_result(), save=False, prior_session=_prior_session())

    assert result["survival_autoplay_persistence"]["calibration"]["calibrated"] is True
    assert result["turn_contract"]["climate_survival"]["survival"]["thirst"] == 71
    changes = result["turn_contract"]["resource_changes"]
    assert changes["source"] == "merged_turn_resource_changes"
    assert changes["climate_survival"]["source"] == "n1231_climate_survival_tick"
    assert changes["hunger_delta"] == 1
    assert changes["thirst_delta"] == 2
    assert changes["fatigue_delta"] == 1
    assert result["session"]["simulation_state"]["needs"] == {"hunger": 69, "thirst": 71, "fatigue": 69}


def test_n1273_1_accumulator_carries_pressure_when_session_snapshot_stays_low() -> None:
    key = "test-n1273-accumulator"
    reset_survival_autoplay_accumulator(key)
    low_result = _regressed_result()
    prior_session = {}

    for _ in range(10):
        patched = persist_result_survival_state(
            low_result,
            save=False,
            prior_session=prior_session,
            accumulator_key=key,
        )
        prior_session = merge_survival_accumulator_into_session({}, key)

    needs = patched["session"]["simulation_state"]["needs"]
    assert needs["hunger"] >= 12
    assert needs["thirst"] >= 23
    assert needs["fatigue"] >= 12
    assert patched["survival_autoplay_persistence"]["accumulator_source"] == "n1273_1_in_process_survival_accumulator"
    assert patched["turn_contract"]["resource_changes"]["thirst_delta"] == 2


def test_n1273_1_accumulator_state_can_seed_selector_session() -> None:
    key = "test-n1273-selector-seed"
    reset_survival_autoplay_accumulator(key)
    result = persist_result_survival_state(
        _regressed_result(),
        save=False,
        prior_session=_prior_session(hunger=68, thirst=69, fatigue=68, action_count=68),
        accumulator_key=key,
    )
    seeded = merge_survival_accumulator_into_session({}, key)

    assert result["session"]["simulation_state"]["needs"]["thirst"] == 71
    assert seeded["simulation_state"]["needs"]["thirst"] == 71
    assert seeded["runtime_state"]["survival_autoplay_accumulator"]["source"] == "n1273_1_in_process_survival_accumulator"
