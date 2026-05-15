from tests.rpg.autoplay_llm_campaign import _apply_turn_action_consistency_gate


def test_run277_buy_rations_is_not_overwritten_by_witness_action():
    row = {
        "turn_index": 4,
        "player_action": "I buy two rations from Bran.",
        "progress_quality": {
            "player_action": "I turn to Mira and ask what she saw near the side door.",
            "quality": "no_change",
        },
        "turn_contract": {
            "player_action": "I buy two rations from Bran.",
        },
    }

    repaired = _apply_turn_action_consistency_gate(
        row,
        canonical_turn_action=(
            "I ask Bran who last saw the witness near the tavern, "
            "where they saw it, and what physical clue points to the next place."
        ),
    )

    assert repaired["canonical_turn_action"] == "I buy two rations from Bran."
    assert repaired["player_action"] == "I buy two rations from Bran."
    assert repaired["turn_contract"]["player_action"] == "I buy two rations from Bran."
    assert repaired["progress_quality"]["player_action"] == "I buy two rations from Bran."

    assert "witness" not in repaired["canonical_turn_action"].lower()
    assert "mira" not in repaired["canonical_turn_action"].lower()