from app.rpg.narration.runtime_narration_contract import (
    _apply_grounding_to_runtime_payload,
)


def test_runtime_grounding_selects_safe_fallback_from_candidate_envelope():
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
            "action": "The unsupported debt claim is refused.",
            "npc": {"speaker": "Bran", "line": "Sorry, friend. I do not owe you anything."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    grounded = _apply_grounding_to_runtime_payload(
        payload,
        turn_contract={
            "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
            "current_location": "location:rusty_flagon_tavern",
            "state_delta": {},
        },
        simulation_state={},
        grounding_settings={
            "enabled": True,
            "llm_safe_fallback_candidate": True,
            "deterministic_fallback": True,
        },
    )

    assert grounded["grounding_validation"]["selected_candidate"] == "safe_fallback"
    assert grounded["grounding_validation"]["fallback_source"] == "llm_safe_fallback"
    assert grounded["grounding_validation"]["primary_rejected"] is True
    assert grounded["reward"] is None
    assert "do not owe" in grounded["npc"]["line"].lower()
    assert grounded["raw_narration_candidates"]["primary"]["reward"]["currency"]["gold"] == 50