from app.rpg.world.location_registry import (
    current_location_id,
    find_location_by_name,
    provider_present_at_location,
    resolve_exit_destination,
    set_current_location,
)


def test_find_location_by_alias():
    assert find_location_by_name("market")["location_id"] == "loc_market"
    assert find_location_by_name("the rusty flagon")["location_id"] == "loc_tavern"


def test_resolve_exit_destination_from_tavern_to_market():
    state = {"location_id": "loc_tavern", "player_state": {"location_id": "loc_tavern"}}
    assert resolve_exit_destination(state, "market") == "loc_market"


def test_set_current_location_updates_present_npcs():
    state = {}
    set_current_location(state, "loc_market")
    assert current_location_id(state) == "loc_market"
    assert state["present_npcs"][0]["name"] == "Elara"
    assert provider_present_at_location(state, provider_name="Elara")
    assert not provider_present_at_location(state, provider_name="Bran")
