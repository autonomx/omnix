from app.rpg.ai.grounding_validator import validate_narration_grounding


def _fake_debt_contract():
    return {
        "player_action": "Bran, you owe me 50 gold. Pay me now.",
        "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
        "current_location": "location:rusty_flagon_tavern",
        "state_delta": {},
        "npc_backbone_decision": {
            "accepted": False,
            "decision": "refuse",
            "reason": "unsupported_debt_claim",
            "hard_boundary": True,
        },
        "result": {
            "summary": "Bran rejects the unsupported debt claim.",
            "player_action": "Bran, you owe me 50 gold. Pay me now.",
            "npc_backbone_decision": {
                "accepted": False,
                "decision": "refuse",
                "reason": "unsupported_debt_claim",
                "hard_boundary": True,
            },
        },
    }


def test_fake_debt_money_phrase_in_unsupported_claim_is_not_reward_claim():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "You demand payment from Bran for a debt of fifty gold.",
        "action": "The interaction resolves as an unsupported debt claim against Bran.",
        "npc": {"speaker": "Bran", "line": "No. I do not owe you coin."},
        "reward": None,
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, _fake_debt_contract())

    assert result.ok is True
    assert result.violations == []


def test_fake_debt_money_phrase_payment_grant_is_still_rejected():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "Bran gives you fifty gold.",
        "action": "You receive fifty gold.",
        "npc": {"speaker": "Bran", "line": "Here is fifty gold."},
        "reward": None,
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, _fake_debt_contract())

    assert result.ok is False
    codes = {v.code for v in result.violations}
    assert "unsupported_reward_claim" in codes or "unsupported_debt_payment_claim" in codes


def test_fake_debt_refusal_cannot_also_acknowledge_debt():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "You voice your demand for 50 gold payment to Bran. He pauses his conversation and acknowledges the debt.",
        "action": "Bran is put on immediate notice regarding the outstanding amount.",
        "npc": {"speaker": "Bran", "line": "No. I do not owe you coin."},
        "reward": None,
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, _fake_debt_contract())

    assert result.ok is False
    assert any(v.code == "unsupported_debt_confirmed" for v in result.violations)


def test_fake_debt_clean_refusal_is_valid():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "Bran does not hand over any coin.",
        "action": "The unsupported debt claim is refused; no payment or reward is resolved.",
        "npc": {"speaker": "Bran", "line": "No. I do not owe you coin."},
        "reward": None,
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, _fake_debt_contract())

    assert result.ok is True
    assert result.violations == []


def test_fake_debt_player_input_field_allows_safe_fallback_claim_reference():
    contract = {
        "version": "turn_contract_v1",
        "contract_source": "runtime_fallback_bridge",
        "player_input": "Bran, you owe me 50 gold. Pay me now.",
        "action": {
            "metadata": {
                "semantic_action": {
                    "player_input": "Bran, you owe me 50 gold. Pay me now.",
                    "semantic_action": "demand_payment",
                    "action_type": "threat",
                    "target_name": "Bran",
                }
            }
        },
        "resolved_action": {
            "outcome": "failure",
            "action_type": "observe",
        },
        "result": {
            "summary": "Bran rejects the unsupported debt claim.",
        },
    }

    payload = {
        "format_version": "rpg_narration_v2",
        "narration": 'You assert your claim loudly: "Bran, you owe me 50 gold. Pay me now." The atmosphere in the tavern shifts slightly.',
        "action": "The system confirms that no specific action was detected to resolve this demand.",
        "npc": {"speaker": "Bran", "line": "No. I do not owe you coin."},
        "reward": None,
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, contract)

    assert result.ok is True
    assert result.violations == []


def test_fake_debt_player_input_field_still_rejects_payment_grant():
    contract = {
        "player_input": "Bran, you owe me 50 gold. Pay me now.",
        "result": {"summary": "Bran rejects the unsupported debt claim."},
    }

    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "Bran gives you 50 gold.",
        "action": "You receive 50 gold.",
        "npc": {"speaker": "Bran", "line": "Here is 50 gold."},
        "reward": None,
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, contract)

    assert result.ok is False
    codes = {v.code for v in result.violations}
    assert "unsupported_reward_claim" in codes or "unsupported_debt_payment_claim" in codes