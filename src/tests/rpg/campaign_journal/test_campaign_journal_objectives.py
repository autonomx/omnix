from app.rpg.campaign_journal.journal import build_player_story_recap
from app.rpg.story_arcs.milestones import add_story_arc_milestone
from app.rpg.story_arcs.state import start_story_arc


def test_campaign_recap_includes_active_objectives():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    add_story_arc_milestone(
        simulation_state,
        arc_id="arc:x",
        milestone_id="milestone:x",
        title="Find the witness",
        objective_text="Find the witness near the tavern.",
        turn_index=1,
    )

    recap = build_player_story_recap(simulation_state, turn_index=2)

    assert recap["objectives"]["active_objectives"][0]["milestone_id"] == "milestone:x"
    assert recap["narrator_context"]["active_objectives"][0]["objective_text"] == "Find the witness near the tavern."