from app.rpg.session.conversation_thread_runtime import (
    advance_conversation_threads_for_turn,
)
from app.rpg.world.location_registry import set_current_location


def _state():
    state = {}
    set_current_location(state, "loc_tavern")
    return state


def _runtime_state():
    return {
        "runtime_settings": {
            "conversation_settings": {
                "enabled": True,
                "conversation_chance_percent": 100,
                "min_ticks_between_conversations": 0,
                "thread_cooldown_ticks": 0,
            }
        }
    }


def test_conversation_does_not_trigger_during_service_turn():
    result = advance_conversation_threads_for_turn(
        player_input="I ask Bran for a room to rent",
        simulation_state=_state(),
        resolved_result={
            "action_type": "service_inquiry",
            "semantic_family": "commerce",
            "service_result": {
                "matched": True,
                "kind": "service_inquiry",
                "service_kind": "lodging",
            },
        },
        tick=1,
        runtime_state=_runtime_state(),
    )

    assert result["triggered"] is False
    assert result["reason"] == "service_turn"


def test_conversation_does_not_trigger_during_travel_turn():
    result = advance_conversation_threads_for_turn(
        player_input="I follow Bran's directions to the market",
        simulation_state=_state(),
        resolved_result={
            "action_type": "travel",
            "semantic_family": "travel",
            "travel_result": {
                "matched": True,
                "applied": True,
            },
        },
        tick=1,
        runtime_state=_runtime_state(),
    )

    assert result["triggered"] is False
    assert result["reason"] == "travel_turn"


def test_conversation_triggers_for_wait_listen_turn():
    result = advance_conversation_threads_for_turn(
        player_input="I wait and listen to the room",
        simulation_state=_state(),
        resolved_result={
            "action_type": "ambient_wait",
            "semantic_family": "ambient",
            "service_result": {
                "matched": False,
                "kind": "not_service",
                "status": "not_service",
            },
        },
        tick=1,
        runtime_state=_runtime_state(),
    )

    assert result["triggered"] is True