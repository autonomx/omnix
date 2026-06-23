from app.rpg.session.runtime import derive_action_candidates


def test_named_prior_service_offer_selection_never_becomes_world_pickup() -> None:
    candidates = derive_action_candidates(
        {},
        "ill take dried rations",
        runtime_state={
            "last_turn_contract": {
                "service_result": {
                    "matched": True,
                    "service_kind": "meal",
                    "provider_id": "npc:Bran",
                    "provider_name": "Bran",
                    "offers": [
                        {
                            "offer_id": "bran_dried_rations",
                            "label": "Dried rations",
                        }
                    ],
                }
            }
        },
    )

    assert candidates == [
        {
            "action_type": "service_purchase",
            "priority": 11,
            "target_id": "npc:Bran",
            "target_name": "Bran",
            "service_kind": "meal",
            "confidence": 0.98,
            "source": "deterministic_prior_service_offer_selection",
        }
    ]
