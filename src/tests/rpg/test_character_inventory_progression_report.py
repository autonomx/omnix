from tests.rpg.autoplay_llm_campaign import _build_character_inventory_progression_summary


def test_character_inventory_progression_applies_currency_inventory_and_xp():
    transcript = [
        {
            "turn_index": 8,
            "result": {
                "xp_delta": 25,
                "inventory_delta": {
                    "items_added": [
                        {"id": "item:marked_coin", "quantity": 1},
                    ]
                },
            },
        },
    ]

    summary = _build_character_inventory_progression_summary(transcript)

    assert summary["player"]["xp"] == 25
    has_marked_coin = any(item["id"] == "item:marked_coin" for item in summary["inventory_delta"])
    assert has_marked_coin