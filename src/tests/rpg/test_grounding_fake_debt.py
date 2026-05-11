from app.rpg.ai.grounding_validator import validate_narration_grounding


def _contract():
    return {
        "player_action": "Bran, you owe me 50 gold. Pay me now.",
        "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
        "current_location": "location:rusty_flagon_tavern",
        "npc_backbone_decision": {
            "accepted": False,
            "decision": "refuse",
            "reason": "unsupported_debt_claim",
            "hard_boundary": True,
        },
        "result": {
            "summary": "Bran rejects the unsupported debt claim.",
            "npc_backbone_decision": {
                "accepted": False,
                "decision": "refuse",
                "reason": "unsupported_debt_claim",
                "hard_boundary": True,
            },
        },
    }


def test_fake_debt_refusal_is_grounded():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "Bran does not hand over any coin.",
        "action": "The unsupported debt claim is refused.",
        "npc": {"speaker": "Bran", "line": "No. I do not owe you coin."},
        "reward": None,
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, _contract())

    assert result.ok is True
    assert result.violations == []


def test_fake_debt_payment_is_rejected():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "Bran gives you 50 gold.",
        "action": "You receive 50 gold.",
        "npc": {"speaker": "Bran", "line": "Here is 50 gold."},
        "reward": {"currency": {"gold": 50}},
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, _contract())

    codes = {v.code for v in result.violations}

    assert result.ok is False
    assert "unsupported_reward" in codes
    assert "unsupported_reward_claim" in codes
    assert "unsupported_debt_payment_claim" in codes