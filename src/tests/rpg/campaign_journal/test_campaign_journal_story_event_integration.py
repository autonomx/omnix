from app.rpg.campaign_journal.journal import build_campaign_journal
from app.rpg.story_arcs.state import start_story_arc
from app.rpg.story_events.application import apply_story_event


def test_apply_story_event_records_campaign_journal_entry():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:x", stage="start")

    result = apply_story_event(
        simulation_state,
        {
            "event_id": "event:x",
            "arc_id": "arc:x",
            "kind": "consequence",
            "summary": "The consequence happened.",
            "effects": [
                {"type": "arc_stage_set", "arc_id": "arc:x", "stage": "done"}
            ],
        },
        turn_index=4,
    )
    journal = build_campaign_journal(simulation_state)

    assert result["ok"] is True
    assert any(row["event_ids"] == ["event:x"] for row in journal["entries"])