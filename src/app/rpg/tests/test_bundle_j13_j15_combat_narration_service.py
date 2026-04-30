from app.rpg.narration.combat_service import generate_combat_narration_sync


def test_generate_combat_narration_sync_accepts_grounded_provider_json():
    def fake_llm(prompt: str) -> str:
        assert "Combat contract" in prompt
        return """
        {
          "format_version": "rpg_narration_v2",
          "narration": "Your arrow strikes the Bandit and drives him back, but he remains on his feet.",
          "action": "You wound the Bandit.",
          "npc": {"speaker": "", "line": ""},
          "reward": "",
          "followup_hooks": []
        }
        """

    result = generate_combat_narration_sync(
        combat_result={
            "reason": "combat_attack_resolved",
            "actor_id": "player",
            "target_id": "enemy:bandit_1",
            "hit": True,
            "damage_applied": 6,
            "target_hp_before": 8,
            "target_hp_after": 2,
            "defeated": False,
        },
        combat_state={
            "active": True,
            "participants": {
                "player": {"actor_id": "player", "name": "You"},
                "enemy:bandit_1": {"actor_id": "enemy:bandit_1", "name": "Bandit"},
            },
        },
        llm_json_call=fake_llm,
    )

    assert result["llm_called"] is True
    assert result["accepted"] is True
    assert result["combat_narration_validation"]["ok"] is True
    assert result["payload"]["narration"]


def test_generate_combat_narration_sync_rejects_invented_death():
    def fake_llm(prompt: str) -> str:
        return """
        {
          "format_version": "rpg_narration_v2",
          "narration": "Your arrow kills the Bandit stone dead.",
          "action": "The Bandit dies.",
          "npc": {"speaker": "", "line": ""},
          "reward": "",
          "followup_hooks": []
        }
        """

    result = generate_combat_narration_sync(
        combat_result={
            "reason": "combat_attack_resolved",
            "actor_id": "player",
            "target_id": "enemy:bandit_1",
            "hit": True,
            "damage_applied": 6,
            "target_hp_before": 8,
            "target_hp_after": 2,
            "defeated": False,
        },
        combat_state={
            "active": True,
            "participants": {
                "player": {"actor_id": "player", "name": "You"},
                "enemy:bandit_1": {"actor_id": "enemy:bandit_1", "name": "Bandit"},
            },
        },
        llm_json_call=fake_llm,
    )

    assert result["llm_called"] is True
    assert result["accepted"] is False
    assert "combat_narration_invented_death" in result["combat_narration_validation"]["warnings"]