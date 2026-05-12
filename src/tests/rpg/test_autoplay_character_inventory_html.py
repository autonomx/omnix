from tests.rpg.autoplay_llm_campaign import _build_minimal_autoplay_html_report


def test_html_report_uses_character_inventory_progression():
    summary = {
        "character_inventory_progression": {
            "player": {
                "name": "The Player",
                "level": 1,
                "xp": 25,
                "xp_to_next_level": 100,
                "progress_log_entries": 5,
            },
            "starting_currency": {"gold": 15, "silver": 8},
            "ending_currency": {"gold": 15, "silver": -9},
            "currency_delta": {"silver": -17},
            "starting_inventory": [
                {
                    "id": "item:trail_rations",
                    "name": "Trail Rations",
                    "quantity": 3,
                    "type": "consumable",
                    "description": "Basic food.",
                }
            ],
            "ending_inventory": [
                {
                    "id": "item:trail_rations",
                    "name": "Trail Rations",
                    "quantity": 3,
                    "type": "consumable",
                    "description": "Basic food.",
                },
                {
                    "id": "item:rations",
                    "name": "Rations",
                    "quantity": 6,
                    "type": "consumable",
                    "description": "",
                },
                {
                    "id": "item:marked_coin",
                    "name": "Marked Coin",
                    "quantity": 1,
                    "type": "quest",
                    "description": "",
                },
            ],
            "inventory_delta": [
                {
                    "id": "item:rations",
                    "name": "Rations",
                    "starting_quantity": 0,
                    "ending_quantity": 6,
                    "delta": 6,
                }
            ],
            "xp_events": [
                {
                    "turn": 8,
                    "xp_delta": 25,
                    "xp_total": 25,
                }
            ],
            "level_events": [],
        }
    }

    html = _build_minimal_autoplay_html_report(summary)

    assert "25 / 100" in html
    assert "Currency Delta" in html
    assert "Inventory Delta" in html
    assert "Rations" in html
    assert "Marked Coin" in html