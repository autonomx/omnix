from rpg.interactive_cli_response_quality import apply_interactive_response_quality_cleanup


def test_phase13_50_rumor_fallback_cleanup_handles_in_tavern_suffix_from_live_matrix():
    original = {
        "turn_index": 1,
        "player_input": "Any rumors around here?",
        "raw_narration": "General Atmosphere/NPCs in Tavern checks the confirmed rumors and news and finds nothing backed by the current state.",
        "narration_preview": "General Atmosphere/NPCs in Tavern checks the confirmed rumors and news and finds nothing backed by the current state.",
        "narration_source": "rumor_repaired",
        "raw_npc": {
            "speaker": "General Atmosphere/NPCs in Tavern",
            "line": "I do not have any confirmed rumors or news for you right now.",
        },
        "raw_result": {
            "narration": "General Atmosphere/NPCs in Tavern checks the confirmed rumors and news and finds nothing backed by the current state.",
            "narration_source": "rumor_repaired",
            "npc": {
                "speaker": "General Atmosphere/NPCs in Tavern",
                "line": "I do not have any confirmed rumors or news for you right now.",
            },
        },
        "extracted": {
            "narration": "General Atmosphere/NPCs in Tavern checks the confirmed rumors and news and finds nothing backed by the current state.",
            "npc_speaker": "General Atmosphere/NPCs in Tavern",
            "npc_line": "I do not have any confirmed rumors or news for you right now.",
        },
        "interactive_cli_intent_diagnostics": {
            "final_classification": {
                "action_type": "talk",
                "target_npc": "General Atmosphere/NPCs in Tavern",
                "requested_terms": ["rumor"],
            }
        },
    }

    cleaned = apply_interactive_response_quality_cleanup(original, player_input="Any rumors around here?")

    assert cleaned["raw_npc"]["speaker"] == "Bran"
    assert cleaned["extracted"]["npc_speaker"] == "Bran"
    assert cleaned["raw_narration"] == "Bran checks the confirmed rumors and news and finds nothing backed by the current state."
    assert cleaned["interactive_cli_response_quality"]["cleanup_source"] == "rumor_fallback_speaker_stability"
