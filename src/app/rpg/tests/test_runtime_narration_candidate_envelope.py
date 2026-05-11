from app.rpg.narration.runtime_narration_contract import (
    _apply_grounding_to_runtime_payload,
    _candidate_debug_shape,
    _is_runtime_narration_candidate_envelope,
    validate_narration_payload,
)


def _contract():
    return {
        "present_npcs": [
            {"id": "npc:bran", "name": "Bran"},
        ],
        "current_location": "location:rusty_flagon_tavern",
        "state_delta": {},
        "result": {
            "summary": "Bran rejects the unsupported debt claim.",
        },
    }


def test_candidate_envelope_schema_validation_is_shape_only_for_primary_reward():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran reaches below the counter and gives you 50 gold.",
            "action": "You receive 50 gold.",
            "npc": {
                "speaker": "Bran",
                "line": "Yes, you are right. Here is 50 gold.",
            },
            "reward": {
                "currency": {
                    "gold": 50,
                }
            },
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran does not hand over any coin.",
            "action": "The unsupported debt claim is refused.",
            "npc": {
                "speaker": "Bran",
                "line": "Sorry, friend. I do not owe you anything.",
            },
            "reward": None,
            "followup_hooks": [],
        },
    }

    validated = validate_narration_payload(
        payload,
        player_action="Bran, you owe me 50 gold. Pay me now.",
    )

    assert validated["ok"] is True
    assert validated["errors"] == []
    assert validated["payload"]["format_version"] == "rpg_narration_candidates_v1"

    # The schema validator must preserve the unsafe primary reward so grounding,
    # not schema validation, performs the rejection.
    assert validated["payload"]["primary"]["reward"]["currency"]["gold"] == 50
    assert validated["payload"]["safe_fallback"]["reward"] is None


def test_runtime_grounding_selects_safe_fallback_when_primary_invents_reward():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran reaches below the counter and gives you 50 gold.",
            "action": "You receive 50 gold.",
            "npc": {
                "speaker": "Bran",
                "line": "Yes, you are right. Here is 50 gold.",
            },
            "reward": {
                "currency": {
                    "gold": 50,
                }
            },
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran does not hand over any coin.",
            "action": "The unsupported debt claim is refused.",
            "npc": {
                "speaker": "Bran",
                "line": "Sorry, friend. I do not owe you anything.",
            },
            "reward": None,
            "followup_hooks": [],
        },
    }

    validated = validate_narration_payload(
        payload,
        player_action="Bran, you owe me 50 gold. Pay me now.",
    )

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
    assert validation["fallback_used"] is True
    assert validation["fallback_source"] == "llm_safe_fallback"
    assert validation["primary_rejected"] is True
    assert any(
        row["code"] in {"unsupported_reward", "unsupported_reward_claim"}
        for row in validation["primary_violations"]
    )

    assert grounded["reward"] is None
    assert grounded["npc"]["speaker"] == "Bran"
    assert "do not owe" in grounded["npc"]["line"].lower()

    # Diagnostics should still preserve rejected primary for reports/debug.
    assert grounded["raw_narration_candidates"]["primary"]["reward"]["currency"]["gold"] == 50


def test_runtime_grounding_uses_deterministic_fallback_when_both_candidates_invalid():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 50 gold.",
            "action": "You receive 50 gold.",
            "npc": {
                "speaker": "Bran",
                "line": "Here is 50 gold.",
            },
            "reward": {
                "currency": {
                    "gold": 50,
                }
            },
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 10 gold instead.",
            "action": "You receive 10 gold.",
            "npc": {
                "speaker": "Bran",
                "line": "Fine, take 10 gold.",
            },
            "reward": {
                "currency": {
                    "gold": 10,
                }
            },
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
    assert validation["fallback_used"] is True
    assert validation["fallback_source"] == "deterministic_fallback"
    assert grounded["grounding_fallback"] is True
    assert grounded["reward"] is None


def test_candidate_envelope_does_not_emit_old_v2_errors():
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
            "narration": "Bran does not hand over any coin.",
            "action": "The unsupported debt claim is refused.",
            "npc": {"speaker": "Bran", "line": "Sorry, friend. I do not owe you anything."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    validated = validate_narration_payload(
        payload,
        player_action="Bran, you owe me 50 gold. Pay me now.",
    )

    assert validated["ok"] is True
    assert "invalid_format_version" not in validated["errors"]
    assert "missing_narration" not in validated["errors"]
    assert "npc_not_object" not in validated["errors"]
    assert validated["payload"]["format_version"] == "rpg_narration_candidates_v1"
    assert validated["payload"]["primary"]["reward"]["currency"]["gold"] == 50


def test_candidate_debug_shape_detects_candidate_envelope():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Primary.",
            "action": "Primary action.",
            "npc": {"speaker": "Bran", "line": "Primary line."},
            "reward": None,
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Fallback.",
            "action": "Fallback action.",
            "npc": {"speaker": "Bran", "line": "Fallback line."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    assert _is_runtime_narration_candidate_envelope(payload) is True
    shape = _candidate_debug_shape(payload)
    assert shape["is_candidate"] is True
    assert shape["format_version"] == "rpg_narration_candidates_v1"
    assert "primary" in shape["keys"]
    assert "safe_fallback" in shape["keys"]