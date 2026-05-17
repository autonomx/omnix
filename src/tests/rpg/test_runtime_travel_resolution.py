from app.rpg.world.travel_graph import (
    apply_travel_result_to_state,
    resolve_travel_destination,
)


def test_runtime_travel_turn_changes_location():
    # Focused unit test against travel resolver
    result = resolve_travel_destination(
        player_input="I step outside to the village square",
        state={"current_location": "location:rusty_flagon_tavern"},
    )

    assert result.get("ok") is True
    assert result.get("to_location") == "location:village_square"

    state = apply_travel_result_to_state(
        state={"current_location": "location:rusty_flagon_tavern", "tick": 5},
        travel_result=result,
    )

    assert state["current_location"] == "location:village_square"
    assert state["tick"] > 5


def test_runtime_travel_failure_provides_routes():
    result = resolve_travel_destination(
        player_input="travel to the moon tower",
        state={"current_location": "location:rusty_flagon_tavern"},
    )

    assert result.get("ok") is False
    assert result.get("reason") == "unknown_or_unreachable_destination"
    assert result.get("available_routes")