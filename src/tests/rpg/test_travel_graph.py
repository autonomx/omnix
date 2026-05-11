from app.rpg.world.travel_graph import (
    apply_travel_result_to_state,
    build_default_travel_graph,
    build_travel_state_delta,
    list_available_routes,
    resolve_travel_destination,
)


def test_default_graph_lists_routes_from_tavern():
    graph = build_default_travel_graph()
    routes = list_available_routes(
        state={"current_location": "location:rusty_flagon_tavern"},
        graph=graph,
    )

    assert routes
    assert any(route["to_location"] == "location:village_square" for route in routes)


def test_resolve_travel_to_square_from_tavern():
    graph = build_default_travel_graph()
    result = resolve_travel_destination(
        player_input="I step outside to the village square",
        state={"current_location": "location:rusty_flagon_tavern"},
        graph=graph,
    )

    assert result["ok"] is True
    assert result["from_location"] == "location:rusty_flagon_tavern"
    assert result["to_location"] == "location:village_square"


def test_apply_travel_updates_location_and_visited():
    result = resolve_travel_destination(
        player_input="go outside",
        state={"current_location": "location:rusty_flagon_tavern", "tick": 5},
    )
    state = apply_travel_result_to_state(
        state={"current_location": "location:rusty_flagon_tavern", "tick": 5},
        travel_result=result,
    )

    assert state["current_location"] == "location:village_square"
    assert "location:rusty_flagon_tavern" in state["visited_locations"]
    assert "location:village_square" in state["visited_locations"]
    assert state["tick"] > 5


def test_travel_state_delta_marks_meaningful_progress():
    result = resolve_travel_destination(
        player_input="go outside",
        state={"current_location": "location:rusty_flagon_tavern"},
    )
    delta = build_travel_state_delta(result)

    assert delta["location_changed"] is True
    assert delta["to_location"] == "location:village_square"


def test_unknown_destination_returns_available_routes():
    result = resolve_travel_destination(
        player_input="travel xyzabc",
        state={"current_location": "location:rusty_flagon_tavern"},
    )

    assert result["ok"] is False
    assert result["reason"] == "unknown_or_unreachable_destination"
    assert result["available_routes"]