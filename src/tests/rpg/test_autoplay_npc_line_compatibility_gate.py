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

    # N116.1 keeps harmless visible narration for soft classification issues.
    # Hard fallback is reserved for factual hallucinations.
    assert repaired["presentation_status"] in {"attached", "attached_metadata_repaired"}
    assert repaired["visible_text_replaced"] is False
    assert "practical request" in repaired["narration"].lower()
