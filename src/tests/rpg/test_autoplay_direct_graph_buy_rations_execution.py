from tests.rpg.autoplay_llm_campaign import _direct_complete_graph_action_from_command


def test_buy_rations_direct_graph_completion_mutates_row_state_result_and_display():
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

    assert result["completed"] is True
    assert result["execution_applied"] is True
    assert result["execution_kind"] == "buy_rations_from_bran"

    row = result["row"]

    assert row["state_delta"]["currency_delta"] == {"copper": -4}
    assert row["state_delta"]["inventory_delta"]["items_added"] == [
        {
            "id": "item:rations",
            "name": "Rations",
            "quantity": 2,
            "type": "consumable",
        }
    ]

    assert row["result"]["purchase_result"]["ok"] is True
    assert row["result"]["purchase_result"]["merchant_id"] == "npc:bran"

    assert row["direct_graph_execution_applied"] is True
    assert row["direct_graph_execution_kind"] == "buy_rations_from_bran"
    assert row["direct_graph_display_override"] is True

    assert "rations" in row["narration"].lower()
    assert "traveler" not in row["narration"].lower()
    assert "rations" in row["npc_line"].lower()


def test_buy_rations_direct_graph_execution_is_idempotent():
    result = _direct_complete_graph_action_from_command(
        command="I buy two rations from Bran.",
        row={"turn_index": 13, "player_action": "I buy two rations from Bran."},
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

    # Simulate the real runner reapplying after dialogue repair.
    from tests.rpg.autoplay_llm_campaign import _apply_buy_rations_direct_graph_execution

    row = _apply_buy_rations_direct_graph_execution(row)

    assert row["state_delta"]["currency_delta"] == {"copper": -4}
    assert row["state_delta"]["inventory_delta"]["items_added"] == [
        {
            "id": "item:rations",
            "name": "Rations",
            "quantity": 2,
            "type": "consumable",
        }
    ]
