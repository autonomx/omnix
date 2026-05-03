from __future__ import annotations

import pytest

from tests.rpg.manual.runner import build_service_scenarios, run_single_scenario
from tests.rpg.manual.scenarios.expected_social_l10_l12_names import (
    EXPECTED_SOCIAL_L10_L12_SCENARIO_NAMES,
)
from tests.rpg.manual.social_checks import run_social_checks


def _get_social_scenarios():
    scenarios = build_service_scenarios()
    return {k: v for k, v in scenarios.items() if k in EXPECTED_SOCIAL_L10_L12_SCENARIO_NAMES}


@pytest.mark.parametrize("scenario_key", sorted(EXPECTED_SOCIAL_L10_L12_SCENARIO_NAMES))
def test_social_scenario_executes(scenario_key: str):
    """Ensure each social L10-L12 scenario can be executed without errors."""
    scenarios = _get_social_scenarios()
    assert scenario_key in scenarios, f"Scenario {scenario_key} not found in registry"

    result = run_single_scenario(scenario_key)
    assert result is not None, f"Scenario {scenario_key} returned no result"


def test_social_scenarios_registry_complete():
    """Ensure all expected social L10-L12 scenarios are registered."""
    scenarios = _get_social_scenarios()
    missing = EXPECTED_SOCIAL_L10_L12_SCENARIO_NAMES - set(scenarios.keys())
    assert not missing, f"Missing social scenarios: {sorted(missing)}"


def test_social_scenario_persuasion_success():
    result = run_single_scenario("social_persuasion_success_high_trust")
    assert result is not None


def test_social_scenario_intimidation_creates_fear():
    result = run_single_scenario("social_intimidation_creates_fear_but_lowers_trust")
    assert result is not None


def test_social_scenario_leverage_valid():
    result = run_single_scenario("social_valid_leverage_from_memory_improves_negotiation")
    assert result is not None


def test_social_scenario_save_load_preserves_state():
    result = run_single_scenario("social_save_load_preserves_reputation_and_fear")
    assert result is not None


def test_manual_social_check_reports_available_result_keys_when_missing():
    session = {
        "simulation_state": {
            "social_state": {
                "manual_results": {
                    "discount_room": {
                        "ok": True,
                        "kind": "persuasion",
                        "stance": "cooperative",
                    }
                }
            }
        }
    }

    result = run_social_checks(
        checks=[
            {
                "type": "social_persuasion_result",
                "result_key": "wrong_key",
                "expected_ok": True,
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is False
    assert result["error"] == "social_result_missing"
    assert result["available_result_keys"] == ["discount_room"]


def test_manual_social_check_prefers_session_social_state_over_partial_result_state():
    session = {
        "simulation_state": {
            "social_state": {
                "manual_results": {
                    "discount_room": {
                        "ok": True,
                        "kind": "persuasion",
                        "stance": "cooperative",
                    }
                }
            }
        }
    }
    partial_result = {
        "simulation_state": {
            "some_other_state": {},
        }
    }

    result = run_social_checks(
        checks=[
            {
                "type": "social_persuasion_result",
                "result_key": "discount_room",
                "expected_ok": True,
                "expected_stance": "cooperative",
            }
        ],
        result=partial_result,
        session=session,
    )[0]

    assert result["ok"] is True
