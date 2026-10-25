"""Items (RQ-2.4; docs/rpg/design/items-and-rest.md): using what the hero carries, putting it down, picking it up,
and wearing or wielding it.

A pure rule: it reads the hero's pack, the ground where they stand and the world's items, and says what happens
as changes. What an item does comes from its kind in the world (potion, food, drink).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    ConditionsChanged,
    HpChanged,
    ItemDropped,
    ItemEquipped,
    ItemPickedUp,
    ItemRemoved,
    ItemUnequipped,
    NeedsChanged,
    StateChange,
)
from app.apps.rpg.rules.combat.stakes import WOUNDED, conditions, healing
from app.apps.rpg.foundation.state import access as _sections

HEAL_SHARE = 0.30
MIN_HEAL = 10
RELIEF = {"food": ("hunger", -25), "drink": ("thirst", -30)}
_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "both": 2, "all": 0}


@dataclass(frozen=True)
class ItemOutcome:
    changes: list[StateChange] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    refused: bool = False
    minutes: int = 0


def _pack(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_d(item) for item in _l(_d(_sections.inventory_state_of(_d(_sections.player_state_of(simulation)))).get("items"))]


def _id(item: Mapping[str, Any]) -> str:
    return _s(item.get("item_id") or item.get("id") or item.get("name"))


def _count(item: Mapping[str, Any]) -> int:
    return int(item.get("qty", item.get("quantity", 1)) or 0)


def _find(stacks: list[dict[str, Any]], item_id: str, text: str) -> dict[str, Any]:
    """The stack the player means: the one the grammar read, else the longest name the words contain."""
    if item_id:
        found = next((stack for stack in stacks if _id(stack) == item_id), None)
        if found:
            return found
    lowered = text.casefold()
    named = sorted((stack for stack in stacks if _s(stack.get("name")) and _s(stack.get("name")).casefold() in lowered),
                   key=lambda stack: len(_s(stack.get("name"))), reverse=True)
    return named[0] if named else {}


def _kind(simulation: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    world = {_s(_d(row).get("id")): _d(row) for row in _l(_d(_sections.world_model_of(simulation)).get("items"))}
    kind = (_s(item.get("category") or item.get("type")) or _s(world.get(_id(item), {}).get("type"))).casefold()
    healing_named = "heal" in _id(item).casefold() or "healing" in _s(item.get("name")).casefold()
    if kind == "potion" or (kind in {"", "consumable", "misc"} and healing_named):
        return "potion"
    return kind


def _quantity(text: str, held: int) -> int:
    for word in re.findall(r"[a-z]+|\d+", text.casefold()):
        if word.isdigit():
            return max(1, min(held, int(word)))
        if word in _NUMBERS:
            return held if _NUMBERS[word] == 0 else min(held, _NUMBERS[word])
    return 1


def use_item(simulation: Mapping[str, Any], item_id: str, text: str) -> ItemOutcome:
    item = _find(_pack(simulation), item_id, text)
    if not item:
        return ItemOutcome(lines=["You carry nothing like that."], refused=True)
    name, kind = _s(item.get("name")) or _id(item), _kind(simulation, item)
    used: list[StateChange] = [ItemRemoved(item_id=_id(item), quantity=1)]
    if kind == "potion":
        player = _d(_sections.player_state_of(simulation))
        hp = _d(_d(player.get("resources")).get("hp"))
        maximum, current = int(hp.get("max") or 0), int(hp.get("current") or 0)
        restored = min(max(0, maximum - current), healing(dict(simulation), "player", max(MIN_HEAL, int(maximum * HEAL_SHARE))))
        lines = [f"You drink the {name}." + (f" It restores {restored} health." if restored else " You feel no different.")]
        changes = [*used, *([HpChanged(delta=restored)] if restored else [])]
        held = conditions(player)
        if any(condition.get("kind") == WOUNDED for condition in held):
            changes.append(ConditionsChanged(actor_id="player", conditions=tuple(
                condition for condition in held if condition.get("kind") != WOUNDED)))
            lines.append("Your wound closes.")
        return ItemOutcome(changes, lines, minutes=10)
    if kind in RELIEF:
        need, delta = RELIEF[kind]
        verb = "eat" if kind == "food" else "drink"
        return ItemOutcome([*used, NeedsChanged(**{need: delta})], [f"You {verb} the {name}. It eases your {need}."],
                           minutes=10)
    return ItemOutcome(lines=[f"The {name} is not something you can use like that."], refused=True)


def drop_item(simulation: Mapping[str, Any], item_id: str, text: str) -> ItemOutcome:
    item = _find(_pack(simulation), item_id, text)
    if not item:
        return ItemOutcome(lines=["You carry nothing like that."], refused=True)
    location = _s(_d(_sections.player_state_of(simulation)).get("location_id"))
    quantity = _quantity(text, _count(item))
    name = _s(item.get("name")) or _id(item)
    return ItemOutcome([ItemDropped(item_id=_id(item), quantity=quantity, location_id=location)],
                       [f"You put down {quantity} {name}; it lies here now." if quantity > 1
                        else f"You put down the {name}; it lies here now."])


def pick_up(simulation: Mapping[str, Any], item_id: str, text: str) -> ItemOutcome:
    location = _s(_d(_sections.player_state_of(simulation)).get("location_id"))
    ground = [_d(item) for item in _l(_d(_d(simulation.get("world_items")).get("by_location")).get(location))]
    item = _find(ground, item_id, text)
    if not item:
        return ItemOutcome(lines=["Nothing by that name lies here to pick up."], refused=True)
    quantity = _quantity(text, _count(item))
    name = _s(item.get("name")) or _id(item)
    return ItemOutcome([ItemPickedUp(item_id=_id(item), quantity=quantity, location_id=location)],
                       [f"You pick up the {name} and stow it in your pack."])


# Where a thing is worn, by its kind or its name (the store's slots; the sheet calls main_hand "Weapon").
_SLOT_WORDS = (
    ("main_hand", ("weapon", "bow", "dagger", "sword", "axe", "staff", "wand", "mace", "spear", "longbow", "club")),
    ("off_hand", ("shield",)),
    ("body", ("armor", "armour", "mail", "leather", "plate", "robe")),
    ("head", ("helmet", "helm", "hood", "cap")),
    ("cloak", ("cloak", "cape", "mantle")),
    ("ring", ("ring", "band")),
    ("tool", ("tool", "compass", "lantern", "lamp", "torch", "spyglass", "lens", "pickaxe", "kit")),  # held to hand
)


def _slot(simulation: Mapping[str, Any], item: Mapping[str, Any]) -> str:
    kind = _kind(simulation, item)
    if kind == "potion" or kind in RELIEF:  # eaten or drunk, never worn (Lantern Bread is no lantern)
        return ""
    words = set(re.findall(r"[a-z]+", f"{kind} {_s(item.get('name'))}".casefold()))
    return next((slot for slot, names in _SLOT_WORDS if words & set(names)), "")


def _worn(simulation: Mapping[str, Any]) -> dict[str, str]:
    store = _d(_sections.inventory_state_of(_d(_sections.player_state_of(simulation))))
    return {_s(slot): _s(item_id) for slot, item_id in _d(store.get("equipment")).items() if _s(item_id)}


def equip_item(simulation: Mapping[str, Any], item_id: str, text: str) -> ItemOutcome:
    """Wear or wield something carried, in its place (a second weapon takes the first one's)."""
    item = _find(_pack(simulation), item_id, text)
    if not item:
        return ItemOutcome(lines=["You carry nothing like that."], refused=True)
    name, slot = _s(item.get("name")) or _id(item), _slot(simulation, item)
    if not slot:
        return ItemOutcome(lines=[f"The {name} is not something you can wear or wield."], refused=True)
    if _worn(simulation).get(slot) == _id(item):
        return ItemOutcome(lines=[f"You already have the {name} ready."])  # nothing to change, and no harm asking
    verb = "take up" if slot in {"main_hand", "off_hand"} else "put on"
    return ItemOutcome([ItemEquipped(slot=slot, item_id=_id(item))], [f"You {verb} the {name}."])


def unequip_item(simulation: Mapping[str, Any], item_id: str, text: str) -> ItemOutcome:
    """Take off or put away something worn; it stays in the pack."""
    worn = _worn(simulation)
    items = {_id(item): item for item in _pack(simulation)}
    wanted = _find([items[item] for item in worn.values() if item in items], item_id, text)
    if not wanted:
        return ItemOutcome(lines=["You are not wearing or wielding anything like that."], refused=True)
    slot = next(slot for slot, worn_id in worn.items() if worn_id == _id(wanted))
    return ItemOutcome([ItemUnequipped(slot=slot)], [f"You put away the {_s(wanted.get('name')) or _id(wanted)}."])


def is_worn(simulation: Mapping[str, Any], item: Mapping[str, Any]) -> bool:
    return _id(item) in _worn(simulation).values()


def pack_actions(simulation: Mapping[str, Any], item: Mapping[str, Any]) -> tuple[str, ...]:
    """What these rules let the hero do with a carried thing: use it (a potion, food or drink), put it on or away (it
    has a place), drop it, or offer it for sale (the trade rule finds the buyer, or says there is none)."""
    kind, slot = _kind(simulation, item), _slot(simulation, item)
    usable = ("use",) if kind == "potion" or kind in RELIEF else ()
    wearable = (("unequip",) if is_worn(simulation, item) else ("equip",)) if slot else ()
    return (*usable, *wearable, "drop", "sell")


__all__ = ["ItemOutcome", "drop_item", "equip_item", "is_worn", "pack_actions", "pick_up", "unequip_item", "use_item"]
