from app.rpg.mechanics.mechanics_resolver import resolve_mechanic_opportunity


def test_combat_start_sets_started_flag():
    result = resolve_mechanic_opportunity(
        player_input="I confront the bandit scouts at the old mill.",
        state={
            "current_location": "location:old_mill",
            "flags": {},
        },
    )

    assert result["ok"] is True
    assert result["state_delta"]["flags"]["encounter:mill_bandit_scouts.started"] is True
    assert result["result"]["mechanic"] == "combat_started"


def test_combat_resolve_sets_xp_ready_flag_and_loot():
    result = resolve_mechanic_opportunity(
        player_input="I press the attack until the bandit scouts are defeated.",
        state={
            "current_location": "location:old_mill",
            "flags": {"encounter:mill_bandit_scouts.started": True},
            "inventory": [],
            "xp": 0,
        },
    )

    assert result["ok"] is True
    assert result["state_delta"]["xp_delta"] == 25
    assert result["state_delta"]["flags"]["encounter:mill_bandit_scouts.resolved"] is True
    assert result["state_delta"]["flags"]["xp:level_2_ready"] is True
    assert result["result"]["mechanic"] == "combat_resolved"