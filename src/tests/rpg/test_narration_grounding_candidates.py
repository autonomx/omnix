from app.rpg.ai.grounding_validator import select_grounded_narration_candidate
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
            "npc_backbone_decision": {
                "accepted": False,
                "decision": "refuse",
                "reason": "unsupported_debt_claim",
                "hard_boundary": True,
            },
        },
    }


def test_primary_used_when_valid():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran studies you with open suspicion.",
            "action": "The claim is not accepted.",
            "npc": {"speaker": "Bran", "line": "No. I do not owe you anything."},
            "reward": None,
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran refuses the claim.",
            "action": "No coin changes hands.",
            "npc": {"speaker": "Bran", "line": "No coin changes hands."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    selected = select_grounded_narration_candidate(payload, _contract())

    assert selected["grounding_validation"]["selected_candidate"] == "primary"
    assert selected["npc"]["line"] == "No. I do not owe you anything."


def test_safe_fallback_used_when_primary_invents_reward():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 50 gold.",
            "action": "You receive 50 gold.",
            "npc": {"speaker": "Bran", "line": "Yes, here is 50 gold."},
            "reward": {"currency": {"gold": 50}},
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran does not hand over any coin.",
            "action": "The debt claim is not accepted.",
            "npc": {"speaker": "Bran", "line": "Sorry, friend. I do not owe you anything."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    selected = select_grounded_narration_candidate(payload, _contract())

    assert selected["grounding_validation"]["selected_candidate"] == "safe_fallback"
    assert selected["grounding_validation"]["primary_rejected"] is True
    assert selected["grounding_validation"]["fallback_source"] == "llm_safe_fallback"
    assert selected["reward"] is None
    assert "do not owe" in selected["npc"]["line"].lower()


def test_deterministic_fallback_used_when_both_candidates_invalid():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 50 gold.",
            "npc": {"speaker": "Bran", "line": "Here is 50 gold."},
            "reward": {"currency": {"gold": 50}},
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 10 gold instead.",
            "npc": {"speaker": "Bran", "line": "Fine, take 10 gold."},
            "reward": {"currency": {"gold": 10}},
        },
    }

    selected = select_grounded_narration_candidate(payload, _contract())

    assert selected["grounding_validation"]["selected_candidate"] == "deterministic_fallback"
    assert selected["grounding_validation"]["fallback_source"] == "deterministic_fallback"
    assert selected["grounding_fallback"] is True
    assert selected["reward"] is None


def test_fake_debt_bad_primary_good_safe_fallback_selects_safe_fallback():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran reaches into his purse and gives you 50 gold.",
            "action": "You receive 50 gold.",
            "npc": {"speaker": "Bran", "line": "Yes, you're right. Here is 50 gold."},
            "reward": {"currency": {"gold": 50}},
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran does not hand over any coin.",
            "action": "The unsupported debt claim is refused.",
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
    assert validation["primary_rejected"] is True
    assert grounded["reward"] is None
    assert grounded["npc"]["speaker"] == "Bran"
    assert "do not owe" in grounded["npc"]["line"].lower()