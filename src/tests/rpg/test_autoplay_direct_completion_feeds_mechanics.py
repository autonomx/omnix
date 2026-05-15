from tests.rpg.autoplay_llm_campaign import (
    _direct_complete_graph_action_from_command,
    _infer_mechanics_from_graph_action,
)


def test_buy_rations_direct_completion_feeds_mechanics():
    completed_action_ids = set()
    completed_mechanics = set()

    result = _direct_complete_graph_action_from_command(
        command="I buy two rations from Bran.",
        row={"turn_index": 14},
        all_graph_actions=[
            {
                "action_id": "buy_rations_from_bran",
                "command": "I buy two rations from Bran.",
                "mechanic": "buying",
                "mechanics": ["buying", "inventory_change", "currency_change"],
                "action_terms": ["buy", "rations", "bran"],
            }
        ],
        completed_action_ids=completed_action_ids,
        completed_mechanics=completed_mechanics,
    )

    assert result["completed"] is True
    assert "buying" in result["mechanics"]
    assert "inventory_change" in result["mechanics"]
    assert "currency_change" in result["mechanics"]
    assert "buying" in completed_mechanics

    row = result["row"]
    assert "buying" in row["mechanics_covered_this_turn"]
    assert "inventory_change" in row["mechanics_covered_this_turn"]
    assert "currency_change" in row["mechanics_covered_this_turn"]


def test_infer_combat_mechanics_from_bandit_action():
    mechanics = _infer_mechanics_from_graph_action(
        {
            "action_id": "protect_wagon_or_lure_bandits",
            "command": "I protect the wagon and lure the bandits into an ambush.",
            "action_terms": ["protect", "wagon", "bandit", "ambush"],
        },
        "I protect the wagon and lure the bandits into an ambush.",
    )

    assert "combat_started" in mechanics
    assert "combat_resolved" in mechanics
    assert "xp_gain" in mechanics