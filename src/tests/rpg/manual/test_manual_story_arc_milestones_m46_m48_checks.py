from app.rpg.story_arcs.milestones import complete_story_arc_milestone
from tests.rpg.manual.story_arc_milestones_m46_m48_checks import (
    run_story_arc_milestones_m46_m48_checks,
)


def test_manual_story_arc_milestone_complete_check():
    # Placeholder test
    # Assume some setup
    simulation_state = {}
    result = complete_story_arc_milestone(simulation_state, "milestone:x")
    assert result["ok"] is False  # since no milestone


def test_manual_story_arc_milestone_runner_returns_failed_check_instead_of_crashing():
    # Pass invalid check to cause an exception in the check
    results = run_story_arc_milestones_m46_m48_checks(
        checks=[
            "invalid_check",  # Not a dict
        ],
        result={},
        session={},
    )

    assert len(results) == 1
    assert results[0]["ok"] is False
    assert "error" in results[0]