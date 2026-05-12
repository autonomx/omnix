from app.rpg.story.escalation_branching import seed_escalation_arcs


def test_escalation_branching_seeds_arc_once():
    result = seed_escalation_arcs(
        existing_arcs={},
        escalation_hooks=[
            {
                "id": "hook:handler",
                "arc_id": "arc:handler",
                "summary": "Handler arrives.",
                "priority": 4,
            }
        ],
        turn_index=12,
    )

    assert result["seeded_count"] == 1
    assert result["story_arcs"]["arc:handler"]["status"] == "active"
    assert result["story_arcs"]["arc:handler"]["escalation_arc"] is True

    second = seed_escalation_arcs(
        existing_arcs=result["story_arcs"],
        escalation_hooks=[
            {
                "id": "hook:handler",
                "arc_id": "arc:handler",
                "summary": "Handler arrives.",
                "priority": 4,
            }
        ],
        turn_index=13,
    )

    assert second["seeded_count"] == 0