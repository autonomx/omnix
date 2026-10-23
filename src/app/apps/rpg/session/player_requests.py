"""Deterministic requests a player makes in a turn about their own state: taking on a quest, practising a skill,
and asking where they stand (level, pack, quests, skills); and the quest progress that arriving somewhere makes.

They change the simulation directly (it is projected to the player sheet), before the turn is narrated, and
``describe_player_events`` states what happened so the narration can tell it.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

from app.apps.rpg.rules.economy.currency import apply_currency_delta
from app.apps.rpg.rules.player.player_progression_state import award_skill_xp, resolve_skill_level_ups

PRACTICE_SKILL_XP = 10

_ACCEPT_QUEST = re.compile(r"\b(accept|take on|take up|start|begin|pursue|i'll do|i will do|sign up for)\b")
_PRACTICE = re.compile(r"\b(practi[cs]e|practi[cs]ing|train|training|drill|exercise)\b")
# "Check my quests", "review inventory", "what's my level"; not "what is the quest?" asked of someone.
_STATUS_REQUEST = re.compile(r"\b(check|review)\b|\b(show me|look at|what(?:'s| is| are))\s+my\b")
_STATUS_TOPICS = {
    "progress": re.compile(r"\b(level|experience|xp|progress|character)\b"),
    "inventory": re.compile(r"\b(inventory|pack|bag|belongings|purse|carry(?:ing)?)\b"),
    "quests": re.compile(r"\b(quests?|journal|objectives?)\b"),
    "skills": re.compile(r"\b(skills?|training)\b"),
}
_WORDS = re.compile(r"[a-z0-9']+")
_STOPWORDS = {"the", "a", "an", "of", "in", "to", "and", "quest", "first"}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _quests(simulation_state: dict[str, Any]) -> list[dict[str, Any]]:
    return [_dict(quest) for quest in _dict(simulation_state.get("quest_state")).get("quests") or ()]


def _store_quests(simulation_state: dict[str, Any], quests: list[dict[str, Any]]) -> None:
    quest_state = _dict(simulation_state.get("quest_state"))
    quest_state["quests"] = quests
    simulation_state["quest_state"] = quest_state


def _named_quest(quests: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
    """The quest the player names, by the distinctive words of its title (or the only one on offer)."""
    words = set(_WORDS.findall(text))
    scored = []
    for quest in quests:
        title_words = set(_WORDS.findall(str(quest.get("title") or "").lower())) - _STOPWORDS
        hits = len(title_words & words)
        if hits:
            scored.append((hits, quest))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]
    available = [quest for quest in quests if quest.get("status") == "available"]
    return available[0] if len(available) == 1 else None


def accept_requested_quest(simulation_state: dict[str, Any], player_input: str) -> dict[str, Any]:
    text = str(player_input or "").lower()
    names_a_quest = any(word in text for word in ("quest", "job", "task"))
    if not names_a_quest or not _ACCEPT_QUEST.search(text):
        return {}
    quests = _quests(simulation_state)
    quest = _named_quest(quests, text)
    if quest is None:
        return {}
    if quest.get("status") in {"completed", "failed"}:
        return {"kind": "quest_unchanged", "quest_id": quest.get("id"), "title": quest.get("title"), "status": quest.get("status")}
    already = quest.get("status") == "active"
    quest["status"] = "active"
    _store_quests(simulation_state, [quest if row.get("id") == quest.get("id") else row for row in quests])
    return {"kind": "quest_already_active" if already else "quest_accepted", "quest_id": quest.get("id"),
            "title": quest.get("title"), "objective": quest.get("objective")}


def practise_requested_skill(simulation_state: dict[str, Any], player_input: str) -> dict[str, Any]:
    text = str(player_input or "").lower()
    if not _PRACTICE.search(text):
        return {}
    player_state = _dict(simulation_state.get("player_state"))
    skills = _dict(player_state.get("skills"))
    skill_id = next((skill for skill in skills if re.search(rf"\b{re.escape(skill.replace('_', ' '))}\b", text)), "")
    if not skill_id:
        return {}
    before = _dict(skills.get(skill_id))
    player_state = award_skill_xp(player_state, skill_id, PRACTICE_SKILL_XP, source="practice")
    player_state = resolve_skill_level_ups(player_state)
    level_ups = player_state.pop("_skill_level_ups", [])
    player_state.pop("_level_ups", None)
    simulation_state["player_state"] = player_state
    after = _dict(_dict(player_state.get("skills")).get(skill_id))
    return {"kind": "skill_practised", "skill_id": skill_id, "xp_gained": PRACTICE_SKILL_XP,
            "level_before": int(before.get("level") or 0), "level": int(after.get("level") or 0),
            "level_ups": level_ups}


def _purse_text(currency: Mapping[str, Any]) -> str:
    coins = [f"{int(currency.get(coin) or 0)} {coin}" for coin in ("gold", "silver", "copper") if int(currency.get(coin) or 0)]
    return ", ".join(coins) or "no coin"


def _quantity(item: Mapping[str, Any]) -> int:
    return int(item.get("qty") or item.get("quantity") or 1)


def report_requested_status(simulation_state: dict[str, Any], player_input: str) -> dict[str, Any]:
    """Where the player stands, from the authoritative state, when they ask (nothing changes)."""
    text = str(player_input or "").lower()
    if not _STATUS_REQUEST.search(text):
        return {}
    topics = [topic for topic, pattern in _STATUS_TOPICS.items() if pattern.search(text)]
    if not topics:
        return {}
    player_state = _dict(simulation_state.get("player_state"))
    lines = []
    if "progress" in topics:
        lines.append(f"You are level {int(player_state.get('level') or 1)}, with {int(player_state.get('xp') or 0)} of "
                     f"{int(player_state.get('xp_to_next') or 100)} experience toward the next level.")
    if "inventory" in topics:
        inventory = _dict(player_state.get("inventory_state"))
        items = [_dict(item) for item in inventory.get("items") or () if _dict(item).get("name")]
        carried = ", ".join(f"{_quantity(item)} {item['name']}" if _quantity(item) > 1 else str(item["name"]) for item in items)
        purse = _dict(inventory.get("currency") or player_state.get("currency"))
        lines.append(f"You carry {carried or 'nothing'}; your purse holds {_purse_text(purse)}.")
    if "quests" in topics:
        quests = _quests(simulation_state)
        active = [f"{quest.get('title')} ({quest.get('objective')})" if quest.get("objective") else str(quest.get("title"))
                  for quest in quests if quest.get("status") == "active"]
        available = [str(quest.get("title")) for quest in quests if quest.get("status") == "available"]
        lines.append(f"Active quests: {'; '.join(active)}." if active else "You have no active quest.")
        if available:
            lines.append(f"Quests you could take on: {', '.join(available)}.")
    if "skills" in topics:
        trained = []
        for skill, row in _dict(player_state.get("skills")).items():
            row = _dict(row)
            if int(row.get("xp") or 0) or int(row.get("level") or 0):
                trained.append(f"{skill.replace('_', ' ')} level {int(row.get('level') or 0)} "
                               f"({int(row.get('xp') or 0)} of {int(row.get('xp_to_next') or 25)} XP)")
        lines.append(f"Skills in training: {'; '.join(trained)}." if trained else "None of your skills has progressed yet.")
    return {"kind": "status_report", "topics": topics, "lines": lines}


def describe_player_events(events: Iterable[Mapping[str, Any]]) -> list[str]:
    """What the turn's requests and arrivals did, in plain sentences the narration can tell."""
    lines: list[str] = []
    for event in events:
        kind = str(event.get("kind") or "")
        title = str(event.get("title") or "")
        if kind == "quest_accepted":
            objective = str(event.get("objective") or "")
            lines.append(f"You take on the quest {title}" + (f": {objective}." if objective else "."))
        elif kind == "quest_already_active":
            lines.append(f"{title} is already among your active quests.")
        elif kind == "skill_practised":
            skill = str(event.get("skill_id") or "").replace("_", " ")
            line = f"Your practice earns {int(event.get('xp_gained') or 0)} experience in {skill}."
            if int(event.get("level") or 0) > int(event.get("level_before") or 0):
                line += f" {skill.capitalize()} rises to level {int(event.get('level') or 0)}."
            lines.append(line)
        elif kind == "quest_progressed":
            lines.append(f"Progress on {title}: {event.get('visited')} of {event.get('of')} places reached.")
        elif kind == "quest_completed":
            rewards = [*(f"{amount} {coin}" for coin, amount in _dict(event.get("currency")).items() if amount),
                       *(str(item) for item in event.get("items") or ())]
            lines.append(f"Quest complete: {title}." + (f" You receive {', '.join(rewards)}." if rewards else ""))
        elif kind == "status_report":
            lines.extend(str(line) for line in event.get("lines") or ())
        elif kind == "item_sold":
            copper = int(event.get("copper") or 0)
            coins = _purse_text(apply_currency_delta({}, {"copper": copper}))
            lines.append(f"You sell the {event.get('item')} to {event.get('buyer')} for {coins}.")
        elif kind == "item_dropped":
            quantity = int(event.get("qty") or 1)
            lines.append(f"You put down {quantity} {event.get('item')}; it lies here now." if quantity > 1
                         else f"You put down the {event.get('item')}; it lies here now.")
        elif kind == "item_picked_up":
            lines.append(f"You pick up the {event.get('item')} and stow it in your pack.")
        elif kind == "pick_up_refused":
            lines.append("Nothing by that name lies here to pick up.")
        elif kind == "sale_refused":
            lines.append({
                "not_carried": "You carry nothing by that name to sell.",
                "no_buyer_here": f"No one here trades in goods to buy the {event.get('item')}.",
                "keepsake": f"{event.get('buyer')} will not buy the {event.get('item')}: it was earned, not bought.",
            }.get(str(event.get("reason")), "The sale does not happen."))
    return lines


_SELL = re.compile(r"\bsell(?:s|ing)?\b")
# What a shop pays for goods it does not trade in itself (a token sum; a shop's own goods fetch half its price).
UNTRADED_GOODS_PRICE = {"copper": 5}


def _copper(price: Mapping[str, Any]) -> int:
    return int(price.get("gold") or 0) * 100 + int(price.get("silver") or 0) * 10 + int(price.get("copper") or 0)


def sell_requested_item(simulation_state: dict[str, Any], player_input: str) -> dict[str, Any]:
    """Sell one of something the player carries to a shopkeeper who is present, in a world with its own people."""
    text = str(player_input or "").lower()
    world = _dict(simulation_state.get("world_model"))
    if not _SELL.search(text) or not world:
        return {}
    player_state = _dict(simulation_state.get("player_state"))
    location_id = str(player_state.get("location_id") or "")
    shops = [
        _dict(provider) for provider in _dict(world.get("providers")).values()
        if "shop_goods" in (_dict(provider).get("service_kinds") or ()) and _dict(provider).get("location_id") == location_id
    ]
    named = [shop for shop in shops if str(shop.get("provider_name") or "").lower() in text]
    shop = (named or shops)[0] if len(named or shops) == 1 else None
    inventory = _dict(player_state.get("inventory_state"))
    items = [_dict(item) for item in inventory.get("items") or ()]
    carried = sorted((item for item in items if str(item.get("name") or "").lower() in text),
                     key=lambda item: len(str(item.get("name") or "")), reverse=True)
    if not carried:
        return {"kind": "sale_refused", "reason": "not_carried"}
    item = carried[0]
    name = str(item.get("name"))
    if shop is None:
        return {"kind": "sale_refused", "item": name, "reason": "no_buyer_here"}
    rewards = {str(reward) for quest in _quests(simulation_state) for reward in quest.get("rewards") or ()}
    if str(item.get("item_id") or "") in rewards:
        return {"kind": "sale_refused", "item": name, "buyer": shop.get("provider_name"), "reason": "keepsake"}
    offers = [_dict(offer) for offer in _dict(world.get("offers")).get(str(shop.get("provider_id"))) or ()]
    own = next((offer for offer in offers if str(offer.get("label") or "").lower() == name.lower()), {})
    paid = max(1, _copper(_dict(own.get("price"))) // 2) if own else _copper(UNTRADED_GOODS_PRICE)
    quantity = int(item.get("qty") or item.get("quantity") or 1)
    remaining = [row for row in items if row is not item]
    if quantity > 1:
        remaining.insert(items.index(item), {**item, "qty": quantity - 1})
    purse = apply_currency_delta(_dict(inventory.get("currency") or player_state.get("currency")), {"copper": paid})
    inventory["items"] = remaining
    inventory["currency"] = purse
    player_state["inventory_state"] = inventory
    player_state["currency"] = deepcopy(purse)
    simulation_state["player_state"] = player_state
    return {"kind": "item_sold", "item": name, "buyer": shop.get("provider_name"), "copper": paid}


_DROP = re.compile(r"\b(drop|drops|dropped|put down|set down|leave behind|discard|throw away)\b")
_PICK_UP = re.compile(r"\b(pick(?:s|ed)?\s+(?:\w+\s+){0,4}?up|pick up|take|grab|collect|gather)\b")


def _named(rows: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
    """The row whose name the player says (the longest such name)."""
    named = [row for row in rows if str(row.get("name") or "").lower() and str(row.get("name")).lower() in text]
    return max(named, key=lambda row: len(str(row.get("name")))) if named else None


def drop_requested_item(simulation_state: dict[str, Any], player_input: str) -> dict[str, Any]:
    """Put something the player carries on the ground where they stand (one, or all with "all")."""
    from app.apps.rpg.session.inventory_runtime import drop_item_action

    text = str(player_input or "").lower()
    if not _DROP.search(text):
        return {}
    player_state = _dict(simulation_state.get("player_state"))
    item = _named([_dict(row) for row in _dict(player_state.get("inventory_state")).get("items") or ()], text)
    if item is None:
        return {}  # "drop by the guild" drops nothing: the rest of the turn reads it
    carried = int(item.get("qty") or item.get("quantity") or 1)
    quantity = carried if re.search(r"\ball\b", text) else 1
    location_id = str(player_state.get("location_id") or simulation_state.get("current_location_id") or "")
    result = drop_item_action(simulation_state, {"item_id": item.get("item_id"), "qty": quantity}, location_id=location_id)
    simulation_state.update(_dict(result.get("simulation_state")))
    return {"kind": "item_dropped", "item": item.get("name"), "qty": quantity}


def pick_up_requested_item(simulation_state: dict[str, Any], player_input: str) -> dict[str, Any]:
    """Take something lying where the player stands into their pack."""
    from app.apps.rpg.rules.items.inventory_state import add_inventory_items
    from app.apps.rpg.rules.items.world_items import list_scene_items, pickup_world_item

    text = str(player_input or "").lower()
    if not _PICK_UP.search(text):
        return {}
    player_state = _dict(simulation_state.get("player_state"))
    location_id = str(player_state.get("location_id") or simulation_state.get("current_location_id") or "")
    item = _named(list_scene_items(simulation_state, location_id), text)
    if item is None:
        # "Take" also takes on quests and takes a seat; only "pick up" is plainly about something on the ground.
        return {"kind": "pick_up_refused", "reason": "not_here"} if "pick" in text else {}
    result = pickup_world_item(simulation_state, str(item.get("instance_id") or ""))
    simulation_state.update(_dict(result.get("simulation_state")))
    # Back in the pack it joins its own stack: where it lay is no longer part of it.
    picked = {key: value for key, value in _dict(result.get("picked_up_item")).items()
              if key not in {"instance_id", "location_id", "_degraded"}}
    player_state = _dict(simulation_state.get("player_state"))
    player_state["inventory_state"] = add_inventory_items(_dict(player_state.get("inventory_state")), [picked])
    simulation_state["player_state"] = player_state
    return {"kind": "item_picked_up", "item": item.get("name"), "qty": int(item.get("qty") or 1)}


def _reward_currency(simulation_state: dict[str, Any], rewards: list[str]) -> dict[str, int]:
    gained = {"gold": 0, "silver": 0, "copper": 0}
    for reward in rewards:
        for amount, coin in re.findall(r"(\d+)\s*(gold|silver|copper)", reward.lower()):
            gained[coin] += int(amount)
    if not any(gained.values()):
        return gained
    player_state = _dict(simulation_state.get("player_state"))
    inventory = _dict(player_state.get("inventory_state"))
    # Added as purchases spend: coins carry over (20 silver is 2 gold), so every purse reads the same way.
    purse = apply_currency_delta(_dict(inventory.get("currency") or player_state.get("currency")), gained)
    inventory["currency"] = purse
    player_state["currency"] = deepcopy(purse)
    player_state["inventory_state"] = inventory
    simulation_state["player_state"] = player_state
    return gained


def _reward_items(simulation_state: dict[str, Any], rewards: list[str]) -> list[str]:
    world_items = {
        str(item.get("id")): item
        for item in _dict(simulation_state.get("world_model")).get("items") or ()
        if isinstance(item, Mapping)
    }
    player_state = _dict(simulation_state.get("player_state"))
    inventory = _dict(player_state.get("inventory_state"))
    items = [_dict(item) for item in inventory.get("items") or ()]
    added = []
    for reward in rewards:
        if not reward.startswith("item:"):
            continue
        item = _dict(world_items.get(reward))
        name = str(item.get("name") or reward.rsplit(":", 1)[-1].replace("-", " ").title())
        existing = next((row for row in items if row.get("item_id") == reward), None)
        if existing:
            existing["qty"] = int(existing.get("qty") or 1) + 1
        else:
            items.append({"item_id": reward, "name": name, "qty": 1, "category": str(item.get("type") or "misc"),
                          "description": str(item.get("effect") or item.get("description") or "")})
        added.append(name)
    inventory["items"] = items
    player_state["inventory_state"] = inventory
    simulation_state["player_state"] = player_state
    return added


def advance_quests_on_arrival(simulation_state: dict[str, Any], location_id: str) -> list[dict[str, Any]]:
    """An active quest that names its places advances as the player reaches them, and completes (paying its
    rewards) when the last is reached."""
    quests = _quests(simulation_state)
    events = []
    changed = False
    for quest in quests:
        places = [str(place) for place in quest.get("locations") or ()]
        if quest.get("status") != "active" or location_id not in places:
            continue
        visited = [str(place) for place in quest.get("visited_locations") or ()]
        if location_id in visited:
            continue
        visited.append(location_id)
        quest["visited_locations"] = visited
        changed = True
        if set(places) <= set(visited):
            quest["status"] = "completed"
            rewards = [str(reward) for reward in quest.get("rewards") or ()]
            events.append({"kind": "quest_completed", "quest_id": quest.get("id"), "title": quest.get("title"),
                           "currency": _reward_currency(simulation_state, rewards),
                           "items": _reward_items(simulation_state, rewards)})
        else:
            events.append({"kind": "quest_progressed", "quest_id": quest.get("id"), "title": quest.get("title"),
                           "visited": len(visited), "of": len(places)})
    if changed:
        _store_quests(simulation_state, quests)
    return events


def has_player_requests(simulation_state: Mapping[str, Any], player_input: str) -> bool:
    """Whether the player's words make such a request (decided on a copy; nothing changes)."""
    return bool(apply_player_requests(deepcopy(dict(simulation_state)), player_input))


def apply_player_requests(simulation_state: dict[str, Any], player_input: str) -> list[dict[str, Any]]:
    """Every request in the player's words that changes their own state, applied in place."""
    return [event for event in (
        accept_requested_quest(simulation_state, player_input),
        practise_requested_skill(simulation_state, player_input),
        report_requested_status(simulation_state, player_input),
        sell_requested_item(simulation_state, player_input),
        drop_requested_item(simulation_state, player_input),
        pick_up_requested_item(simulation_state, player_input),
    ) if event]


__all__ = [
    "PRACTICE_SKILL_XP",
    "accept_requested_quest",
    "advance_quests_on_arrival",
    "apply_player_requests",
    "describe_player_events",
    "drop_requested_item",
    "has_player_requests",
    "pick_up_requested_item",
    "practise_requested_skill",
    "report_requested_status",
    "sell_requested_item",
]
