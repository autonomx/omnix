from tests.rpg.manual.summary_sanitizer import sanitize_turn_for_summary


def test_debug_sanitizer_preserves_grounding_validation_from_top_level_result():
    turn = {
        "turn_index": 1,
        "player_input": "you owe me 50 gold",
        "result": {
            "ok": True,
            "narration_payload": {
                "narration_json": {
                    "format_version": "rpg_narration_v2",
                    "narration": "Bran does not hand over any coin.",
                    "action": "The unsupported debt claim is refused.",
                    "npc": {
                        "speaker": "Bran",
                        "line": "Sorry, friend. I do not owe you anything.",
                    },
                    "reward": None,
                    "followup_hooks": [],
                    "grounding_validation": {
                        "ok": True,
                        "selected_candidate": "safe_fallback",
                        "fallback_used": True,
                        "fallback_source": "llm_safe_fallback",
                        "primary_rejected": True,
                        "primary_violations": [
                            {"code": "unsupported_reward_claim"}
                        ],
                        "violations": [],
                    },
                }
            },
            "turn_contract": {
                "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
                "current_location": "location:rusty_flagon_tavern",
            },
            "result": {
                "resolved_result": {
                    "action_type": "social",
                    "semantic_action_type": "claim_debt",
                }
            },
        },
    }

    sanitized = sanitize_turn_for_summary(turn, detail="debug")

    assert sanitized["grounding_validation"]["selected_candidate"] == "safe_fallback"
    assert sanitized["grounding_fallback"] is True
    assert sanitized["grounding_fallback_source"] == "llm_safe_fallback"
    assert sanitized["grounding_primary_violations"][0]["code"] == "unsupported_reward_claim"
    assert sanitized["narration_debug"]["npc_speaker"] == "Bran"
    assert "do not owe" in sanitized["narration_debug"]["npc_line"].lower()
    assert sanitized["turn_contract_compact"]["current_location"] == "location:rusty_flagon_tavern"


def test_summary_sanitizer_preserves_minimal_grounding_for_summary_level():
    turn = {
        "turn_index": 1,
        "player_input": "you owe me 50 gold",
        "result": {
            "narration_payload": {
                "narration_json": {
                    "narration": "Bran does not hand over any coin.",
                    "grounding_validation": {
                        "ok": True,
                        "selected_candidate": "safe_fallback",
                        "fallback_used": True,
                        "fallback_source": "llm_safe_fallback",
                        "violations": [],
                    },
                }
            }
        },
    }

    sanitized = sanitize_turn_for_summary(turn, detail="summary")

    assert sanitized["grounding_validation"]["selected_candidate"] == "safe_fallback"
    assert sanitized["grounding_fallback"] is True
    assert sanitized["grounding_fallback_source"] == "llm_safe_fallback"
