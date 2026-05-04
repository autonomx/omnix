from tests.rpg.manual.scenarios.quest_log_m49_m51 import (
    STORY_QUEST_LOG_M49_M51_SCENARIOS,
)


def test_m49_m51_manual_scenarios_use_supported_turn_shape():
    for name, scenario in STORY_QUEST_LOG_M49_M51_SCENARIOS.items():
        turns = scenario.get("turns") or []
        assert turns, f"{name} has no turns"
        assert all(isinstance(turn, str) and turn.strip() for turn in turns), (
            f"{name} uses unsupported turn shape; manual_llm_transcript.py "
            "expects turns to be player input strings"
        )


def test_m49_m51_completed_objective_scenarios_use_supported_completion_setup_key():
    completed_scenarios = [
        "quest_log_completed_objective_moves_to_completed_section",
        "quest_log_pin_missing_or_completed_rejected",
    ]

    for name in completed_scenarios:
        scenario = STORY_QUEST_LOG_M49_M51_SCENARIOS[name]
        assert "setup_complete_story_arc_milestones" in scenario
        assert "setup_story_arc_milestones_completed" not in scenario


def test_m49_m51_unpin_expectation_matches_priority_sort_after_unpin():
    scenario = STORY_QUEST_LOG_M49_M51_SCENARIOS["quest_log_unpin_removes_pin"]
    tracker_checks = [
        check
        for check in scenario.get("checks") or []
        if isinstance(check, dict)
        and check.get("type") == "objective_tracker_payload"
    ]

    assert tracker_checks
    assert tracker_checks[-1]["expected_first_objective_id"] == "milestone:find_witness"