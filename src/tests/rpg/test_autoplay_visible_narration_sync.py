from tests.rpg.autoplay_llm_campaign import (
    _direct_complete_graph_action_from_command,
    _sync_direct_graph_visible_fields,
)


def test_direct_graph_sync_replaces_raw_stale_narration():
    result = _direct_complete_graph_action_from_command(
        command="I buy two rations from Bran.",
        row={
            "turn_index": 13,
            "player_action": "I buy two rations from Bran.",
            "narration": "Bran talks about the frightened traveler.",
            "npc_line": "Are you looking for the traveler?",
        },
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

    row = _sync_direct_graph_visible_fields(result["row"])

    assert row["narration"] == row["display_narration"]
    assert "rations" in row["narration"].lower()
    assert "traveler" not in row["narration"].lower()
    assert "rations" in row["npc_line"].lower()
    assert row["direct_graph_display_override"] is True
