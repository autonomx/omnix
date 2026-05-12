from tests.rpg.autoplay_llm_campaign import (
    _build_character_inventory_progression_summary,
)


def test_character_inventory_summary_reads_mechanic_resolution_state_delta():
    transcript = [
        {
            "turn_index": 5,
            "player_action": "I buy two rations from Bran.",
            "mechanic_resolution": {
                "ok": True,
                "mechanic": "buying",
                "result": {
                    "currency_delta": {"silver": -4},
                    "inventory_delta": {
                        "items_added": [{"id": "item:rations", "quantity": 2}]
                    },
                },
                "state_delta": {
                    "currency_delta": {"silver": -4},
                    "inventory_delta": {
                        "items_added": [{"id": "item:rations", "quantity": 2}]
                    },
                },
            },
        },
        {
            "turn_index": 8,
            "player_action": "I press the attack until the bandit scouts are defeated.",
            "mechanic_resolution": {
                "ok": True,
                "mechanic": "combat_resolved",
                "result": {
                    "xp_delta": 25,
                    "inventory_delta": {
                        "items_added": [
                            {"id": "item:marked_coin", "quantity": 1},
                            {"id": "item:bandit_knife", "quantity": 1},
                        ]
                    },
                },
                "state_delta": {
                    "xp_delta": 25,
                    "inventory_delta": {
                        "items_added": [
                            {"id": "item:marked_coin", "quantity": 1},
                            {"id": "item:bandit_knife", "quantity": 1},
                        ]
                    },
                },
            },
        },
    ]

    summary = _build_character_inventory_progression_summary(transcript)

    assert summary["player"]["xp"] == 25
    assert summary["currency_delta"]["silver"] == -4

    delta_by_id = {row["id"]: row["delta"] for row in summary["inventory_delta"]}
    assert delta_by_id["item:rations"] == 2
    assert delta_by_id["item:marked_coin"] == 1
    assert delta_by_id["item:bandit_knife"] == 1