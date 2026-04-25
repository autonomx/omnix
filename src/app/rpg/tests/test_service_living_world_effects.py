from app.rpg.economy.service_resolver import resolve_service_turn
from app.rpg.session.service_runtime import (
    service_action_from_result,
    service_authoritative_result,
)


def _state(currency=None):
    return {
        "tick": 12,
        "location_id": "loc_market",
        "present_npcs": [
            {"id": "npc:Elara", "name": "Elara"},
            {"id": "npc:Bran", "name": "Bran"},
        ],
        "player_state": {
            "location_id": "loc_market",
            "inventory_state": {
                "currency": currency or {"gold": 0, "silver": 0, "copper": 0},
                "items": [],
                "equipment": {},
                "last_loot": [],
            }
        },
    }


def _authoritative_for(player_input, state):
    service_result = resolve_service_turn(
        player_input=player_input,
        action={},
        resolved_action={},
        simulation_state=state,
        runtime_state={},
    )
    action = service_action_from_result(player_input, {}, service_result)
    return service_authoritative_result(state, action)


def test_service_inquiry_adds_memory_and_social_state_without_purchase():
    state = _state({"gold": 0, "silver": 2, "copper": 0})

    authoritative = _authoritative_for("I ask Elara what she sells", state)
    result = authoritative["result"]
    simulation_state = authoritative["simulation_state"]

    assert result["action_type"] == "service_inquiry"
    assert result["purchase_applied"] is False
    assert result["service_application"]["memory_entry"]["kind"] == "service_inquiry"
    assert (
        result["service_application"]["social_effects"]["relationship_key"]
        == "npc:Elara::player"
    )

    memory_state = simulation_state["memory_state"]
    assert memory_state["service_memories"][0]["kind"] == "service_inquiry"
    assert memory_state["npc_memories"]["npc:Elara"][0]["owner_id"] == "npc:Elara"

    relationship = simulation_state["relationship_state"]["npc:Elara::player"]
    assert relationship["axes"]["familiarity"] > 0
    assert simulation_state["npc_emotion_state"]["npc:Elara"]["dominant_emotion"]


def test_successful_service_purchase_updates_memory_social_and_stock():
    state = _state({"gold": 0, "silver": 2, "copper": 0})

    authoritative = _authoritative_for("I buy a torch from Elara", state)
    result = authoritative["result"]
    simulation_state = authoritative["simulation_state"]

    assert result["purchase_applied"] is True
    assert result["service_result"]["status"] == "purchased"
    assert result["service_application"]["memory_entry"]["kind"] == "service_purchase"
    assert (
        result["service_application"]["social_effects"]["relationship"]["axes"]["trust"]
        > 0
    )
    assert result["service_application"]["stock_update"]["offer_id"] == "elara_torch"
    assert result["service_application"]["stock_update"]["before"] == 3
    assert result["service_application"]["stock_update"]["after"] == 2

    assert (
        simulation_state["service_offer_state"]["offers"]["elara_torch"]["stock_remaining"]
        == 2
    )
    assert simulation_state["memory_state"]["service_memories"][-1]["kind"] == "service_purchase"
    assert simulation_state["relationship_state"]["npc:Elara::player"]["axes"]["familiarity"] >= 1
    assert simulation_state["npc_emotion_state"]["npc:Elara"]["valence"] > 0


def test_blocked_purchase_updates_memory_and_annoyance_but_does_not_decrement_stock():
    state = _state({"gold": 0, "silver": 1, "copper": 0})

    authoritative = _authoritative_for("I buy rope from Elara", state)
    result = authoritative["result"]
    simulation_state = authoritative["simulation_state"]

    assert result["purchase_applied"] is False
    assert result["blocked_reason"] == "insufficient_funds"
    assert result["service_application"]["memory_entry"]["kind"] == "service_purchase_blocked"
    assert result["service_application"]["stock_update"] == {}

    relationship = simulation_state["relationship_state"]["npc:Elara::player"]
    assert relationship["axes"]["annoyance"] > 0
    assert "elara_rope" not in simulation_state.get("service_offer_state", {}).get("offers", {})


def test_stock_exhaustion_removes_offer_from_available_actions():
    state = _state({"gold": 0, "silver": 5, "copper": 0})
    state["service_offer_state"] = {
        "offers": {
            "elara_torch": {
                "stock_remaining": 0,
                "stock_initial": 1,
            }
        }
    }

    result = resolve_service_turn(
        player_input="I ask Elara what she sells",
        action={},
        resolved_action={},
        simulation_state=state,
        runtime_state={},
    )

    offer_ids = {offer["offer_id"] for offer in result["offers"]}
    action_ids = {action["offer_id"] for action in result["available_actions"]}

    assert "elara_torch" not in offer_ids
    assert "elara_torch" not in action_ids
    assert "elara_rope" in offer_ids
