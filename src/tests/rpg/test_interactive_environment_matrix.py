from __future__ import annotations

from tests.rpg import interactive_feature_matrix_environment as env_matrix


def test_environment_scenarios_are_available() -> None:
    ids = {scenario.scenario_id for scenario in env_matrix.environment_feature_matrix_scenarios()}

    assert ids == env_matrix.ENVIRONMENT_MATRIX_SCENARIO_IDS
