from tests.rpg.autoplay_llm_campaign import (
    _direct_complete_graph_action_from_command,
    _sync_direct_graph_canonical_action_display,
)


def test_explicit_combat_direct_graph_row_gets_canonical_visible_action():
    result = _direct_complete_graph_action_from_command(
        command="I check in with Garran and focus on the active wagon-road objective.",
        row={
            "turn_index": 19,
            "player_action": "I check in with Garran and focus on the active wagon-road objective.",
        },
        all_graph_actions=[
            {
                "action_id": "protect_wagon_or_lure_bandits",
                "command": "I protect the wagon and fight the bandits.",
                "mechanic": "combat_started",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "changed_parts": ["combat_started", "combat_resolved", "xp_gain"],
                "action_terms": ["protect", "wagon", "fight", "bandits"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    row = result["row"]
    row["direct_graph_action_completion"] = {
        key: value for key, value in result.items() if key != "row"
    }

    row = _sync_direct_graph_canonical_action_display(row)

    assert row["player_action"] == "I protect the wagon and fight the bandits."
    assert row["visible_player_action"] == "I protect the wagon and fight the bandits."
    assert row["direct_graph_canonical_action_synced"] is True


def test_buy_rations_keeps_canonical_buy_action():
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
    row["direct_graph_action_completion"] = {
        key: value for key, value in result.items() if key != "row"
    }

    row = _sync_direct_graph_canonical_action_display(row)

    assert row["player_action"] == "I buy two rations from Bran."
