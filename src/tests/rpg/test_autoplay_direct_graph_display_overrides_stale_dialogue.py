from tests.rpg.autoplay_llm_campaign import (
    _apply_dialogue_action_relevance_gate,
    _assert_repaired_dialogue_visible_fields,
    _direct_complete_graph_action_from_command,
)


def test_direct_graph_buy_overrides_stale_witness_dialogue():
    stale_row = {
        "turn_index": 14,
        "player_action": "I buy two rations from Bran.",
        "selected_narration": {
            "source": "provider_runtime_narration",
            "dialogue_source": "story_hook",
            "narration": "The practical request lands against the unease of the room.",
            "npc": {
                "speaker": "Bran",
                "line": "Ask plainly. Are you looking for the traveler, the road, or the person who frightened them?",
            },
        },
    }

    result = _direct_complete_graph_action_from_command(
        command="I buy two rations from Bran.",
        row=stale_row,
        all_graph_actions=[
            {
                "action_id": "buy_rations_from_bran",
                "command": "I buy two rations from Bran.",
                "mechanic": "buying",
                "mechanics": ["buying", "inventory_change", "currency_change"],
                "action_terms": ["buy", "rations", "bran"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    row = result["row"]
    row = _apply_dialogue_action_relevance_gate(row)
    row = _assert_repaired_dialogue_visible_fields(row)

    assert row["direct_graph_display_override"] is True
    assert "rations" in row["display_narration"].lower()
    assert "traveler" not in row["npc_line"].lower()
    assert "frightened" not in row["npc_line"].lower()
    assert "rations" in row["npc_line"].lower()
