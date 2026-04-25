from app.rpg.session.turn_contract import build_turn_contract


def _state_with_currency(currency=None):
    return {
        "player_state": {
            "inventory_state": {
                "currency": currency or {"gold": 1, "silver": 0, "copper": 0}
            }
        },
        "actor_states": [
            {
                "id": "npc:Bran",
                "name": "Bran",
            },
            {
                "id": "npc:Elara",
                "name": "Elara",
            },
        ],
    }


def test_turn_contract_attaches_lodging_service_result():
    contract = build_turn_contract(
        player_input="I ask Bran for a room to rent",
        action={"action_type": "social_activity", "target_id": "npc:Bran", "target_name": "Bran"},
        resolved_action={"outcome": "success"},
        simulation_state_before=_state_with_currency(),
        simulation_state_after=_state_with_currency(),
        runtime_state={},
    )

    service_result = contract["service_result"]

    assert service_result["matched"] is True
    assert service_result["kind"] == "service_inquiry"
    assert service_result["service_kind"] == "lodging"
    assert service_result["provider_id"] == "npc:Bran"
    assert service_result["status"] == "offers_available"
    assert any(offer["offer_id"] == "bran_lodging_common_cot" for offer in service_result["offers"])
    assert contract["resolved_action"]["service_result"] == service_result
    assert contract["resolved_result"]["service_result"] == service_result
    assert contract["presentation"]["available_actions"]


def test_turn_contract_normalizes_outer_action_for_service_turns():
    contract = build_turn_contract(
        player_input="I ask Bran for a room to rent",
        action={"action_type": "use_item", "target_id": "Bran", "target_name": "Bran"},
        resolved_action={"ok": False, "reason": "unknown_item", "action_type": "use_item"},
        simulation_state_before=_state_with_currency(),
        simulation_state_after=_state_with_currency(),
        runtime_state={},
    )

    assert contract["service_result"]["matched"] is True
    assert contract["action"]["action_type"] == "service_inquiry"
    assert contract["resolved_action"]["action_type"] == "service_inquiry"
    assert contract["resolved_result"]["action_type"] == "service_inquiry"
    assert contract["resolved_action"]["service_kind"] == "lodging"
    assert contract["resolved_action"]["target_id"] == "npc:Bran"
    assert contract["resolved_action"]["target_name"] == "Bran"
    assert contract["resolved_action"].get("reason") != "unknown_item"


def test_turn_contract_has_primary_version_for_service_turns():
    contract = build_turn_contract(
        player_input="I ask Bran for a room to rent",
        action={"action_type": "service_inquiry", "target_id": "npc:Bran", "target_name": "Bran"},
        resolved_action={"ok": True, "outcome": "success", "action_type": "service_inquiry"},
        simulation_state_before=_state_with_currency(),
        simulation_state_after=_state_with_currency(),
        runtime_state={},
    )

    assert contract["version"] == "turn_contract_v1"
    assert contract["service_result"]["matched"] is True
    assert contract["presentation"]["available_actions"]
    assert contract["resolved_result"]["service_result"]["matched"] is True


def test_turn_contract_attaches_meal_service_result():
    contract = build_turn_contract(
        player_input="I ask Bran for food",
        action={"action_type": "social_activity", "target_id": "npc:Bran", "target_name": "Bran"},
        resolved_action={"outcome": "success"},
        simulation_state_before=_state_with_currency(),
        simulation_state_after=_state_with_currency(),
        runtime_state={},
    )

    service_result = contract["service_result"]

    assert service_result["matched"] is True
    assert service_result["service_kind"] == "meal"
    assert service_result["provider_id"] == "npc:Bran"
    assert any(offer["offer_id"] == "bran_meal_stew" for offer in service_result["offers"])


def test_turn_contract_attaches_paid_information_service_result():
    contract = build_turn_contract(
        player_input="I ask Bran if he has heard any rumors",
        action={"action_type": "social_activity", "target_id": "npc:Bran", "target_name": "Bran"},
        resolved_action={"outcome": "success"},
        simulation_state_before=_state_with_currency(),
        simulation_state_after=_state_with_currency(),
        runtime_state={},
    )

    service_result = contract["service_result"]

    assert service_result["matched"] is True
    assert service_result["service_kind"] == "paid_information"
    assert service_result["provider_id"] == "npc:Bran"
    assert any(offer["offer_id"] == "bran_paid_rumor" for offer in service_result["offers"])


def test_turn_contract_attaches_shop_goods_service_result():
    contract = build_turn_contract(
        player_input="I ask Elara what she sells",
        action={"action_type": "social_activity", "target_id": "npc:Elara", "target_name": "Elara"},
        resolved_action={"outcome": "success"},
        simulation_state_before=_state_with_currency(),
        simulation_state_after=_state_with_currency(),
        runtime_state={},
    )

    service_result = contract["service_result"]

    assert service_result["matched"] is True
    assert service_result["service_kind"] == "shop_goods"
    assert service_result["provider_id"] == "npc:Elara"
    assert any(offer["offer_id"] == "elara_torch" for offer in service_result["offers"])
    assert any(action["offer_id"] == "elara_torch" for action in contract["presentation"]["available_actions"])


def test_turn_contract_attaches_purchase_ready_without_mutating_state():
    before_state = _state_with_currency({"gold": 0, "silver": 2, "copper": 0})
    after_state = _state_with_currency({"gold": 0, "silver": 2, "copper": 0})

    contract = build_turn_contract(
        player_input="I buy a torch from Elara",
        action={"action_type": "social_activity", "target_id": "npc:Elara", "target_name": "Elara"},
        resolved_action={"outcome": "success"},
        simulation_state_before=before_state,
        simulation_state_after=after_state,
        runtime_state={},
    )

    service_result = contract["service_result"]

    assert service_result["matched"] is True
    assert service_result["kind"] == "service_purchase"
    assert service_result["selected_offer_id"] == "elara_torch"
    assert service_result["status"] == "purchase_ready"
    assert service_result["purchase"]["can_afford"] is True
    assert service_result["purchase"]["resource_changes"]["currency"] == {
        "gold": 0,
        "silver": -1,
        "copper": 0,
    }

    # 7.0D only attaches the deterministic contract. State mutation is 7.0F.
    assert before_state["player_state"]["inventory_state"]["currency"] == {
        "gold": 0,
        "silver": 2,
        "copper": 0,
    }
    assert after_state["player_state"]["inventory_state"]["currency"] == {
        "gold": 0,
        "silver": 2,
        "copper": 0,
    }


def test_non_service_turn_has_empty_service_result():
    contract = build_turn_contract(
        player_input="I look around the tavern",
        action={"action_type": "observe"},
        resolved_action={"outcome": "success"},
        simulation_state_before=_state_with_currency(),
        simulation_state_after=_state_with_currency(),
        runtime_state={},
    )

    assert contract["service_result"]["matched"] is False
    assert contract["presentation"]["available_actions"] == []
