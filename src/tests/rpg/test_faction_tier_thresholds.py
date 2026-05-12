from app.rpg.story.faction_pressure import (
    FactionPressureRule,
    emit_faction_pressure_events,
)
from app.rpg.story.followup_arc_progression import (
    FollowupArcProgressionRule,
    progress_followup_arcs,
)
from app.rpg.story.followup_arc_resolution import (
    FollowupArcResolutionRule,
    resolve_followup_arcs,
)


def test_progression_suspicious_requirement_accepts_hostile():
    result = progress_followup_arcs(
        story_arcs={
            "arc:test": {
                "arc_id": "arc:test",
                "status": "active",
                "current_stage": "seeded_followup",
                "started_turn": 1,
            }
        },
        state={
            "faction_reputation": {
                "faction:enemy": {
                    "tier": "hostile",
                    "reputation": -6,
                }
            }
        },
        turn_index=10,
        rules=[
            FollowupArcProgressionRule(
                id="rule:test",
                arc_id="arc:test",
                requires_turns_since_started=1,
                requires_faction_tier=("faction:enemy", "suspicious"),
                to_stage="progressed",
            )
        ],
    )

    assert result["progressed_count"] == 1


def test_progression_friendly_requirement_accepts_trusted():
    result = progress_followup_arcs(
        story_arcs={
            "arc:test": {
                "arc_id": "arc:test",
                "status": "active",
                "current_stage": "seeded_followup",
                "started_turn": 1,
            }
        },
        state={
            "faction_reputation": {
                "faction:ally": {
                    "tier": "trusted",
                    "reputation": 6,
                }
            }
        },
        turn_index=10,
        rules=[
            FollowupArcProgressionRule(
                id="rule:test",
                arc_id="arc:test",
                requires_turns_since_started=1,
                requires_faction_tier=("faction:ally", "friendly"),
                to_stage="progressed",
            )
        ],
    )

    assert result["progressed_count"] == 1


def test_resolution_suspicious_requirement_accepts_hostile():
    result = resolve_followup_arcs(
        story_arcs={
            "arc:test": {
                "arc_id": "arc:test",
                "status": "active",
                "current_stage": "progressed",
                "last_progress_turn": 1,
            }
        },
        state={
            "faction_reputation": {
                "faction:enemy": {
                    "tier": "hostile",
                    "reputation": -6,
                }
            }
        },
        turn_index=10,
        rules=[
            FollowupArcResolutionRule(
                id="rule:test",
                arc_id="arc:test",
                from_stage="progressed",
                requires_turns_since_progress=1,
                requires_faction_tier=("faction:enemy", "suspicious"),
            )
        ],
    )

    assert result["resolved_count"] == 1


def test_pressure_suspicious_requirement_accepts_hostile():
    result = emit_faction_pressure_events(
        faction_state={
            "faction:enemy": {
                "tier": "hostile",
                "reputation": -6,
            }
        },
        turn_index=10,
        rules=[
            FactionPressureRule(
                id="pressure:test",
                faction_id="faction:enemy",
                min_reputation=-10,
                max_reputation=-2,
                required_tier="suspicious",
            )
        ],
    )

    assert result["event_count"] == 1