from tests.rpg.autoplay_llm_campaign import (
    _apply_dialogue_action_relevance_gate,
    _assert_repaired_dialogue_visible_fields,
    _normalize_repaired_dialogue_transcript_rows,
)


def test_buy_rations_repair_updates_all_visible_fields():
    row = {
        "turn_index": 4,
        "player_action": "I buy two rations from Bran.",
        "dialogue_source": "story_hook_display:hook:witness:report_to_bran",
        "narration": "You direct your attention toward Mira, asking about the stranger she saw near the road.",
        "display_narration": "Bran listens carefully, then his face hardens as the witness details fit an old fear.",
        "selected_narration": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran listens carefully, then his face hardens as the witness details fit an old fear.",
            "action": "The witness report is received.",
            "npc": {
                "speaker": "Bran",
                "line": "That sounds like the bandit road. If they are involved, this will not end at my door.",
            },
            "dialogue_source": "story_hook_display:hook:witness:report_to_bran",
        },
        "result": {
            "narration": "Bran listens carefully, then his face hardens as the witness details fit an old fear.",
            "npc": {
                "speaker": "Bran",
                "line": "That sounds like the bandit road.",
            },
        },
    }

    repaired = _apply_dialogue_action_relevance_gate(row)
    repaired = _assert_repaired_dialogue_visible_fields(repaired)

    assert repaired["dialogue_action_relevance_repaired"] is True
    assert repaired["dialogue_source"] == "deterministic_action_relevance_fallback"

    assert "transaction" in repaired["narration"].lower()
    assert "transaction" in repaired["display_narration"].lower()
    assert "transaction" in repaired["selected_narration"]["narration"].lower()
    assert "transaction" in repaired["result"]["narration"].lower()

    assert repaired["npc"] == {}
    assert repaired["result"]["npc"] == {}

    forbidden = ("mira", "witness", "bandit road", "old fear")
    for term in forbidden:
        assert term not in repaired["narration"].lower()
        assert term not in repaired["display_narration"].lower()
        assert term not in repaired["selected_narration"]["narration"].lower()


def test_repaired_dialogue_normalization_overwrites_top_level_narration():
    row = {
        "turn_index": 4,
        "player_action": "I buy two rations from Bran.",
        "dialogue_source": "story_hook_display:hook:witness:report_to_bran",
        "narration": "Your gaze settles on Mira, the wary innkeeper.",
        "display_narration": "Bran listens carefully, then his face hardens as the witness details fit an old fear.",
        "selected_narration": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran listens carefully, then his face hardens as the witness details fit an old fear.",
            "action": "The witness report is received.",
            "npc": {
                "speaker": "Bran",
                "line": "That sounds like the bandit road.",
            },
            "dialogue_source": "story_hook_display:hook:witness:report_to_bran",
        },
    }

    repaired = _apply_dialogue_action_relevance_gate(row)
    repaired = _assert_repaired_dialogue_visible_fields(repaired)
    normalized = _normalize_repaired_dialogue_transcript_rows([repaired])[0]

    assert normalized["dialogue_action_relevance_repaired"] is True
    assert normalized["dialogue_source"] == "deterministic_action_relevance_fallback"

    assert "transaction" in normalized["narration"].lower()
    assert "transaction" in normalized["display_narration"].lower()
    assert "transaction" in normalized["selected_narration"]["narration"].lower()

    forbidden = ("mira", "witness", "bandit road", "old fear")
    for term in forbidden:
        assert term not in normalized["narration"].lower()
        assert term not in normalized["display_narration"].lower()
        assert term not in normalized["selected_narration"]["narration"].lower()