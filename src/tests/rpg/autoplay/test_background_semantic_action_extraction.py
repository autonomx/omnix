from tests.rpg.autoplay_llm_campaign import _extract_background_semantic_action_record


def test_extracts_semantic_action_from_turn_contract_when_v2_missing():
    turn_result = {
        "turn_contract": {
            "semantic_action": {
                "semantic_action_type": "ask",
                "semantic_family": "social",
                "target": "bran",
            }
        }
    }

    extracted = _extract_background_semantic_action_record(turn_result)

    assert extracted["semantic_action_type"] == "ask"
    assert extracted["semantic_family"] == "social"
    assert extracted["target"] == "bran"


def test_prefers_top_level_semantic_action_v2_over_contract_semantic_action():
    turn_result = {
        "semantic_action_v2": {
            "semantic_action_type": "inspect",
        },
        "turn_contract": {
            "semantic_action": {
                "semantic_action_type": "ask",
            }
        },
    }

    extracted = _extract_background_semantic_action_record(turn_result)

    assert extracted["semantic_action_type"] == "inspect"