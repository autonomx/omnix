"""The trade rule (RQ-2.3): buying from and selling to the people who trade where the hero stands."""
from __future__ import annotations

from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules.economy.trade import buy, coins, sell, stock_left

OFFERS = {
    "npc:orik": [
        {"offer_id": "npc:orik:night", "service_kind": "lodging", "label": "A night's lodging", "price": {"silver": 5},
         "effects": {"duration": "one_night"}, "stock": 1},
        {"offer_id": "npc:orik:meal", "service_kind": "meal", "label": "A hot meal", "price": {"copper": 8}, "effects": {}},
    ],
    "npc:brindle": [
        {"offer_id": "npc:brindle:healing-potion", "service_kind": "shop_goods", "label": "Healing Potion",
         "price": {"silver": 3}, "stock": 3,
         "effects": {"items_added": [{"item_id": "healing_potion", "name": "Healing Potion", "quantity": 1, "type": "potion"}]}},
    ],
}
PROVIDERS = {
    "npc:orik": {"provider_id": "npc:orik", "provider_name": "Orik Stonewake", "aliases": ["orik", "innkeeper"],
                 "location_id": "loc:village", "service_kinds": ["lodging", "meal"]},
    "npc:brindle": {"provider_id": "npc:brindle", "provider_name": "Brindle Gearwing", "aliases": ["brindle"],
                    "location_id": "loc:village", "service_kinds": ["shop_goods"], "buys": {"price_fraction": 0.5}},
}


def _campaign(purse=100, items=(), here="loc:village", quests=()):
    currency = {"gold": purse // 100, "silver": purse // 10 % 10, "copper": purse % 10}
    return {"manifest": {}, "state": {"player": {}}, "simulation_state": {
        "tick": 4,
        "world_model": {"offers": OFFERS, "providers": PROVIDERS},
        "present_npc_state": {"present_npc_ids": ["npc:orik", "npc:brindle"]},
        "player_state": {"location_id": here, "currency": dict(currency),
                         "inventory_state": {"currency": dict(currency), "items": [dict(item) for item in items]}},
        "survival": {"hunger": 50, "thirst": 10, "fatigue": 0},
        "quest_state": {"quests": [dict(quest) for quest in quests]},
    }}


def _after(campaign, outcome):
    document, _ = reduce(campaign, outcome.changes)
    return document["simulation_state"]


def test_buying_pays_takes_the_goods_and_the_stock_and_is_remembered() -> None:
    campaign = _campaign()
    outcome = buy(campaign["simulation_state"], "I buy a Healing Potion from Brindle Gearwing.")
    assert outcome.kind == "bought"
    assert outcome.lines == ["You pay 3 silver to Brindle Gearwing for Healing Potion. The transaction is complete."]
    after = _after(campaign, outcome)
    assert after["player_state"]["currency"] == {"gold": 0, "silver": 7, "copper": 0}
    assert [item["item_id"] for item in after["player_state"]["inventory_state"]["items"]] == ["healing_potion"]
    assert after["trade"]["stock"]["npc:brindle:healing-potion"] == {"remaining": 2, "day": 0}
    assert after["trade"]["ledger"][-1] == {"provider_id": "npc:brindle", "provider_name": "Brindle Gearwing",
                                           "deal": "bought", "what": "Healing Potion", "copper": 30, "tick": 4}


def test_a_meal_eases_hunger_and_a_room_is_kept_for_the_night() -> None:
    campaign = _campaign()
    meal = buy(campaign["simulation_state"], "I buy a meal from Orik Stonewake.")
    assert meal.lines[-1] == "It eases your hunger." and _after(campaign, meal)["survival"]["hunger"] == 15
    room = buy(campaign["simulation_state"], "I rent a room for the night from Orik.")
    [reserved] = _after(campaign, room)["active_services"]
    assert reserved["offer_id"] == "npc:orik:night" and reserved["status"] == "active"
    assert reserved["effects"]["duration"] == "one_night"


def test_what_cannot_be_bought_is_refused_and_an_unnamed_purchase_lists_the_offers() -> None:
    simulation = _campaign(purse=20)["simulation_state"]
    assert buy(simulation, "I buy a Healing Potion from Brindle.").lines == [
        "You cannot afford Healing Potion: it costs 3 silver and you have 2 silver."]
    listed = buy(simulation, "I buy supplies from Brindle Gearwing.")
    assert listed.kind == "listed" and listed.changes == []
    assert listed.lines == ["Brindle Gearwing offers: Healing Potion (3 silver). Nothing is sold until you name one."]
    assert buy(_campaign(here="loc:grove")["simulation_state"], "I buy a healing potion.").lines == ["No one here sells that."]
    sold_out = _campaign()
    sold_out["simulation_state"]["trade"] = {"stock": {"npc:orik:night": 0}}
    assert buy(sold_out["simulation_state"], "I rent a room from Orik.").lines == ["A night's lodging is sold out."]
    assert buy({"world_model": {}}, "buy bread") is None  # no economy section: the older path's


def test_what_sold_out_comes_back_with_the_days() -> None:
    campaign = _campaign()
    simulation = campaign["simulation_state"]
    simulation["trade"] = {"stock": {"npc:orik:night": {"remaining": 0, "day": 0}}}
    simulation["environment"] = {"absolute_minutes": 23 * 60}
    assert buy(simulation, "I rent a room from Orik.").lines == ["A night's lodging is sold out."]  # the same day
    simulation["environment"] = {"absolute_minutes": 25 * 60}  # the next: the inn's rooms are free again
    assert buy(simulation, "I rent a room from Orik.").kind == "bought"
    offer = next(row for row in simulation["world_model"]["offers"]["npc:brindle"] if row["offer_id"].endswith("potion"))
    offer["restock_per_day"] = 1  # as the world wrote it: one a day
    simulation["trade"]["stock"]["npc:brindle:healing-potion"] = {"remaining": 0, "day": 0}
    assert stock_left(simulation, offer) == 1
    offer["restock_per_day"] = 0  # never
    assert stock_left(simulation, offer) == 0


def test_selling_pays_half_for_the_shops_own_goods_a_token_for_others_and_nothing_for_quest_rewards() -> None:
    items = [{"item_id": "healing_potion", "name": "Healing Potion", "qty": 2},
             {"item_id": "iron_dagger", "name": "Iron Dagger", "qty": 1},
             {"item_id": "item:sigil", "name": "Wayfarer Sigil", "qty": 1}]
    campaign = _campaign(purse=0, items=items, quests=[{"id": "q", "rewards": ["item:sigil"]}])
    simulation = campaign["simulation_state"]
    potion = sell(simulation, "I sell my Healing Potion to Brindle Gearwing.")
    assert potion.lines == ["You sell the Healing Potion to Brindle Gearwing for 1 silver, 5 copper."]
    after = _after(campaign, potion)
    assert after["player_state"]["inventory_state"]["items"][0]["qty"] == 1
    assert sell(simulation, "I sell my Iron Dagger to Brindle Gearwing.").lines == [
        "You sell the Iron Dagger to Brindle Gearwing for 5 copper."]
    assert sell(simulation, "I sell my Wayfarer Sigil to Brindle.").lines == [
        "Brindle Gearwing will not buy the Wayfarer Sigil: it was earned, not bought."]
    assert sell(simulation, "I sell my crown.").lines == ["You carry nothing by that name to sell."]


def test_coins_read_as_the_play_screen_shows_them() -> None:
    assert (coins(208), coins(5), coins(0)) == ("2 gold, 8 copper", "5 copper", "nothing")


def test_prices_answer_scarcity_the_roads_trust_and_a_haggle() -> None:
    from app.apps.rpg.rules.checks import check
    from app.apps.rpg.rules.economy.trade import price_of

    campaign = _campaign(purse=1000)
    simulation = campaign["simulation_state"]
    brindle, potion = PROVIDERS["npc:brindle"], OFFERS["npc:brindle"][0]
    assert price_of(simulation, brindle, potion) == (30, [])
    simulation["trade"] = {"stock": {"npc:brindle:healing-potion": {"remaining": 0, "day": 0}}}
    potion = {**potion, "stock": 5, "restock_per_day": 1}  # one of five back by the next day: nearly gone
    simulation["environment"] = {"absolute_minutes": 25 * 60}
    assert price_of(simulation, brindle, potion) == (38, ["it is nearly gone"])
    simulation["trade"] = {}
    simulation["world_model"]["locations"] = {"loc:village": {"region_id": "region:march"}}
    simulation["causal_world_runtime"] = {"state": {"cells": {"region:march": {"values": {"trade_access": 30}}}}}
    assert price_of(simulation, brindle, potion) == (36, ["the roads choke trade"])
    simulation["relationship_state"] = {"npc:brindle": {"trust": 60}}
    assert price_of(simulation, brindle, potion)[1] == ["the roads choke trade", "you are trusted"]

    simulation["world_model"]["npcs"] = {"npc:brindle": {"name": "Brindle Gearwing"}}
    simulation["player_state"]["stats"] = {"charisma": 30}  # a sure haggle
    haggle = check(simulation, "haggle", "npc:brindle", turn_key="1")
    assert haggle.band != "failure" and "Brindle Gearwing comes down on the price, for today." in haggle.lines
    haggled, _ = reduce(campaign, haggle.changes)
    after = haggled["simulation_state"]
    assert price_of(after, brindle, potion)[1][-1] == "you haggled"
    bought = buy(after, "I buy a Healing Potion from Brindle Gearwing.")
    assert bought.lines[0].startswith("You pay ") and "(the roads choke trade, you are trusted, you haggled)" in bought.lines[0]
    after["environment"] = {"absolute_minutes": 49 * 60}  # the next day: the haggle is spent
    assert "you haggled" not in price_of(after, brindle, potion)[1]
