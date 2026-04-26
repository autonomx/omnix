from app.rpg.economy.service_resolver import resolve_service_turn
from app.rpg.world.location_registry import set_current_location


def _base_state(location_id: str):
    state = {
        "player_state": {
            "inventory_state": {
                "currency": {"gold": 0, "silver": 5, "copper": 0},
                "items": [],
                "equipment": {},
                "last_loot": [],
            }
        }
    }
    set_current_location(state, location_id)
    return state


def test_elara_shop_goods_not_available_in_tavern():
    state = _base_state("loc_tavern")
    result = resolve_service_turn(
        player_input="I ask Elara what she sells",
        action={},
        resolved_action={},
        simulation_state=state,
        runtime_state={},
    )

    assert not result.get("matched") or result.get("provider_name") != "Elara"


def test_elara_shop_goods_available_in_market():
    state = _base_state("loc_market")
    result = resolve_service_turn(
        player_input="I ask Elara what she sells",
        action={},
        resolved_action={},
        simulation_state=state,
        runtime_state={},
    )

    assert result.get("matched") is True
    assert result.get("provider_name") == "Elara"
    assert result.get("service_kind") == "shop_goods"


def test_bran_lodging_not_available_in_market():
    state = _base_state("loc_market")
    result = resolve_service_turn(
        player_input="I ask Bran for a room to rent",
        action={},
        resolved_action={},
        simulation_state=state,
        runtime_state={},
    )

    assert not result.get("matched") or result.get("provider_name") != "Bran"


def test_wait_and_listen_to_room_does_not_resolve_lodging_service():
    state = _base_state("loc_tavern")
    result = resolve_service_turn(
        player_input="I wait and listen to the room",
        action={},
        resolved_action={},
        simulation_state=state,
        runtime_state={},
    )

    assert result.get("matched") is False
    assert result.get("status") == "not_service"
    assert result.get("reason") in {
        "ambient_wait_or_listen",
        "ambient_room_context_not_lodging",
    }
