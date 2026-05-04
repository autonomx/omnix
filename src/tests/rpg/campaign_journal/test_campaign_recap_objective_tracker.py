from app.rpg.campaign_journal.journal import build_player_story_recap
from app.rpg.quest_log.runtime import pin_objective
from app.rpg.story_arcs.milestones import add_story_arc_milestone
from app.rpg.story_arcs.state import start_story_arc


def test_campaign_recap_includes_objective_tracker():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    add_story_arc_milestone(
        simulation_state,
        arc_id="arc:x",
        milestone_id="milestone:x",
        title="Find the witness",
        objective_text="Find the witness near the tavern.",
    )
    pin_objective(simulation_state, "milestone:x")

    recap = build_player_story_recap(simulation_state, turn_index=2)

    assert recap["objective_tracker"]["objectives"][0]["objective_id"] == "milestone:x"
    assert recap["narrator_context"]["objective_tracker"][0]["pinned"] is True