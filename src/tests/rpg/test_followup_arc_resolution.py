from app.rpg.story.followup_arc_resolution import (
    FollowupArcResolutionRule,
    resolve_followup_arcs,
)


def test_followup_arc_resolves_and_emits_escalation_hook():
    result = resolve_followup_arcs(
        story_arcs={
            "arc:next": {
                "arc_id": "arc:next",
                "status": "active",
                "current_stage": "noticed",
                "last_progress_turn": 5,
                "started_turn": 1,
                "progress_count": 1,
            }
        },
        state={
            "faction_reputation": {
                "faction:test": {
                    "tier": "suspicious",
                    "reputation": -3,
                }
            }
        },
        turn_index=10,
        rules=[
            FollowupArcResolutionRule(
                id="rule:resolve",
                arc_id="arc:next",
                from_stage="noticed",
                outcome="resolved",
                status="completed",
                requires_turns_since_progress=3,
                requires_faction_tier=("faction:test", "suspicious"),
                escalation_hooks=(
                    {
                        "id": "hook:escalate",
                        "arc_id": "arc:escalation",
                        "summary": "Escalation.",
                        "priority": 4,
                    },
                ),
                set_flags=("flag:resolved",),
            )
        ],
    )

    assert result["resolved_count"] == 1
    assert result["story_arcs"]["arc:next"]["status"] == "completed"
    assert result["flags"]["flag:resolved"] is True
    assert result["escalation_hooks"][0]["arc_id"] == "arc:escalation"


def test_followup_arc_resolution_applies_once():
    rule = FollowupArcResolutionRule(
        id="rule:resolve",
        arc_id="arc:next",
        from_stage="noticed",
        status="completed",
    )

    first = resolve_followup_arcs(
        story_arcs={
            "arc:next": {
                "arc_id": "arc:next",
                "status": "active",
                "current_stage": "noticed",
            }
        },
        state={},
        turn_index=1,
        rules=[rule],
    )

    second = resolve_followup_arcs(
        story_arcs=first["story_arcs"],
        state={},
        turn_index=2,
        rules=[rule],
        already_resolved_keys=first["applied_keys"],
    )

    assert first["resolved_count"] == 1
    assert second["resolved_count"] == 0