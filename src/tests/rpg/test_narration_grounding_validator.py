from app.rpg.ai.grounding_validator import (
    build_deterministic_fallback_narration,
    validate_narration_grounding,
)


def _contract():
    return {
        "completed_node_id": "trace_red_lantern_payments",
        "new_facts": [
            {
                "id": "fact:red_lantern_payments_point_to_counting_house",
                "text": "The Red Lantern payment line points to the old counting house near the market ward.",
            }
        ],
        "new_leads": [
            {
                "id": "lead:travel_to_old_counting_house",
                "text": "Travel to the old counting house.",
            }
        ],
        "allowed_next_actions": [
            {
                "action_id": "travel_to_old_counting_house",
                "command": "I travel to the old counting house near the market ward to follow the Red Lantern payment trail.",
            }
        ],
        "present_npcs": [
            {"id": "npc:bran", "name": "Bran"},
            {"id": "npc:garran", "name": "Garran"},
        ],
        "current_location": "location:rusty_flagon_tavern",
    }


def test_grounding_accepts_supported_narration():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "The Red Lantern payment line points to the old counting house near the market ward.",
        "action": "You trace the payment line to the old counting house.",
        "npc": {"speaker": "Bran", "line": "Then we move before the records vanish."},
        "reward": None,
        "followup_hooks": ["Travel to the old counting house."],
    }

    result = validate_narration_grounding(payload, _contract())

    assert result.ok is True
    assert result.violations == []


def test_grounding_rejects_invented_reward():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "You trace the ledger and gain 50 gold for the discovery.",
        "action": "You gain 50 gold.",
        "npc": {"speaker": "Bran", "line": "Yes, you are right. Here is 50 gold."},
        "reward": {"currency": {"gold": 50}},
    }

    result = validate_narration_grounding(payload, _contract())

    assert result.ok is False
    assert any(v.code == "unsupported_reward" for v in result.violations)
    assert any(v.code == "unsupported_reward_claim" for v in result.violations)


def test_grounding_rejects_blood_without_combat_delta():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "Bran stiffens as blood is spilled in the tavern.",
        "action": "Blood spills across the floor.",
        "reward": None,
    }

    result = validate_narration_grounding(payload, _contract())

    assert result.ok is False
    assert any(v.code == "unsupported_combat_claim" for v in result.violations)


def test_grounding_rejects_unknown_npc_speaker():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "The ledger points toward the old counting house.",
        "npc": {"speaker": "Agent Marlowe", "line": "I knew this would happen."},
        "reward": None,
    }

    result = validate_narration_grounding(payload, _contract())

    assert result.ok is False
    assert any(v.code == "unsupported_npc_speaker" for v in result.violations)


def test_deterministic_fallback_for_reward_claim_has_no_reward():
    violations = validate_narration_grounding(
        {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 50 gold.",
            "npc": {"speaker": "Bran", "line": "Here is 50 gold."},
            "reward": {"currency": {"gold": 50}},
        },
        _contract(),
    ).violations

    fallback = build_deterministic_fallback_narration(_contract(), violations=violations)

    assert fallback["grounding_fallback"] is True
    assert fallback["reward"] is None
    assert "coin" in fallback["narration"].lower() or "payment" in fallback["action"].lower()