from app.rpg.session.turn_contract import build_turn_contract


def test_service_presentation_actions_are_ui_safe_commands():
    state = {
        "player_state": {
            "inventory_state": {
                "currency": {"gold": 1, "silver": 0, "copper": 0},
                "items": [],
            }
        }
    }

    contract = build_turn_contract(
        player_input="I ask Bran for a room to rent",
        action={"action_type": "service_inquiry", "target_id": "npc:Bran", "target_name": "Bran"},
        resolved_action={"ok": True, "outcome": "success", "action_type": "service_inquiry"},
        simulation_state_before=state,
        simulation_state_after=state,
        runtime_state={},
    )

    actions = contract["presentation"]["available_actions"]

    assert actions
    assert actions[0]["action_id"].startswith("service:purchase:")
    assert actions[0]["command"] == "I buy Common room cot from Bran"
    assert actions[0]["label"] == "Common room cot — 5 silver"
    assert actions[0]["provider_id"] == "npc:Bran"
    assert actions[0]["offer_id"] == "bran_lodging_common_cot"
