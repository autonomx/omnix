from __future__ import annotations

from copy import deepcopy
from typing import Any

from tests.rpg import interactive_environment_feature_matrix_zip as envzip


def test_environment_zip_runner_selects_named_scenario() -> None:
    selected = envzip._select_environment_scenarios(["terrain_memory_probe"])

    assert [scenario.scenario_id for scenario in selected] == ["terrain_memory_probe"]


def test_environment_zip_runner_requires_live_provider(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        envzip,
        "run_environment_feature_matrix",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    exit_code = envzip.main([])

    assert exit_code == 2
    assert "--live-provider" in capsys.readouterr().out


def _seed_environment() -> dict[str, Any]:
    return {
        "absolute_minutes": 480,
        "active_events": [
            {
                "type": "weather",
                "condition": "rain",
                "intensity": "light",
                "remaining_minutes": 120,
            }
        ],
        "calendar": {"year": 1, "day_of_year": 1, "days_per_year": 360},
        "climate_profile_id": "temperate_hills",
        "environment_seed": 7,
        "event_history": [],
        "recent_conditions": {"rain": 0, "snow": 0, "dry": 0, "freezing": 0},
        "region_id": "starting_region",
    }


def test_environment_travel_hook_advances_saved_and_returned_time(monkeypatch) -> None:
    environment = _seed_environment()
    session = {"state": {"world": {"environment": deepcopy(environment)}}}
    saved: list[dict[str, Any]] = []
    monkeypatch.setattr(envzip, "_load_environment_session", lambda session_id: session)
    monkeypatch.setattr(envzip, "_save_environment_session", lambda value: saved.append(deepcopy(value)))
    turn_summary: dict[str, Any] = {
        "interactive_cli_intent_diagnostics": {
            "final_classification": {"action_type": "travel"},
        },
        "raw_result": {
            "session": {"state": {"world": {"environment": deepcopy(environment)}}},
            "narration_payload": {
                "session": {"state": {"world": {"environment": deepcopy(environment)}}},
            },
        },
    }

    envzip._advance_environment_after_travel_turn(
        session_id="session-1",
        turn_summary=turn_summary,
        turn_index=2,
        player_input="I travel north along the road.",
    )

    raw = turn_summary["raw_result"]
    returned_env = raw["session"]["state"]["world"]["environment"]
    nested_env = raw["narration_payload"]["session"]["state"]["world"]["environment"]
    saved_env = saved[0]["state"]["world"]["environment"]
    assert returned_env["absolute_minutes"] > 480
    assert nested_env["absolute_minutes"] == returned_env["absolute_minutes"]
    assert saved_env["absolute_minutes"] == returned_env["absolute_minutes"]
    assert raw["environment_elapsed_handoff"]["absolute_minutes_before"] == 480
