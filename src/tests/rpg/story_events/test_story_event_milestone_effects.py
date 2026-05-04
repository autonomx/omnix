from app.rpg.campaign_journal.journal import build_campaign_journal
from app.rpg.story_arcs.milestones import get_story_arc_milestone
from app.rpg.story_arcs.state import start_story_arc
from app.rpg.story_events.application import apply_story_event


def test_story_event_can_add_milestone_objective():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:add_milestone",
            "arc_id": "arc:x",
            "summary": "A witness becomes important.",
            "effects": [
                {
                    "type": "milestone_add",
                    "arc_id": "arc:x",
                    "milestone_id": "milestone:witness",
                    "title": "Find the witness",
                    "objective_text": "Find the witness near the tavern.",
                }
            ],
        },
        turn_index=2,
    )

    assert result["ok"] is True
    assert get_story_arc_milestone(simulation_state, "milestone:witness")["status"] == "active"


def test_story_event_can_complete_milestone_and_write_journal_objective():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", title="X", stage="start")
    apply_story_event(
        simulation_state,
        {
            "event_id": "event:add_milestone",
            "arc_id": "arc:x",
            "summary": "A witness becomes important.",
            "effects": [
                {
                    "type": "milestone_add",
                    "arc_id": "arc:x",
                    "milestone_id": "milestone:witness",
                    "title": "Find the witness",
                    "journal_on_complete": "The witness was found.",
                }
            ],
        },
        turn_index=2,
    )

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:complete_milestone",
            "arc_id": "arc:x",
            "summary": "The witness was found.",
            "effects": [
                {"type": "milestone_complete", "milestone_id": "milestone:witness"}
            ],
        },
        turn_index=3,
    )
    journal = build_campaign_journal(simulation_state)

    assert result["ok"] is True
    assert get_story_arc_milestone(simulation_state, "milestone:witness")["status"] == "completed"
    assert any(row["kind"] == "objective" and "witness" in row["summary"] for row in journal["entries"])