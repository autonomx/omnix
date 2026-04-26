from app.rpg.session.travel_runtime import resolve_travel_turn


def test_travel_to_market_mutates_location():
    state = {
        "location_id": "loc_tavern",
        "player_state": {"location_id": "loc_tavern"},
    }

    result = resolve_travel_turn(
        player_input="I follow Bran's directions to the market",
        simulation_state=state,
        tick=7,
    )

    assert result["matched"] is True
    assert result["applied"] is True
    assert result["from_location_id"] == "loc_tavern"
    assert result["to_location_id"] == "loc_market"
    assert state["location_id"] == "loc_market"
    assert state["present_npcs"][0]["name"] == "Elara"
    assert state["world_event_state"]["events"][0]["kind"] == "travel"


def test_unavailable_travel_destination_does_not_mutate_location():
    state = {
        "location_id": "loc_tavern",
        "player_state": {"location_id": "loc_tavern"},
    }
    result = resolve_travel_turn(player_input="I go to the moon", simulation_state=state, tick=1)

    assert result["matched"] is False or result["applied"] is False
    assert state["location_id"] == "loc_tavern"


def test_asking_for_directions_to_market_does_not_travel():
    state = {
        "location_id": "loc_tavern",
        "player_state": {"location_id": "loc_tavern"},
    }

    result = resolve_travel_turn(
        player_input="I ask Bran for directions to the market",
        simulation_state=state,
        tick=7,
    )

    assert result["matched"] is False
    assert state["location_id"] == "loc_tavern"


def test_how_do_i_get_to_market_does_not_travel():
    state = {
        "location_id": "loc_tavern",
        "player_state": {"location_id": "loc_tavern"},
    }

    result = resolve_travel_turn(
        player_input="How do I get to the market?",
        simulation_state=state,
        tick=7,
    )

    assert result["matched"] is False
    assert state["location_id"] == "loc_tavern"


def test_following_directions_to_market_travels():
    state = {
        "location_id": "loc_tavern",
        "player_state": {"location_id": "loc_tavern"},
    }

    result = resolve_travel_turn(
        player_input="I follow Bran's directions to the market",
        simulation_state=state,
        tick=8,
    )

    assert result["matched"] is True
    assert result["applied"] is True
    assert result["to_location_id"] == "loc_market"
    assert state["location_id"] == "loc_market"
