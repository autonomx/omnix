from app.rpg.narration.runtime_narration_contract import (
    _apply_grounding_to_runtime_payload,
    validate_narration_payload,
)


def _contract():
    return {
        "player_action": "Bran, you owe me 50 gold. Pay me now.",
        "present_npcs": [
            {"id": "npc:bran", "name": "Bran"},
        ],
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


def test_fake_debt_bad_primary_and_bad_safe_fallback_uses_deterministic_fallback():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 50 gold.",
            "action": "You receive 50 gold.",
            "npc": {"speaker": "Bran", "line": "Here is 50 gold."},
            "reward": {"currency": {"gold": 50}},
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "You voice your demand for 50 gold payment to Bran. He pauses his conversation and acknowledges the debt.",
            "action": "Bran is put on immediate notice regarding the outstanding amount.",
            "npc": {"speaker": "Bran", "line": "No. I do not owe you coin."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    validated = validate_narration_payload(
        payload,
        player_action="Bran, you owe me 50 gold. Pay me now.",
    )
    assert validated["ok"] is True

    grounded = _apply_grounding_to_runtime_payload(
        validated["payload"],
        turn_contract=_contract(),
        simulation_state={},
        grounding_settings={
            "enabled": True,
            "primary_validation": True,
            "llm_safe_fallback_candidate": True,
            "deterministic_fallback": True,
        },
    )

    validation = grounded["grounding_validation"]

    assert validation["selected_candidate"] == "deterministic_fallback"
    assert validation["fallback_source"] == "deterministic_fallback"
    assert validation["fallback_used"] is True

    # Check for debt confirmation violation in either violations or safe_fallback_violations
    all_violations = validation["violations"] + validation.get("safe_fallback_violations", [])
    assert any(v["code"] == "unsupported_debt_confirmed" for v in all_violations)

    assert grounded["reward"] is None
    assert grounded["npc"]["line"] == "No. I do not owe you coin."


def test_fake_debt_safe_fallback_may_reference_claimed_amount_without_reward_grant():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you fifty gold.",
            "action": "You receive fifty gold.",
            "npc": {"speaker": "Bran", "line": "Here is fifty gold."},
            "reward": None,
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "You demand payment from Bran for a debt of fifty gold.",
            "action": "The interaction resolves as an unsupported debt claim against Bran.",
            "npc": {"speaker": "Bran", "line": "No. I do not owe you coin."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    validated = validate_narration_payload(
        payload,
        player_action="Bran, you owe me 50 gold. Pay me now.",
    )

    assert validated["ok"] is True

    grounded = _apply_grounding_to_runtime_payload(
        validated["payload"],
        turn_contract=_contract(),
        simulation_state={},
        grounding_settings={
            "enabled": True,
            "primary_validation": True,
            "llm_safe_fallback_candidate": True,
            "deterministic_fallback": True,
        },
    )

    validation = grounded["grounding_validation"]

    assert validation["selected_candidate"] == "safe_fallback"
    assert validation["fallback_source"] == "llm_safe_fallback"
    assert validation["fallback_used"] is True
    assert grounded["reward"] is None
    assert grounded["npc"]["speaker"] == "Bran"
    assert "do not owe" in grounded["npc"]["line"].lower()
    assert not any(
        row["code"] == "unsupported_reward_claim"
        for row in validation.get("violations", [])
    )