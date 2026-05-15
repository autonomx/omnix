from app.rpg.dialogue.dialogue_action_relevance import (
    build_action_relevant_fallback,
    should_allow_display_source,
    validate_dialogue_action_relevance,
)


def test_commerce_action_blocks_stale_witness_dialogue():
    result = validate_dialogue_action_relevance(
        player_action="I buy two rations from Bran.",
        row={},
        display_source="story_hook_display:hook:witness:report_to_bran",
        narration="Bran listens carefully, then his face hardens as the witness details fit an old fear.",
        npc_speaker="Bran",
        npc_line="That sounds like the bandit road.",
    )

    assert result["ok"] is False
    assert "commerce_action_dialogue_mismatch" in result["reasons"]
    assert "stale_witness_dialogue_for_unrelated_action" in result["reasons"]


def test_travel_action_blocks_tavern_conversation_beat():
    result = validate_dialogue_action_relevance(
        player_action="I travel to the old north watchpost.",
        row={
            "location_id": "location:old_north_watchpost",
            "npc_presence": {
                "npc:bran": {
                    "location_id": "scene:rusty_flagon",
                    "availability": "available",
                }
            },
        },
        display_source="conversation_beat",
        narration="Bran reacts to the question.",
        npc_speaker="Bran",
        npc_line="The room has been busier than usual tonight.",
    )

    assert result["ok"] is False
    assert "travel_action_dialogue_mismatch" in result["reasons"]
    assert "speaker_presence_mismatch" in result["reasons"]


def test_combat_action_blocks_stale_social_dialogue():
    result = validate_dialogue_action_relevance(
        player_action="I press the attack until the bandit scouts are defeated.",
        row={},
        display_source="raw_ai_payload",
        narration="Bran reacts to the question.",
        npc_speaker="Bran",
        npc_line="Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?",
    )

    assert result["ok"] is False
    assert "combat_action_dialogue_mismatch" in result["reasons"]


def test_display_source_gate_blocks_hook_for_commerce():
    result = should_allow_display_source(
        player_action="I pay Bran 5 silver for a common room.",
        display_source="story_hook_display:hook:witness:report_to_bran",
        row={},
    )

    assert result["ok"] is False
    assert result["blocked_reasons"]


def test_action_relevant_fallback_is_safe_for_commerce():
    fallback = build_action_relevant_fallback(
        player_action="I buy two rations from Bran.",
        row={},
    )

    assert fallback["dialogue_source"] == "deterministic_action_relevance_fallback"
    assert fallback["npc"] == {}
    assert "transaction" in fallback["narration"].lower()