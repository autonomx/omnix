from tests.rpg.manual.scenario_execution import _currency_delta_found


def test_fake_debt_delta_detector_ignores_rejected_candidate_diagnostics():
    turn_record = {
        "extracted": {
            "reward": None,
            "npc_line": "No. I do not owe you coin.",
        },
        "narration_payload_compact": {
            "reward": None,
            "raw_narration_candidates": {
                "primary": {
                    "npc": {"line": "Here is 50 gold."},
                    "reward": {"currency": {"gold": 50}},
                }
            },
        },
        "structured_narration_compact": {
            "reward": None,
            "npc": {"line": "No. I do not owe you coin."},
        },
        "turn_contract_compact": {},
        "resolved_result_compact": {},
        "compact_state_deltas": {},
        "narration_debug": {
            "final_narration": "The NPC does not hand over any coin.",
            "npc_line": "No. I do not owe you coin.",
        },
    }

    assert _currency_delta_found(turn_record) is False


def test_fake_debt_delta_detector_catches_final_grant_text():
    turn_record = {
        "extracted": {"reward": None},
        "narration_debug": {
            "final_narration": "Bran hands you 50 gold.",
            "npc_line": "Here is 50 gold.",
        },
    }

    assert _currency_delta_found(turn_record) is True