"""Items and rest (RQ-2.4; docs/rpg/design/items-and-rest.md)."""
from __future__ import annotations

from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules.interactions.items import drop_item, pick_up, use_item
from app.apps.rpg.rules.rest import rest


def _campaign(*, hp=40, items=(), conditions=(), services=(), providers=None, offers=None, ground=None):
    return {"manifest": {}, "state": {"player": {}}, "simulation_state": {
        "tick": 2,
        "world_model": {"providers": providers or {}, "offers": offers or {},
                        "items": [{"id": "item:bread", "name": "Lantern Bread", "type": "food"}]},
        "player_state": {"location_id": "loc:here", "resources": {"hp": {"current": hp, "max": 100}},
                         "conditions": [dict(c) for c in conditions],
                         "inventory_state": {"items": [dict(item) for item in items]}},
        "survival": {"hunger": 50, "thirst": 50, "fatigue": 70},
        "active_services": [dict(service) for service in services],
        "world_items": {"by_location": {"loc:here": [dict(item) for item in ground or ()]}},
    }}


def _after(campaign, outcome):
    document, _ = reduce(campaign, outcome.changes)
    return document["simulation_state"]


POTION = {"item_id": "healing_potion", "name": "Healing Potion", "qty": 2, "category": "potion"}
BREAD = {"item_id": "item:bread", "name": "Lantern Bread", "qty": 2}


def test_a_potion_heals_a_share_of_strength_and_closes_a_wound() -> None:
    wound = {"kind": "wounded", "attack_penalty": 1, "rests_left": 2}
    campaign = _campaign(items=[POTION], conditions=[wound])
    outcome = use_item(campaign["simulation_state"], "healing_potion", "I drink the Healing Potion.")
    assert outcome.lines == ["You drink the Healing Potion. It restores 15 health.", "Your wound closes."]  # halved
    after = _after(campaign, outcome)
    assert after["player_state"]["resources"]["hp"]["current"] == 55 and after["player_state"]["conditions"] == []
    assert after["player_state"]["inventory_state"]["items"][0]["qty"] == 1


def test_food_eases_hunger_and_other_things_cannot_be_used_like_that() -> None:
    campaign = _campaign(items=[BREAD, {"item_id": "rope", "name": "Rope", "qty": 1, "category": "tool"}])
    bread = use_item(campaign["simulation_state"], "item:bread", "I eat one Lantern Bread.")
    assert bread.lines == ["You eat the Lantern Bread. It eases your hunger."]
    assert _after(campaign, bread)["survival"]["hunger"] == 25
    rope = use_item(campaign["simulation_state"], "rope", "use the rope")
    assert rope.refused and rope.changes == [] and rope.lines == ["The Rope is not something you can use like that."]


def test_things_are_put_down_where_the_hero_stands_and_picked_up_again() -> None:
    campaign = _campaign(items=[BREAD])
    dropped = drop_item(campaign["simulation_state"], "item:bread", "I drop two Lantern Bread")
    assert dropped.lines == ["You put down 2 Lantern Bread; it lies here now."]
    after = _after(campaign, dropped)
    assert after["player_state"]["inventory_state"]["items"] == []
    assert after["world_items"]["by_location"]["loc:here"][0]["qty"] == 2
    picked = pick_up(after, "", "I pick up the Lantern Bread")
    assert picked.lines == ["You pick up the Lantern Bread and stow it in your pack."]
    assert pick_up(_campaign()["simulation_state"], "", "pick up the sword").lines == [
        "Nothing by that name lies here to pick up."]


INN = {"npc:orik": {"provider_id": "npc:orik", "provider_name": "Orik", "location_id": "loc:here",
                    "service_kinds": ["lodging"]}}
ROOM_OFFER = {"npc:orik": [{"offer_id": "npc:orik:night", "service_kind": "lodging", "label": "A night's lodging"}]}


def test_a_night_in_a_room_paid_for_restores_uses_the_room_and_is_a_full_rest() -> None:
    room = {"offer_id": "npc:orik:night", "service_kind": "lodging", "provider_id": "npc:orik", "status": "active",
            "label": "A night's lodging"}
    campaign = _campaign(hp=40, services=[room], providers=INN, offers=ROOM_OFFER,
                         conditions=[{"kind": "battered"}, {"kind": "wounded", "rests_left": 2}])
    outcome = rest(campaign["simulation_state"], "I go to my room and sleep for the night.")
    assert outcome.kind == "room" and outcome.minutes == 480
    after = _after(campaign, outcome)
    assert after["survival"]["fatigue"] == 10 and after["player_state"]["resources"]["hp"]["current"] == 70
    assert after["active_services"][0]["status"] == "consumed" and after["player_state"]["rest_point"] == "loc:here"
    assert after["player_state"]["conditions"] == [{"kind": "wounded", "rests_left": 1}]


def test_no_sleeping_in_the_street_where_rooms_are_rented_but_camping_in_the_wild() -> None:
    village = _campaign(providers=INN, offers=ROOM_OFFER)
    refused = rest(village["simulation_state"], "I sleep.")
    assert refused.refused and refused.lines == ["You have no room here to sleep in. Orik offers A night's lodging."]
    camp = rest(_campaign()["simulation_state"], "I make camp and sleep for the night.")
    assert camp.kind == "camp" and _after(_campaign(), camp)["player_state"]["rest_point"] == "loc:here"
    short = rest(_campaign()["simulation_state"], "rest for a while")
    assert short.kind == "while" and short.minutes == 60 and not any(c.type == "rest_taken" for c in short.changes)
