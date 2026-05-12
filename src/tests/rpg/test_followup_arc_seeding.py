from app.rpg.story.followup_arc_seeding import seed_followup_arcs


def test_followup_arc_seeding_adds_new_arc_once():
    result = seed_followup_arcs(
        existing_arcs={
            "arc:done": {
                "arc_id": "arc:done",
                "status": "completed",
            }
        },
        followup_hooks=[
            {
                "id": "hook:next",
                "arc_id": "arc:next",
                "summary": "Next lead.",
                "priority": 2,
            }
        ],
        turn_index=12,
    )

    assert result["seeded_count"] == 1
    assert result["story_arcs"]["arc:next"]["status"] == "active"

    second = seed_followup_arcs(
        existing_arcs=result["story_arcs"],
        followup_hooks=[
            {
                "id": "hook:next",
                "arc_id": "arc:next",
                "summary": "Next lead.",
                "priority": 2,
            }
        ],
        turn_index=13,
    )

    assert second["seeded_count"] == 0