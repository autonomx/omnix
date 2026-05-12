from app.rpg.story.faction_pressure import (
    FactionPressureRule,
    emit_faction_pressure_events,
)
from app.rpg.story.tavern_faction_pressure_rules import tavern_faction_pressure_rules


def test_faction_pressure_emits_when_tier_matches():
    result = emit_faction_pressure_events(
        faction_state={
            "faction:test": {
                "reputation": -3,
                "tier": "suspicious",
            }
        },
        turn_index=10,
        rules=[
            FactionPressureRule(
                id="pressure:test",
                faction_id="faction:test",
                min_reputation=-10,
                max_reputation=-2,
                required_tier="suspicious",
                cooldown_turns=5,
                pressure_event={
                    "summary": "Watchers appear.",
                },
                world_signal={
                    "id": "signal:test",
                    "summary": "Pressure signal.",
                },
                set_flags=("pressure:test.active",),
            )
        ],
    )

    assert result["event_count"] == 1
    assert result["events"][0]["faction_id"] == "faction:test"
    assert len(result["world_signals"]) == 1
    assert result["flags"]["pressure:test.active"] is True


def test_faction_pressure_respects_cooldown():
    first = emit_faction_pressure_events(
        faction_state={
            "faction:test": {
                "reputation": -3,
                "tier": "suspicious",
            }
        },
        turn_index=10,
        rules=[
            FactionPressureRule(
                id="pressure:test",
                faction_id="faction:test",
                min_reputation=-10,
                max_reputation=-2,
                required_tier="suspicious",
                cooldown_turns=5,
            )
        ],
    )

    second = emit_faction_pressure_events(
        faction_state={
            "faction:test": {
                "reputation": -3,
                "tier": "suspicious",
            }
        },
        turn_index=12,
        rules=[
            FactionPressureRule(
                id="pressure:test",
                faction_id="faction:test",
                min_reputation=-10,
                max_reputation=-2,
                required_tier="suspicious",
                cooldown_turns=5,
            )
        ],
        last_emitted_turn_by_rule=first["last_emitted_turn_by_rule"],
    )

    assert first["event_count"] == 1
    assert second["event_count"] == 0


def test_tavern_pressure_rules_delegate_cooldown_to_pacing():
    rules = tavern_faction_pressure_rules()
    assert rules
    assert all(rule.cooldown_turns == 0 for rule in rules)