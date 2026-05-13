from app.rpg.story.escalation_arc_progression import (
    EscalationArcProgressionRule,
    progress_escalation_arcs,
)


def test_escalation_arc_progresses_when_rule_met():
    result = progress_escalation_arcs(
        story_arcs={
            "arc:handler": {
                "arc_id": "arc:handler",
                "status": "active",
                "current_stage": "seeded_escalation",
                "escalation_arc": True,
                "started_turn": 10,
                "progress_count": 0,
            }
        },
        state={
            "faction_reputation": {
                "faction:enemy": {
                    "tier": "hostile",
                    "reputation": -5,
                }
            }
        },
        turn_index=15,
        rules=[
            EscalationArcProgressionRule(
                id="rule:handler",
                arc_id="arc:handler",
                from_stage="seeded_escalation",
                to_stage="handler_moves",
                requires_turns_since_started=3,
                requires_faction_tier=("faction:enemy", "suspicious"),
                set_flags=("flag:handler_moves",),
                world_signals=({"id": "signal:handler"},),
            )
        ],
    )

    assert result["progressed_count"] == 1
    assert result["story_arcs"]["arc:handler"]["current_stage"] == "handler_moves"
    assert result["flags"]["flag:handler_moves"] is True
    assert len(result["world_signals"]) == 1