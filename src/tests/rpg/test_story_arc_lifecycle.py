from app.rpg.story.story_arc_lifecycle import (
    ArcFailureRule,
    ArcResolutionRule,
    apply_story_arc_lifecycle,
)


def test_story_arc_completes_when_requirements_met():
    arcs = {
        "arc:marked_coin_investigation": {
            "arc_id": "arc:marked_coin_investigation",
            "title": "Marked Coin Investigation",
            "status": "active",
            "started_turn": 1,
            "last_progress_turn": 1,
        }
    }

    result = apply_story_arc_lifecycle(
        arc_states=arcs,
        state={
            "completed_objectives": ["objective:identify_marked_coin"],
            "inventory": [{"id": "item:marked_coin", "quantity": 1}],
            "mechanics_covered": {
                "combat_resolved": True,
                "quest_progress": True,
            },
        },
        turn_index=10,
        resolution_rules=[
            ArcResolutionRule(
                id="rule:complete",
                arc_id="arc:marked_coin_investigation",
                outcome="completed",
                requires_objectives=("objective:identify_marked_coin",),
                requires_items=("item:marked_coin",),
                requires_mechanics=("combat_resolved", "quest_progress"),
                reward_xp=10,
                set_flags=("arc:marked_coin_investigation.completed",),
            )
        ],
        failure_rules=[],
    )

    assert result["ok"] is True
    assert result["resolved_count"] == 1

    arc = result["story_arc_state_delta"]["story_arcs"]["arc:marked_coin_investigation"]
    assert arc["status"] == "completed"
    assert result["story_arc_state_delta"]["xp_delta"] == 10
    assert result["story_arc_state_delta"]["flags"]["arc:marked_coin_investigation.completed"] is True


def test_story_arc_fails_when_stalled():
    arcs = {
        "arc:marked_coin_investigation": {
            "arc_id": "arc:marked_coin_investigation",
            "title": "Marked Coin Investigation",
            "status": "active",
            "started_turn": 1,
            "last_progress_turn": 1,
        }
    }

    result = apply_story_arc_lifecycle(
        arc_states=arcs,
        state={},
        turn_index=100,
        resolution_rules=[],
        failure_rules=[
            ArcFailureRule(
                id="rule:stalled",
                arc_id="arc:marked_coin_investigation",
                outcome="failed_stalled",
                fail_after_turns_without_progress=80,
            )
        ],
    )

    assert result["failed_count"] == 1

    arc = result["story_arc_state_delta"]["story_arcs"]["arc:marked_coin_investigation"]
    assert arc["status"] == "failed"