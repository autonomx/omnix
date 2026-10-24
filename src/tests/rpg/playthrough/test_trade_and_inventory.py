"""Playthrough: trade, the pack, equipment, and a night at the inn (RQ-0.3)."""
from __future__ import annotations

import pytest

from tests.rpg.playthrough.campaigns import POSTGRES, in_worlds

pytestmark = POSTGRES

NO_WORLD_MODEL = ("RQ-2.0: a lore-only world (Vesper-9) launches with an empty world model: no places, people, "
                  "offers or routes are derived from its topics")
STARTER_TRAVEL = ("RQ-2.8: the starter town names its tavern three ways (loc_tavern, rusty_flagon_tavern, "
                  "location:rusty_flagon_tavern) and its travel graph knows only the last, so no route leaves the "
                  "tavern (and the travel turn is not counted)")
STARTER_TRADE = ("RQ-2.3: the starter town buys from its fallback merchant wherever the hero is: buying a potion "
                 "from an absent Elara charges the sheet's purse, delivers nothing, and leaves the simulation's "
                 "inventory purse at the old amount")

# Where each world's shop is, what it sells, and what the hero carries to drop.
SHOP = {
    "aurelia": {"route": ["go to Starfall Village"], "merchant": "Brindle Gearwing", "ware": "Healing Potion",
                "price": 30, "buys_back": 15, "elsewhere": "go to Wayfarers' Guild", "back": "go to Starfall Village",
                "food": "Lantern Bread"},
    "starter": {"route": ["go to the market"], "merchant": "Elara", "ware": "Healing Potion", "price": 100,
                "buys_back": 50, "elsewhere": "go outside", "back": "go back inside", "food": "Torch"},
    "vesper": {"route": [], "merchant": "a vendor", "ware": "Stim Patch", "price": 10, "buys_back": 5,
               "elsewhere": "go to Tidebreak Docks", "back": "go to Black Rain Station", "food": "Iron Dagger"},
}


@pytest.mark.parametrize("world", in_worlds(vesper=NO_WORLD_MODEL, starter=STARTER_TRADE))
def test_trade_round_trip_keeps_the_purse_exact(launch, world) -> None:
    play, shop = launch(world), SHOP[world]
    for step in shop["route"]:
        play.turn(step)
    purse = play.purse()

    play.turn(f"I buy a {shop['ware']} from {shop['merchant']}.")
    assert play.inventory().get(shop["ware"]) == 1
    assert play.purse() == purse - shop["price"]
    assert len(set(play.purses().values())) == 1, play.purses()  # every copy of the purse agrees

    play.turn(f"I sell my {shop['ware']} to {shop['merchant']}.")
    assert shop["ware"] not in play.inventory()
    assert play.purse() == purse - shop["price"] + shop["buys_back"]  # half the shop's price
    assert len(set(play.purses().values())) == 1, play.purses()

    play.turn("look around")  # a later turn keeps both
    assert shop["ware"] not in play.inventory()
    assert play.purse() == purse - shop["price"] + shop["buys_back"]


@pytest.mark.parametrize("world", in_worlds(vesper=NO_WORLD_MODEL, starter=STARTER_TRAVEL))
def test_inventory_round_trip_drop_leave_return_pick_up(launch, world) -> None:
    play, shop = launch(world), SHOP[world]
    for step in shop["route"]:
        play.turn(step)
    here, carried = play.location(), play.inventory()[shop["food"]]

    play.turn(f"I drop one {shop['food']} on the ground.")
    assert play.inventory().get(shop["food"], 0) == carried - 1
    play.turn(shop["elsewhere"])
    assert play.location() != here
    play.turn(f"I pick up the {shop['food']}.")  # it lies where it was dropped, not here
    assert play.inventory().get(shop["food"], 0) == carried - 1
    play.turn(shop["back"])
    assert play.location() == here
    play.turn(f"I pick up the {shop['food']}.")
    assert play.inventory()[shop["food"]] == carried  # back in its own stack
    assert [item["name"] for item in play.public()["player"]["inventory"]].count(shop["food"]) == 1


@pytest.mark.parametrize("world", in_worlds())
def test_equip_through_loadout_survives_story_turns(launch, world) -> None:
    play = launch(world)
    play.turn("look around")
    response = play.loadout("equip", "Iron Dagger")
    assert response.status_code == 200, response.text[:300]
    assert "Iron Dagger" in play.facts()["equipment"]
    play.turn("wait")
    assert "Iron Dagger" in play.facts()["equipment"]
    assert play.inventory()["Iron Dagger"] == 1  # equipping keeps one dagger, not two or none
    play.turn("look around")
    assert "Iron Dagger" in play.facts()["equipment"] and play.inventory()["Iron Dagger"] == 1


INN = {
    "aurelia": {"route": ["go to Starfall Village"], "keeper": "Orik Stonewake", "room": 50, "meal": 8},
    "starter": {"route": [], "keeper": "Bran", "room": 50, "meal": 15},
    "vesper": {"route": [], "keeper": "the bartender", "room": 10, "meal": 5},
}


@pytest.mark.parametrize("world", in_worlds(vesper=NO_WORLD_MODEL, starter=(
    "RQ-2.3: the starter town's innkeeper sells no meal asked for by name: 'I buy a meal from Bran' charges "
    "nothing and eases no hunger")))
def test_lodging_and_needs_over_a_night(launch, world) -> None:
    play, inn = launch(world), INN[world]
    for step in inn["route"]:
        play.turn(step)
    for _ in range(3):
        play.turn("wait")
    needs, purse = play.survival(), play.purse()
    assert needs["hunger"] > 0 and needs["fatigue"] > 0 and needs["thirst"] > 0  # needs rise with time

    play.turn(f"I buy a meal from {inn['keeper']}.")
    assert play.purse() == purse - inn["meal"]
    assert play.survival()["hunger"] < needs["hunger"]

    play.turn(f"I rent a room for the night from {inn['keeper']}.")
    assert play.purse() == purse - inn["meal"] - inn["room"]
    assert play.survival()["fatigue"] >= needs["fatigue"]  # paying for a room rests no one

    play.turn("I go to my room and sleep for the night.")
    rested = play.survival()
    assert rested["fatigue"] < needs["fatigue"]
    assert play.purse() == purse - inn["meal"] - inn["room"]  # the night was paid for


@pytest.mark.parametrize("world", in_worlds("aurelia"))
def test_a_second_night_of_lodging_is_used(launch, world) -> None:
    play, inn = launch(world), INN[world]
    for step in inn["route"]:
        play.turn(step)
    for night in range(2):
        play.turn(f"I rent a room for the night from {inn['keeper']}.")
        play.turn("I go to my room and sleep for the night.")
        services = play.simulation().get("active_services") or []
        assert [service.get("status") for service in services] == ["consumed"] * (night + 1), services
