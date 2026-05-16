from tests.rpg.autoplay_llm_campaign import _cleanup_bad_generic_fallback_narration


def test_social_action_does_not_keep_practical_transaction_fallback():
    row = _cleanup_bad_generic_fallback_narration(
        {
            "player_action": "I ask Bran who saw the traveler leave by the side door.",
            "narration": "The exchange is handled as a practical transaction.",
        }
    )

    assert row["fallback_narration_cleanup_applied"] is True
    assert row["fallback_narration_category"] == "social"
    assert "practical transaction" not in row["narration"].lower()
    assert "conversation" in row["narration"].lower()


def test_travel_action_does_not_keep_combat_fallback():
    row = _cleanup_bad_generic_fallback_narration(
        {
            "player_action": "I travel toward the old mill.",
            "narration": "The combat moment resolves through the current objective.",
        }
    )

    assert row["fallback_narration_cleanup_applied"] is True
    assert row["fallback_narration_category"] == "travel"
    assert "combat moment" not in row["narration"].lower()
    assert "route" in row["narration"].lower() or "move" in row["narration"].lower()
