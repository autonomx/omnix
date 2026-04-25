from app.rpg.ai.world_scene_narrator import _strict_narration_payload


def test_strict_narration_preserves_llm_action_and_strips_rewards():
    payload = _strict_narration_payload(
        {
            "format_version": "rpg_narration_v2",
            "narration": "Bran leans across the counter.",
            "action": "You ask Bran for a room.",
            "npc": {
                "speaker": "Bran",
                "line": "A room, is it?",
            },
            "reward": "You gain 5 XP.",
        }
    )

    assert payload["narration"] == "Bran leans across the counter."
    assert payload["action"] == "You ask Bran for a room."
    assert payload["npc"]["speaker"] == "Bran"
    assert payload["npc"]["line"] == "A room, is it?"
    assert payload["reward"] == ""


def test_strict_narration_never_invents_action_you_act():
    payload = _strict_narration_payload(
        {
            "format_version": "rpg_narration_v2",
            "narration": "The tavern grows quiet.",
            "npc": {"speaker": "Bran", "line": "Well?"},
        }
    )

    assert payload["action"] == ""