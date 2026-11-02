"""Gear in the one store (RQ-2.4): wearing and wielding, the sheet's list, and the v8 gathering of the old record."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.foundation.state import reduce
from app.apps.rpg.foundation.state.changes import ItemEquipped, ItemRemoved, ItemUnequipped
from app.apps.rpg.foundation.state.gear import gather_gear
from app.apps.rpg.rules.interactions.items import equip_item, unequip_item

SWORD = {"item_id": "item:sword", "name": "Short Sword", "type": "weapon", "qty": 1}
CLOAK = {"item_id": "item:cloak", "name": "Travel Cloak", "type": "clothing", "qty": 1}
BREAD = {"item_id": "item:bread", "name": "Bread", "type": "food", "qty": 2}


def _document(equipment: dict[str, str] | None = None) -> dict[str, Any]:
    return {"state": {"player": {"equipment": []}},
            "simulation_state": {"player_state": {"inventory_state": {
                "items": [dict(SWORD), dict(CLOAK), dict(BREAD)], "equipment": dict(equipment or {})}}}}


def test_wielding_and_wearing_take_their_slots_and_the_sheet_shows_them() -> None:
    document = _document()
    simulation = document["simulation_state"]
    sword = equip_item(simulation, "item:sword")
    assert sword.changes == [ItemEquipped(slot="main_hand", item_id="item:sword")]
    assert sword.lines == ["You take up the Short Sword."]
    document, _ = reduce(document, [*sword.changes, *equip_item(simulation, "item:cloak").changes])
    assert document["simulation_state"]["player_state"]["inventory_state"]["equipment"] == {
        "main_hand": "item:sword", "cloak": "item:cloak"}
    assert document["state"]["player"]["equipment"] == [{"slot": "Weapon", "name": "Short Sword"},
                                                        {"slot": "Cloak", "name": "Travel Cloak"}]


def test_what_cannot_be_worn_is_refused_and_what_is_worn_is_already_ready() -> None:
    assert equip_item(_document()["simulation_state"], "item:bread").refused
    ready = equip_item(_document({"main_hand": "item:sword"})["simulation_state"], "item:sword")
    assert not ready.refused and ready.changes == [] and ready.lines == ["You already have the Short Sword ready."]


def test_putting_away_keeps_it_in_the_pack() -> None:
    document = _document({"main_hand": "item:sword"})
    outcome = unequip_item(document["simulation_state"], "item:sword")
    assert outcome.changes == [ItemUnequipped(slot="main_hand")]
    after, _ = reduce(document, outcome.changes)
    assert after["simulation_state"]["player_state"]["inventory_state"]["equipment"] == {}
    assert any(item["item_id"] == "item:sword" for item in after["simulation_state"]["player_state"]["inventory_state"]["items"])
    assert unequip_item(document["simulation_state"], "item:cloak").refused  # not worn


def test_gear_no_longer_carried_is_no_longer_worn() -> None:
    document, _ = reduce(_document(), [ItemEquipped(slot="main_hand", item_id="item:sword")])
    sold, _ = reduce(document, [ItemRemoved(item_id="item:sword", quantity=1)])
    assert sold["simulation_state"]["player_state"]["inventory_state"]["equipment"] == {}
    assert sold["state"]["player"]["equipment"] == []


def test_version_8_gathers_the_old_gear_record_into_the_store() -> None:
    document = {"simulation_state": {"player_state": {
        "inventory": {"items": [dict(SWORD), {"item_id": "item:coin", "name": "copper coin", "qty": 14}],
                      "equipment": {"main_hand": "item:sword", "ring": "item:gone"}},
        "inventory_state": {"items": [dict(SWORD), dict(BREAD)], "equipment": {"cloak": "item:cloak"}},
    }}}
    gathered = gather_gear(document)
    player = gathered["simulation_state"]["player_state"]
    assert "inventory" not in player and "inventory" in document["simulation_state"]["player_state"]  # a copy
    assert [item["item_id"] for item in player["inventory_state"]["items"]] == ["item:sword", "item:bread", "item:coin"]
    assert player["inventory_state"]["equipment"] == {"main_hand": "item:sword", "cloak": "item:cloak"}
    assert gather_gear(gathered) is gathered  # nothing left to gather


def test_a_tool_is_held_to_hand_and_food_is_not_worn() -> None:
    simulation = {"player_state": {"inventory_state": {"items": [
        {"item_id": "item:compass", "name": "Gateborn Compass", "type": "trinket", "qty": 1}, dict(BREAD)]}}}
    held = equip_item(simulation, "item:compass")
    assert not held.refused and [change.slot for change in held.changes] == ["tool"]
    assert equip_item(simulation, "item:bread").refused


def test_the_play_screen_offers_what_the_rules_allow_for_each_thing_carried() -> None:
    """The pack's actions are the item rules' own reading (RQ-7.7): food is eaten, a worn cloak is taken off, a sword
    not wielded is taken up; anything can be dropped or offered for sale."""
    from app.apps.rpg.edge.api.payloads.player_view import player_session_view
    from app.apps.rpg.rules.interactions.items import pack_actions

    simulation = _document({"cloak": "item:cloak"})["simulation_state"]
    assert pack_actions(simulation, BREAD) == ("use", "drop", "sell")
    assert pack_actions(simulation, CLOAK) == ("unequip", "drop", "sell")
    assert pack_actions(simulation, SWORD) == ("equip", "drop", "sell")
    assert pack_actions(simulation, {"item_id": "item:potion", "name": "Healing Potion", "category": "potion"})[0] == "use"
    # Bread named for a lantern is still bread: eaten, never held to hand.
    assert pack_actions(simulation, {"item_id": "item:lantern-bread", "name": "Lantern Bread", "category": "food"}) == (
        "use", "drop", "sell")

    document = _document({"cloak": "item:cloak"})
    document["state"]["player"]["inventory"] = [{"item_id": "item:cloak", "name": "Travel Cloak", "category": "clothing",
                                                 "quantity": 1}]
    shown = player_session_view(document)["state"]["player"]["inventory"]
    assert shown == [{"item_id": "item:cloak", "name": "Travel Cloak", "category": "clothing", "quantity": 1,
                      "actions": ["unequip", "drop", "sell"], "worn": True}]
    assert "actions" not in document["state"]["player"]["inventory"][0]  # the stored sheet is not changed
