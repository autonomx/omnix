"""Items and rest (RQ-2.4; docs/rpg/design/items-and-rest.md)."""
from __future__ import annotations

from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.foundation.state.changes import ItemRemoved, RegardChanged
from app.apps.rpg.rules.interactions.items import GIFT_REGARD, drop_item, give_item, pick_up, use_item
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
    outcome = use_item(campaign["simulation_state"], "healing_potion")
    assert outcome.lines == ["You drink the Healing Potion. It restores 15 health.", "Your wound closes."]  # halved
    after = _after(campaign, outcome)
    assert after["player_state"]["resources"]["hp"]["current"] == 55 and after["player_state"]["conditions"] == []
    assert after["player_state"]["inventory_state"]["items"][0]["qty"] == 1


def test_food_eases_hunger_and_other_things_cannot_be_used_like_that() -> None:
    campaign = _campaign(items=[BREAD, {"item_id": "rope", "name": "Rope", "qty": 1, "category": "tool"}])
    bread = use_item(campaign["simulation_state"], "item:bread")
    assert bread.lines == ["You eat the Lantern Bread. It eases your hunger."]
    assert _after(campaign, bread)["survival"]["hunger"] == 25
    rope = use_item(campaign["simulation_state"], "rope")
    assert rope.refused and rope.changes == [] and rope.lines == ["The Rope is not something you can use like that."]


def test_things_are_put_down_where_the_hero_stands_and_picked_up_again() -> None:
    campaign = _campaign(items=[BREAD])
    dropped = drop_item(campaign["simulation_state"], "item:bread", quantity=2)
    assert dropped.lines == ["You put down 2 Lantern Bread; it lies here now."]
    after = _after(campaign, dropped)
    assert after["player_state"]["inventory_state"]["items"] == []
    assert after["world_items"]["by_location"]["loc:here"][0]["qty"] == 2
    picked = pick_up(after, "item:bread")
    assert picked.lines == ["You pick up the Lantern Bread and stow it in your pack."]
    assert pick_up(_campaign()["simulation_state"], "item:sword").lines == [
        "Nothing by that name lies here to pick up."]


INN = {"npc:orik": {"provider_id": "npc:orik", "provider_name": "Orik", "location_id": "loc:here",
                    "service_kinds": ["lodging"]}}
ROOM_OFFER = {"npc:orik": [{"offer_id": "npc:orik:night", "service_kind": "lodging", "label": "A night's lodging"}]}


def test_a_night_in_a_room_paid_for_restores_uses_the_room_and_is_a_full_rest() -> None:
    room = {"offer_id": "npc:orik:night", "service_kind": "lodging", "provider_id": "npc:orik", "status": "active",
            "label": "A night's lodging"}
    campaign = _campaign(hp=40, services=[room], providers=INN, offers=ROOM_OFFER,
                         conditions=[{"kind": "battered"}, {"kind": "wounded", "rests_left": 2}])
    outcome = rest(campaign["simulation_state"], "sleep")
    assert outcome.kind == "room" and outcome.minutes == 480
    after = _after(campaign, outcome)
    assert after["survival"]["fatigue"] == 10 and after["player_state"]["resources"]["hp"]["current"] == 70
    assert after["active_services"][0]["status"] == "consumed" and after["player_state"]["rest_point"] == "loc:here"
    assert after["player_state"]["conditions"] == [{"kind": "wounded", "rests_left": 1}]


def test_no_sleeping_in_the_street_where_rooms_are_rented_but_camping_in_the_wild() -> None:
    village = _campaign(providers=INN, offers=ROOM_OFFER)
    refused = rest(village["simulation_state"], "sleep")
    assert refused.refused and refused.lines == ["You have no room here to sleep in. Orik offers a night's lodging."]
    camp = rest(_campaign()["simulation_state"], "camp")
    assert camp.kind == "camp" and _after(_campaign(), camp)["player_state"]["rest_point"] == "loc:here"
    short = rest(_campaign()["simulation_state"], None)
    assert short.kind == "while" and short.minutes == 60 and not any(c.type == "rest_taken" for c in short.changes)


def test_a_gift_leaves_the_pack_for_someone_here_who_trusts_the_hero_more() -> None:
    dagger = {"item_id": "iron_dagger", "name": "Iron Dagger", "qty": 1, "category": "weapon"}
    campaign = _campaign(items=[dagger, BREAD])
    simulation = campaign["simulation_state"]
    simulation["world_model"]["npcs"] = {"npc:liora": {"name": "Liora Fen"}, "npc:orik": {"name": "Orik"}}
    simulation["present_npc_state"] = {"present_npc_ids": ["npc:liora"]}
    given = give_item(simulation, "iron_dagger", "npc:liora")
    assert given.lines == ["You give the Iron Dagger to Liora Fen."] and not given.refused
    assert given.changes == [ItemRemoved(item_id="iron_dagger", quantity=1),
                             RegardChanged(npc_id="npc:liora", name="Liora Fen", delta=GIFT_REGARD, reason="gift:iron_dagger")]
    after = _after(campaign, given)
    assert [item["item_id"] for item in after["player_state"]["inventory_state"]["items"]] == ["item:bread"]
    assert give_item(simulation, "item:bread", "", quantity=2).lines == [
        "You give 2 Lantern Bread to Liora Fen."]  # unnamed: to the one person here
    away = give_item(simulation, "iron_dagger", "npc:orik")
    assert away.refused and away.lines == ["Orik is not here."] and away.changes == []
    assert give_item(simulation, "rope", "npc:liora").lines == ["You carry nothing like that."]
    simulation["present_npc_state"] = {"present_npc_ids": ["npc:liora", "npc:orik"]}
    asked = give_item(simulation, "iron_dagger", "")
    assert asked.refused and asked.lines == ["To whom do you give the Iron Dagger?"]
    # Gifts alone win no one's trust (review 4: ten apples one at a time reached the friendly stance).
    simulation["relationship_state"] = {"npc:liora": {"trust": 23}}
    simulation["present_npc_state"] = {"present_npc_ids": ["npc:liora"]}
    nearly = give_item(simulation, "item:bread", "")
    assert [change.delta for change in nearly.changes if change.type == "regard_changed"] == [2]  # up to 25
    simulation["relationship_state"] = {"npc:liora": {"trust": 25}}
    assert [change.type for change in give_item(simulation, "item:bread", "").changes] == [
        "item_removed"]


def test_a_nights_sleep_lasts_until_morning_and_never_less_than_eight_hours() -> None:
    """The playtest: a room taken at 20:36 was slept in for eight hours, and the hero woke at 04:36 to a village
    asleep, the narration saying "by morning"."""
    def slept(at_minute: int) -> int:
        campaign = _campaign()
        campaign["simulation_state"]["environment"] = {"absolute_minutes": at_minute}
        return rest(campaign["simulation_state"], "camp").minutes

    assert slept(1440 + 20 * 60 + 36) == 11 * 60 + 24  # 20:36 to 08:00
    assert slept(1440 + 2 * 60) == 480  # 02:00: eight hours, to 10:00
    assert slept(1440 + 14 * 60) == 480  # an afternoon's: eight hours
