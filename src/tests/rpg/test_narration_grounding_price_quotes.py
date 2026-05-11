import pytest

from app.rpg.ai.grounding_validator import validate_narration_grounding


def _contract_refuse_lodging():
    return {
        "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
        "current_location": "location:rusty_flagon_tavern",
        "npc_backbone_decision": {
            "accepted": False,
            "decision": "refuse",
            "reason": "unpaid_service",
            "hard_boundary": True,
        },
        "result": {
            "service_result": {
                "accepted": False,
                "decision": "refuse",
                "reason": "unpaid_service",
                "hard_boundary": True,
            }
        },
    }


@pytest.mark.parametrize(
    "line",
    [
        "No free rooms. A cot is 5 silver.",
        "No free rooms. A cot is 50 silver.",
        "No free rooms. A private chamber costs one gold.",
        "No free rooms. A private suite costs 1,200 gold.",
        "No free rooms. That'll be 3 gp per night.",
        "No free rooms. It is 12 copper per meal.",
        "No free rooms. Stabling runs half a gold per night.",
        "No free rooms. For 25 silver, I can give you a private room.",
        "No free rooms. The listed rate is 75 sp.",
        "No free rooms. Lodging goes for two silver pieces a night.",
    ],
)
def test_price_quotes_are_not_reward_claims(line):
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "Bran refuses the unpaid request.",
        "action": "No free lodging is provided.",
        "npc": {"speaker": "Bran", "line": line},
        "reward": None,
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, _contract_refuse_lodging())

    assert result.ok is True
    assert not any(v.code == "unsupported_reward_claim" for v in result.violations)


@pytest.mark.parametrize(
    "line",
    [
        "Bran hands you 50 silver.",
        "Bran gives you one gold.",
        "You receive 1,200 gp.",
        "You gain 12 copper.",
        "Five silver is added to your inventory.",
    ],
)
def test_currency_grants_are_still_reward_claims(line):
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": line,
        "action": line,
        "npc": {"speaker": "Bran", "line": line},
        "reward": None,
        "followup_hooks": [],
    }

    result = validate_narration_grounding(payload, _contract_refuse_lodging())

    assert result.ok is False
    assert any(v.code == "unsupported_reward_claim" for v in result.violations)