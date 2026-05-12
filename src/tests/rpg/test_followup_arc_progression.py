from app.rpg.story.followup_arc_progression import (
    FollowupArcProgressionRule,
    progress_followup_arcs,
)


def test_followup_arc_progresses_when_rule_met():
    result = progress_followup_arcs(
        story_arcs={
            "arc:next": {
                "arc_id": "arc:next",
                "status": "active",
                "current_stage": "seeded_followup",
                "started_turn": 5,
                "progress_count": 0,
                "source_hook_id": "hook:next",
                "history": [],
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
            FollowupArcProgressionRule(
                id="rule:progress",
                arc_id="arc:next",
                from_stage="seeded_followup",
                to_stage="noticed",
                requires_turns_since_started=3,
                requires_faction_tier=("faction:test", "suspicious"),
                set_flags=("flag:noticed",),
                world_signals=(
                    {"id": "signal:noticed", "summary": "Noticed."},
                ),
            )
        ],
    )

    assert result["progressed_count"] == 1
    assert result["story_arcs"]["arc:next"]["current_stage"] == "noticed"
    assert result["flags"]["flag:noticed"] is True
    assert len(result["world_signals"]) == 1


def test_followup_arc_progression_applies_once():
    rule = FollowupArcProgressionRule(
        id="rule:progress",
        arc_id="arc:next",
        from_stage="seeded_followup",
        to_stage="noticed",
    )

    first = progress_followup_arcs(
        story_arcs={
            "arc:next": {
                "arc_id": "arc:next",
                "status": "active",
                "current_stage": "seeded_followup",
            }
        },
        state={},
        turn_index=1,
        rules=[rule],
    )

    second = progress_followup_arcs(
        story_arcs=first["story_arcs"],
        state={},
        turn_index=2,
        rules=[rule],
        already_progressed_keys=first["applied_keys"],
    )

    assert first["progressed_count"] == 1
    assert second["progressed_count"] == 0