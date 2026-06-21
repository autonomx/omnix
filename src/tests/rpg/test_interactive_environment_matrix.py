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


def _turn(minutes: int = 0) -> dict[str, Any]:
    snapshot = _snapshot()
    return {
        "raw_result": {
            "narration": "The weather and terrain remain visible.",
            "environment_snapshot": snapshot,
            "environment_narration_contract": {
                "authority": "read_only_environment_snapshot",
                "forbidden": ["advance_time", "invent_temperature"],
                "allowed": ["describe_current_snapshot"],
                "instruction": "Describe only the current environment.",
            },
            "simulation_state": {
                "world": {
                    "environment": {
                        "absolute_minutes": minutes,
                        "active_events": [],
                        "recent_conditions": {"rain": 3, "mud": 2},
                    }
                }
            },
        },
        "raw_narration": "The weather and terrain remain visible.",
    }


def test_environment_scenarios_are_available() -> None:
    ids = {scenario.scenario_id for scenario in env_matrix.environment_feature_matrix_scenarios()}

    assert ids == env_matrix.ENVIRONMENT_MATRIX_SCENARIO_IDS


def test_environment_validator_requires_returned_snapshot() -> None:
    item = {
        "scenario": env_matrix.environment_feature_matrix_scenarios()[0],
        "result": {"turns": [{"raw_result": {"narration": "No environment payload."}}]},
    }

    validation = env_matrix.apply_environment_feature_validators(item, {"ok": True})

    assert validation["ok"] is False
    assert "environment_snapshot" in validation["failures"][0]


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
