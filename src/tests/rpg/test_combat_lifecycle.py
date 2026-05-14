from app.rpg.combat.combat_lifecycle import CombatEncounterRule, run_combat_lifecycle_tick


def test_combat_lifecycle_resolves_encounter_when_rule_matches():
    result = run_combat_lifecycle_tick(
        combat_state={},
        player_state={"hp": 20, "max_hp": 20},
        world_state={
            "story_arcs": {"arc:test": {"current_stage": "active"}},
            "faction_reputation": {"faction:test": {"tier": "hostile"}},
        },
        turn_index=10,
        rules=[
            CombatEncounterRule(
                id="combat:test",
                encounter_id="encounter:test",
                trigger_every_turns=5,
                required_arc_stage=("arc:test", "active"),
                required_faction_tier=("faction:test", "suspicious"),
                enemy_id="enemy:test",
                enemy_name="Test Enemy",
                enemy_hp=6,
                enemy_attack=2,
                player_attack=3,
                max_rounds=3,
                world_signal={"id": "signal:test", "summary": "Combat signal."},
            )
        ],
    )

    assert result["encounter_count"] == 1
    assert result["event_count"] == 1
    assert result["encounters"][0]["outcome"] in {"victory", "withdraw", "player_defeated"}
    assert result["world_signals"]
    assert result["memory_events"]


def test_combat_lifecycle_respects_cooldown():
    first = run_combat_lifecycle_tick(
        combat_state={},
        player_state={"hp": 20, "max_hp": 20},
        world_state={},
        turn_index=10,
        rules=[
            CombatEncounterRule(
                id="combat:test",
                encounter_id="encounter:test",
                trigger_every_turns=5,
                cooldown_turns=20,
            )
        ],
    )

    second = run_combat_lifecycle_tick(
        combat_state=first["combat_state"],
        player_state=first["player_state"],
        world_state={},
        turn_index=15,
        rules=[
            CombatEncounterRule(
                id="combat:test",
                encounter_id="encounter:test",
                trigger_every_turns=5,
                cooldown_turns=20,
            )
        ],
        last_trigger_turn_by_rule=first["last_trigger_turn_by_rule"],
    )

    assert first["encounter_count"] == 1
    assert second["encounter_count"] == 0