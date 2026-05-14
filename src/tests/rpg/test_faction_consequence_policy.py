from app.rpg.factions.faction_consequence_policy import (
    FactionConsequenceRule,
    emit_faction_consequences,
)


def test_faction_consequence_emits_when_combat_outcome_and_tier_match():
    result = emit_faction_consequences(
        state={
            "faction_reputation": {
                "faction:test": {"tier": "hostile", "reputation": -5}
            },
            "combat_lifecycle_summary": {
                "by_outcome": {"victory": 1}
            },
        },
        turn_index=20,
        rules=[
            FactionConsequenceRule(
                id="faction:test_rule",
                faction_id="faction:test",
                consequence_kind="retaliation",
                required_tier="suspicious",
                required_combat_outcome="victory",
                reputation_delta=-1,
                world_signal={"id": "signal:test", "summary": "Faction signal."},
            )
        ],
    )

    assert result["event_count"] == 1
    assert result["events"][0]["subtype"] == "retaliation"
    assert result["world_signals"]
    assert result["faction_reputation"]["faction:test"]["reputation"] == -6


def test_faction_consequence_respects_cooldown():
    first = emit_faction_consequences(
        state={
            "faction_reputation": {"faction:test": {"tier": "hostile"}},
            "combat_lifecycle_summary": {"by_outcome": {"victory": 1}},
        },
        turn_index=20,
        rules=[
            FactionConsequenceRule(
                id="faction:test_rule",
                faction_id="faction:test",
                consequence_kind="retaliation",
                required_tier="suspicious",
                required_combat_outcome="victory",
                cooldown_turns=20,
            )
        ],
    )

    second = emit_faction_consequences(
        state={
            "faction_reputation": {"faction:test": {"tier": "hostile"}},
            "combat_lifecycle_summary": {"by_outcome": {"victory": 1}},
        },
        turn_index=25,
        rules=[
            FactionConsequenceRule(
                id="faction:test_rule",
                faction_id="faction:test",
                consequence_kind="retaliation",
                required_tier="suspicious",
                required_combat_outcome="victory",
                cooldown_turns=20,
            )
        ],
        last_emitted_turn_by_rule=first["last_emitted_turn_by_rule"],
    )

    assert first["event_count"] == 1
    assert second["event_count"] == 0