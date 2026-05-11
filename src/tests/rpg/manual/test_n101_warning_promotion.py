from tests.rpg.manual.scenario_execution import (
    _is_n101_gate_warning,
    _promote_turn_scenario_warnings,
)


def test_n101_warning_promotion_adds_to_regression_warnings():
    scenario_warnings = []
    regression_warnings = []
    turn_summaries = [
        {
            "scenario_warnings": [
                "npc_bran_refuses_fake_debt:turn_1:n101_fake_debt_used_deterministic_fallback",
                "npc_bran_refuses_fake_debt:turn_1:fake_debt_unexpected_selected_candidate:deterministic_fallback",
            ]
        }
    ]

    _promote_turn_scenario_warnings(
        turn_summaries=turn_summaries,
        scenario_warnings=scenario_warnings,
        regression_warnings=regression_warnings,
    )

    assert "npc_bran_refuses_fake_debt:turn_1:n101_fake_debt_used_deterministic_fallback" in scenario_warnings
    assert "npc_bran_refuses_fake_debt:turn_1:n101_fake_debt_used_deterministic_fallback" in regression_warnings
    assert "npc_bran_refuses_fake_debt:turn_1:fake_debt_unexpected_selected_candidate:deterministic_fallback" in regression_warnings


def test_n101_warning_classifier_matches_gate_markers():
    assert _is_n101_gate_warning(
        "npc_bran_refuses_fake_debt:turn_1:n101_fake_debt_used_deterministic_fallback"
    )
    assert _is_n101_gate_warning(
        "npc_bran_refuses_fake_debt:turn_1:grounding_primary_violation:unsupported_reward_claim"
    )
    assert _is_n101_gate_warning(
        "npc_bran_refuses_fake_debt:turn_1:grounding_fallback_used:deterministic_fallback:deterministic_fallback"
    )
    assert not _is_n101_gate_warning("ordinary_non_gate_warning")


def test_fake_debt_warning_promotes_to_regression_warning():
    scenario_warnings = []
    regression_warnings = []
    turn_summaries = [
        {
            "scenario_warnings": [
                "npc_bran_refuses_fake_debt:turn_1:n101_fake_debt_used_deterministic_fallback",
                "npc_bran_refuses_fake_debt:turn_1:grounding_violation:unsupported_reward_claim",
            ]
        }
    ]

    _promote_turn_scenario_warnings(
        turn_summaries=turn_summaries,
        scenario_warnings=scenario_warnings,
        regression_warnings=regression_warnings,
    )

    assert regression_warnings == [
        "npc_bran_refuses_fake_debt:turn_1:n101_fake_debt_used_deterministic_fallback",
        "npc_bran_refuses_fake_debt:turn_1:grounding_violation:unsupported_reward_claim",
    ]


def test_combat_contradiction_expected_fallback_does_not_promote():
    assert not _is_n101_gate_warning(
        "narration_validator_catches_hit_miss_contradiction:turn_1:grounding_fallback_used:deterministic_fallback:deterministic_fallback"
    )
    assert not _is_n101_gate_warning(
        "narration_validator_catches_hit_miss_contradiction:turn_1:grounding_violation:unsupported_combat_claim"
    )