from tests.rpg.autoplay_llm_campaign import (
    _build_character_inventory_progression_summary,
    _direct_complete_graph_action_from_command,
)


def test_character_inventory_progression_reads_buy_rations_row_state_delta():
    result = _direct_complete_graph_action_from_command(
        command="I buy two rations from Bran.",
        row={
            "turn_index": 13,
            "player_action": "I buy two rations from Bran.",
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

    row = result["row"]

    progression = _build_character_inventory_progression_summary(
        [row],
        initial_state={
            "name": "The Player",
            "currency": {"gold": 15, "silver": 20, "copper": 50},
            "inventory": [],
            "xp": 0,
            "level": 1,
        },
    )

    assert progression["currency_delta"]["copper"] == -4
    assert progression["ending_currency"]["copper"] == 46

    assert progression["currency_events"]
    assert progression["currency_events"][0]["delta"] == {"copper": -4}

    assert progression["inventory_events"]

    assert any(
        item["id"] == "item:rations" and int(item.get("quantity") or 0) == 2
        for item in progression["ending_inventory"]
    )

    assert any(
        item["id"] == "item:rations" and item["delta"] == 2
        for item in progression["inventory_delta"]
    )
