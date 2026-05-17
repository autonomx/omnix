from tests.rpg.autoplay_llm_campaign import (
    _apply_turn_bound_presentation_compatibility_gate,
)


def test_buy_rations_turn_clears_stale_investigation_npc_line():
    row = {
        "turn_index": 14,
        "player_action": "I buy two rations from Bran.",
        "canonical_turn_action": "I buy two rations from Bran.",
        "mechanics_covered_this_turn": ["buying", "inventory_change", "currency_change"],
        "narration": "The practical request lands against the unease of the room.",
        "display_narration": "The practical request lands against the unease of the room.",
        "selected_narration": "The practical request lands against the unease of the room.",
        "npc": {
            "speaker": "Bran",
            "line": "Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?",
        },
    }

    repaired = _apply_turn_bound_presentation_compatibility_gate(row)

    assert repaired["presentation_status"] == "attached_repaired"
    assert repaired["npc"] == {}
    assert repaired["npc_line"] == ""
    assert "purchase" in repaired["narration"].lower()
    assert repaired["dialogue_action_relevance"]["reason"] in {
        "action_presentation_category_mismatch",
        "unsupported_combat_claim_suppressed",
        "presentation_incompatible",
    }
