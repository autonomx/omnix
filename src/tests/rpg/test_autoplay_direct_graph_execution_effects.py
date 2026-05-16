from tests.rpg.autoplay_llm_campaign import (
    _build_character_inventory_progression_summary,
    _direct_complete_graph_action_from_command,
)


def test_buy_rations_direct_graph_completion_mutates_inventory_currency_and_display():
    result = _direct_complete_graph_action_from_command(
        command="I buy two rations from Bran.",
        row={"turn_index": 14, "player_action": "I buy two rations from Bran."},
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
        mechanics_state={
            "currency": {"gold": 15, "silver": 20, "copper": 50},
            "inventory": [],
            "xp": 0,
            "level": 1,
            "flags": {},
        },
    )

    assert result["completed"] is True
    assert result["execution_delta_applied"] is True

    row = result["row"]

    assert row["state_delta"]["currency_delta"] == {"copper": -4}
    assert row["state_delta"]["inventory_delta"]["items_added"][0]["id"] == "item:rations"
    assert row["state_delta"]["inventory_delta"]["items_added"][0]["quantity"] == 2

    assert row["result"]["purchase_result"]["ok"] is True
    assert row["selected_narration"]["source"] == "direct_graph_execution_display"
    assert "rations" in row["selected_narration"]["narration"].lower()
    assert row["npc"]["speaker"] == "Bran"
    assert "rations" in row["npc"]["line"].lower()


def test_direct_graph_buy_appears_in_character_inventory_progression():
    row = _direct_complete_graph_action_from_command(
        command="I buy two rations from Bran.",
        row={"turn_index": 1, "player_action": "I buy two rations from Bran."},
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
    )["row"]

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
    assert any(
        item["id"] == "item:rations" and item["delta"] == 2
        for item in progression["inventory_delta"]
    )


def test_combat_direct_graph_completion_grants_xp_delta():
    result = _direct_complete_graph_action_from_command(
        command="I protect the wagon and fight the bandits.",
        row={"turn_index": 20, "player_action": "I protect the wagon and fight the bandits."},
        all_graph_actions=[
            {
                "action_id": "protect_wagon_or_lure_bandits",
                "command": "I protect the wagon and fight the bandits.",
                "mechanic": "combat_started",
                "mechanics": ["combat_started", "combat_resolved", "xp_gain"],
                "action_terms": ["protect", "wagon", "fight", "bandits"],
            }
        ],
        completed_action_ids=set(),
        completed_mechanics=set(),
    )

    row = result["row"]

    assert row["state_delta"]["xp_delta"] == 5
    assert row["result"]["combat_result"]["ok"] is True
    assert row["selected_narration"]["reward"]["xp_delta"] == 5
