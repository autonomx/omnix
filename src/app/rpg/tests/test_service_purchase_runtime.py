from app.rpg.economy.service_effects import apply_service_purchase_result
from app.rpg.economy.service_resolver import resolve_service_turn
from app.rpg.session.runtime import _service_action_from_result, _service_authoritative_result


def _state(currency=None):
    return {
        "tick": 12,
        "player_state": {
            "inventory_state": {
                "items": [],
                "equipment": {},
                "capacity": 50,
                "currency": currency or {"gold": 0, "silver": 5, "copper": 0},
                "last_loot": [],
            }
        },
        "memory_state": {"rumors": []},
        "active_rumors": [],
    }


def test_apply_service_purchase_deducts_currency_for_lodging_and_adds_active_service():
    simulation_state = _state({"gold": 0, "silver": 5, "copper": 0})
    service_result = resolve_service_turn(
        player_input="I buy Common room cot from Bran",
        action={},
        resolved_action={},
        simulation_state=simulation_state,
        runtime_state={},
    )

    applied = apply_service_purchase_result(simulation_state, service_result, tick=12)

    assert applied["applied"] is True
    assert applied["blocked"] is False
    assert applied["currency_before"] == {"gold": 0, "silver": 5, "copper": 0}
    assert applied["currency_after"] == {"gold": 0, "silver": 0, "copper": 0}
    assert applied["service_result"]["status"] == "purchased"
    assert applied["service_result"]["purchase"]["applied"] is True
    assert applied["simulation_state"]["player_state"]["inventory_state"]["currency"] == {
        "gold": 0,
        "silver": 0,
        "copper": 0,
    }
    assert applied["simulation_state"]["active_services"][0]["service_kind"] == "lodging"
    assert applied["simulation_state"]["active_services"][0]["offer_id"] == "bran_lodging_common_cot"


def test_apply_service_purchase_adds_shop_item():
    simulation_state = _state({"gold": 0, "silver": 2, "copper": 0})
    service_result = resolve_service_turn(
        player_input="I buy a torch from Elara",
        action={},
        resolved_action={},
        simulation_state=simulation_state,
        runtime_state={},
    )

    applied = apply_service_purchase_result(simulation_state, service_result, tick=12)

    assert applied["applied"] is True
    assert applied["currency_before"] == {"gold": 0, "silver": 2, "copper": 0}
    assert applied["currency_after"] == {"gold": 0, "silver": 1, "copper": 0}

    inventory = applied["simulation_state"]["player_state"]["inventory_state"]
    assert inventory["currency"] == {"gold": 0, "silver": 1, "copper": 0}
    assert inventory["items"] == [
        {
            "item_id": "torch",
            "name": "Torch",
            "quantity": 1,
        }
    ]
    assert inventory["last_loot"] == [
        {
            "item_id": "torch",
            "name": "Torch",
            "quantity": 1,
        }
    ]


def test_apply_service_purchase_blocks_without_mutation_when_insufficient_funds():
    simulation_state = _state({"gold": 0, "silver": 1, "copper": 0})
    service_result = resolve_service_turn(
        player_input="I buy rope from Elara",
        action={},
        resolved_action={},
        simulation_state=simulation_state,
        runtime_state={},
    )

    applied = apply_service_purchase_result(simulation_state, service_result, tick=12)

    assert applied["applied"] is False
    assert applied["blocked"] is True
    assert applied["blocked_reason"] == "insufficient_funds"
    assert applied["currency_before"] == {"gold": 0, "silver": 1, "copper": 0}
    assert applied["currency_after"] == {"gold": 0, "silver": 1, "copper": 0}
    assert applied["simulation_state"]["player_state"]["inventory_state"]["currency"] == {
        "gold": 0,
        "silver": 1,
        "copper": 0,
    }
    assert applied["simulation_state"]["player_state"]["inventory_state"]["items"] == []


def test_apply_service_purchase_adds_paid_information_stub():
    simulation_state = _state({"gold": 0, "silver": 2, "copper": 0})
    service_result = resolve_service_turn(
        player_input="I buy Local rumor from Bran",
        action={},
        resolved_action={},
        simulation_state=simulation_state,
        runtime_state={},
    )

    applied = apply_service_purchase_result(simulation_state, service_result, tick=12)

    assert applied["applied"] is True
    assert applied["currency_after"] == {"gold": 0, "silver": 0, "copper": 0}
    assert applied["rumor_added"]["status"] == "purchased_pending_generation"
    assert applied["simulation_state"]["memory_state"]["rumors"][0]["source_provider_id"] == "npc:Bran"


def test_service_authoritative_result_applies_purchase_runtime_effects():
    simulation_state = _state({"gold": 0, "silver": 2, "copper": 0})
    service_result = resolve_service_turn(
        player_input="I buy a torch from Elara",
        action={},
        resolved_action={},
        simulation_state=simulation_state,
        runtime_state={},
    )
    action = _service_action_from_result(
        "I buy a torch from Elara",
        {},
        service_result,
    )

    authoritative = _service_authoritative_result(simulation_state, action)
    result = authoritative["result"]

    assert result["ok"] is True
    assert result["action_type"] == "service_purchase"
    assert result["service_result"]["status"] == "purchased"
    assert result["service_result"]["purchase"]["applied"] is True
    assert result["purchase_applied"] is True
    assert authoritative["simulation_state"]["player_state"]["inventory_state"]["currency"] == {
        "gold": 0,
        "silver": 1,
        "copper": 0,
    }
    assert authoritative["simulation_state"]["player_state"]["inventory_state"]["items"][0]["item_id"] == "torch"


def test_service_authoritative_result_blocks_purchase_runtime_effects():
    simulation_state = _state({"gold": 0, "silver": 1, "copper": 0})
    service_result = resolve_service_turn(
        player_input="I buy rope from Elara",
        action={},
        resolved_action={},
        simulation_state=simulation_state,
        runtime_state={},
    )
    action = _service_action_from_result(
        "I buy rope from Elara",
        {},
        service_result,
    )

    authoritative = _service_authoritative_result(simulation_state, action)
    result = authoritative["result"]

    assert result["ok"] is False
    assert result["outcome"] == "blocked"
    assert result["blocked_reason"] == "insufficient_funds"
    assert result["service_result"]["status"] == "blocked"
    assert result["purchase_applied"] is False
    assert authoritative["simulation_state"]["player_state"]["inventory_state"]["currency"] == {
        "gold": 0,
        "silver": 1,
        "copper": 0,
    }
    assert authoritative["simulation_state"]["player_state"]["inventory_state"]["items"] == []