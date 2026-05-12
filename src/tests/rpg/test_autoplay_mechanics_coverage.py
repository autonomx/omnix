from tests.rpg.autoplay_llm_campaign import _build_mechanics_coverage_summary


def test_service_inquiry_does_not_count_as_lodging_purchase():
    transcript = [
        {
            "turn_index": 1,
            "player_action": "I ask Bran about a room.",
            "turn_contract": {
                "result": {
                    "service_result": {
                        "status": "offers_available",
                        "offers": [{"offer_id": "room"}],
                        "selected_offer_id": "",
                        "purchase": None,
                    }
                }
            },
        }
    ]

    summary = _build_mechanics_coverage_summary(transcript)

    assert summary["mechanics"]["service_or_lodging"]["count"] == 0


def test_available_mechanic_counts_are_reported():
    transcript = [
        {
            "turn_index": 1,
            "available_mechanics": [
                {"mechanic": "buying"},
                {"mechanic": "party_recruitment"},
            ],
        },
        {
            "turn_index": 2,
            "available_mechanics": [
                {"mechanic": "buying"},
            ],
        },
    ]

    summary = _build_mechanics_coverage_summary(transcript)

    assert summary["available_mechanic_counts"]["buying"] == 2
    assert summary["available_mechanic_counts"]["party_recruitment"] == 1