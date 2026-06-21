from __future__ import annotations

from typing import Any

from tests.rpg import interactive_feature_matrix_environment as env_matrix


def _snapshot() -> dict[str, Any]:
    return {
        "region_id": "starting_region",
        "weather": {"condition": "rain", "intensity": "light"},
        "calendar": {"season_id": "spring", "time_label": "Day 1, morning"},
        "display": {"weather": "Light Rain", "terrain": "Muddy"},
        "resources": {"water_availability": 70, "forage_availability": 62},
        "context": {"exposure": "outdoor"},
        "terrain_condition": "muddy",
        "temperature_c": 12,
    }


def _environment(minutes: int = 0) -> dict[str, Any]:
    return {
        "environment_version": 2,
        "region_id": "starting_region",
        "climate_profile_id": "temperate_hills",
        "absolute_minutes": minutes,
        "environment_seed": 17,
        "calendar": {"initial_day": 1},
        "active_events": [
            {
                "id": "rain-front",
                "type": "weather",
                "condition": "rain",
                "intensity": "light",
                "remaining_minutes": 80,
            }
        ],
        "recent_conditions": {"rain": 3, "mud": 2},
    }


def _turn(minutes: int = 0, *, explicit_snapshot: bool = True) -> dict[str, Any]:
    raw_result: dict[str, Any] = {
        "narration": "The weather and terrain remain visible.",
        "simulation_state": {
            "world": {"environment": _environment(minutes)},
            "scene": {"environment_context": {"exposure": "outdoor"}},
        },
    }
    if explicit_snapshot:
        raw_result["environment_snapshot"] = _snapshot()
        raw_result["environment_narration_contract"] = {
            "authority": "read_only_environment_snapshot",
            "forbidden": ["advance_time", "invent_temperature"],
            "allowed": ["describe_current_snapshot"],
            "instruction": "Describe only the current environment.",
        }
    return {
        "raw_result": raw_result,
        "raw_narration": "The weather and terrain remain visible.",
    }


def test_environment_scenarios_are_available() -> None:
    ids = {scenario.scenario_id for scenario in env_matrix.environment_feature_matrix_scenarios()}

    assert ids == env_matrix.ENVIRONMENT_MATRIX_SCENARIO_IDS


def test_environment_validator_requires_returned_or_derivable_snapshot() -> None:
    item = {
        "scenario": env_matrix.environment_feature_matrix_scenarios()[0],
        "result": {"turns": [{"raw_result": {"narration": "No environment payload."}}]},
    }

    validation = env_matrix.apply_environment_feature_validators(item, {"ok": True})

    assert validation["ok"] is False
    assert "environment snapshot" in validation["failures"][0]


def test_environment_validator_accepts_snapshot_contract_and_time() -> None:
    scenario = next(
        item
        for item in env_matrix.environment_feature_matrix_scenarios()
        if item.scenario_id == "weather_travel_elapsed_probe"
    )
    result = {"turns": [_turn(0), _turn(10)]}

    validation = env_matrix.apply_environment_feature_validators(
        {"scenario": scenario, "result": result},
        {"ok": True},
    )

    assert validation["ok"] is True


def test_environment_validator_derives_snapshot_from_cli_session_state() -> None:
    scenario = next(
        item
        for item in env_matrix.environment_feature_matrix_scenarios()
        if item.scenario_id == "environment_narration_guardrail_probe"
    )
    result = {"turns": [_turn(0, explicit_snapshot=False)]}

    validation = env_matrix.apply_environment_feature_validators(
        {"scenario": scenario, "result": result},
        {"ok": True},
    )

    assert validation["ok"] is True
