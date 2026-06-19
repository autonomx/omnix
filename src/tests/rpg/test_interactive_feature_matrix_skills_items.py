from __future__ import annotations

from tests.rpg import interactive_feature_matrix as feature_matrix


def _scenario_by_id() -> dict[str, feature_matrix.IntentFeatureScenario]:
    return {scenario.scenario_id: scenario for scenario in feature_matrix.default_feature_matrix_scenarios()}


def test_feature_matrix_includes_skills_and_items_probes() -> None:
    scenarios = _scenario_by_id()

    assert feature_matrix.SKILLS_MATRIX_SCENARIO_ID in scenarios
    assert feature_matrix.ITEMS_MATRIX_SCENARIO_ID in scenarios
    assert feature_matrix.KNOWN_FEATURE_GAP_SCENARIO_IDS == frozenset()


def test_skills_and_items_probes_are_selectable_for_live_provider_runs() -> None:
    selected = feature_matrix._select_feature_scenarios(
        [feature_matrix.SKILLS_MATRIX_SCENARIO_ID, feature_matrix.ITEMS_MATRIX_SCENARIO_ID]
    )

    assert [scenario.scenario_id for scenario in selected] == [
        feature_matrix.SKILLS_MATRIX_SCENARIO_ID,
        feature_matrix.ITEMS_MATRIX_SCENARIO_ID,
    ]


def test_skills_probe_checks_training_practice_and_progress_text() -> None:
    scenario = _scenario_by_id()[feature_matrix.SKILLS_MATRIX_SCENARIO_ID]

    assert len(scenario.commands) == 3
    assert "skills" in scenario.commands[0].lower()
    assert "practice" in scenario.commands[1].lower()
    assert "skill progress" in scenario.commands[2].lower()
    assert all(expectation.provider_called is True for expectation in scenario.expectations)
    assert any("skill" in term for term in scenario.expectations[0].contains_any)
    assert any("sword" in term for term in scenario.expectations[1].contains_any)
    assert any("progress" in term for term in scenario.expectations[2].contains_any)


def test_items_probe_checks_inventory_use_merchant_and_crafting_text() -> None:
    scenario = _scenario_by_id()[feature_matrix.ITEMS_MATRIX_SCENARIO_ID]

    assert len(scenario.commands) == 4
    assert "inventory" in scenario.commands[0].lower()
    assert "ration" in scenario.commands[1].lower()
    assert "buy" in scenario.commands[2].lower()
    assert "crafting" in scenario.commands[3].lower()
    assert all(expectation.provider_called is True for expectation in scenario.expectations)
    assert any("inventory" in term for term in scenario.expectations[0].contains_any)
    assert any("ration" in term for term in scenario.expectations[1].contains_any)
    assert any("sell" in term for term in scenario.expectations[2].contains_any)
    assert any("torch" in term for term in scenario.expectations[3].contains_any)


def test_backed_quest_followup_probe_does_not_require_pronoun_turn_target() -> None:
    scenario = _scenario_by_id()["backed_quest_acceptance_probe"]

    assert scenario.expectations[0].final_target_contains_any == ("bran",)
    assert scenario.expectations[1].final_target_contains_any == ()
    assert scenario.expectations[2].final_target_contains_any == ()
    assert all(expectation.provider_called is True for expectation in scenario.expectations)
