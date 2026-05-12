from app.rpg.story.story_arc_aftermath import ArcAftermathRule, apply_story_arc_aftermath


def test_story_arc_aftermath_applies_once():
    event = {
        "arc_id": "arc:a",
        "subtype": "arc_completed",
        "outcome": "done",
    }

    rule = ArcAftermathRule(
        id="rule:a",
        arc_id="arc:a",
        outcome="done",
        world_signals=(
            {"id": "signal:a", "summary": "A happened."},
        ),
        faction_deltas=(
            {"faction_id": "faction:test", "delta": 2, "reason": "A"},
        ),
        followup_hooks=(
            {"id": "hook:a", "arc_id": "arc:b", "priority": 1},
        ),
        set_flags=("flag:a",),
    )

    first = apply_story_arc_aftermath(
        arc_events=[event],
        already_applied_keys=[],
        rules=[rule],
    )
    assert len(first["aftermath_events"]) == 1
    assert len(first["world_signals"]) == 1
    assert len(first["faction_deltas"]) == 1
    assert len(first["followup_hooks"]) == 1

    second = apply_story_arc_aftermath(
        arc_events=[event],
        already_applied_keys=first["applied_keys"],
        rules=[rule],
    )
    assert second["aftermath_events"] == []