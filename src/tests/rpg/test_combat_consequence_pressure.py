from app.rpg.combat.combat_consequence_pressure import apply_combat_consequence_pressure


def test_combat_consequence_pressure_emits_recovery_event_and_economy_hint():
    result = apply_combat_consequence_pressure(
        player_state={"hp": 12, "max_hp": 20},
        pending_injuries=[
            {
                "encounter_id": "encounter:test",
                "severity": 2,
                "resolved": False,
            }
        ],
        turn_index=20,
    )

    assert result["event_count"] == 1
    assert result["events"][0]["subtype"] == "recovery_pressure"
    assert result["economy_pressure_hints"][0]["amount"] == 2
    assert result["pending_injuries"][0]["resolved"] is True