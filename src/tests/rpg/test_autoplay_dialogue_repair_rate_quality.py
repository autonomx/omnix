from tests.rpg.autoplay_llm_campaign import (
    _build_dialogue_repair_quality_summary,
    _build_dialogue_stale_source_summary,
)


def test_dialogue_repair_quality_warns_when_repair_rate_high():
    summary = {
        "dialogue_action_relevance_summary": {
            "checked_count": 100,
            "repaired_count": 31,
            "unrepaired_count": 0,
        }
    }

    quality = _build_dialogue_repair_quality_summary(summary)

    assert quality["ok"] is True
    assert quality["product_quality_ok"] is False
    assert quality["repair_rate"] == 0.31
    assert "dialogue_action_relevance_repair_rate_high" in quality["warnings"]


def test_dialogue_stale_source_summary_counts_repaired_rows():
    transcript = [
        {
            "turn_index": 4,
            "player_action": "I buy two rations from Bran.",
            "canonical_turn_action": "I buy two rations from Bran.",
            "dialogue_action_relevance": {
                "repaired": True,
                "source": "combined_background",
                "reason": "action_category_mismatch",
            },
            "selected_narration": "Bran talks about an unrelated witness.",
        }
    ]

    stale = _build_dialogue_stale_source_summary(transcript)

    assert stale["checked_count"] == 1
    assert stale["repaired_count"] == 1
    assert stale["by_source"]["combined_background"] == 1
    assert stale["by_reason"]["action_category_mismatch"] == 1
