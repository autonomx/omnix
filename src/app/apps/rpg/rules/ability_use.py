"""The hero's abilities, used (RQ-2.6 part 2; docs/rpg/design/combat.md): pure, from the campaign to the changes.

An ability is the hero's own (``state.ability_tree``), used once it is unlocked (``state.ability_state``), ready
(its cooldown, counted in the hero's turns, is over) and paid for (its stamina or mana). In a fight its effect
operations say what it does there: a blow made sharper and harder (``resource_delta`` on the target's health, with an
attack check's bonus), a heal of the hero, or a target hindered (a negative check on an enemy, for its turns). Out
of a fight it is paid for and begins its cooldown the same way, and its heal heals; what else it does there no rule of
the game keeps, so the story tells it. The hotbar holds the hero's active abilities, one to a slot (1 to 10).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import AbilityUsed, HotbarChanged, HpChanged, ResourcesChanged, StateChange
from app.apps.rpg.foundation.state import access as _sections

DAMAGE_PER_BONUS = 4  # an ability's health damage is on the hero's 100-point scale: every 4 is +1 to the blow


@dataclass(frozen=True)
class FightEffect:
    """What an ability does in a fight."""

    strikes: bool = False
    damage_bonus: int = 0
    accuracy_bonus: int = 0
    heal: int = 0
    hinder: int = 0  # taken from the target's blows
    hinder_turns: int = 0


def known(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The hero's unlocked abilities, as their tree defines them."""
    state = _d(document.get("state"))
    unlocked = {_s(ability_id) for ability_id in _l(_d(state.get("ability_state")).get("unlocked"))}
    return [_d(row) for row in _l(_d(state.get("ability_tree")).get("abilities"))
            if _s(_d(row).get("ability_id")) in unlocked and _s(_d(row).get("name"))]


def find(document: Mapping[str, Any], ref: str) -> dict[str, Any] | None:
    """An unlocked ability by id, hotbar slot, or its name in the player's words."""
    abilities = known(document)
    wanted = _s(ref).strip()
    slot = _s(_d(_d(document.get("state")).get("hotbar")).get(wanted))
    for row in abilities:
        if _s(row.get("ability_id")) in {wanted, slot}:
            return row
    words = re.findall(r"[a-z]+", wanted.casefold())
    named = [row for row in abilities if all(word in words for word in re.findall(r"[a-z]+", _s(row.get("name")).casefold()))]
    return max(named, key=lambda row: len(_s(row.get("name"))), default=None)


def costs(ability: Mapping[str, Any]) -> dict[str, int]:
    return {name: int(amount) for name, amount in _d(ability.get("resource_cost")).items()
            if name in {"stamina", "mana"} and int(amount or 0) > 0}


def _turn(document: Mapping[str, Any]) -> int:
    state, manifest = _d(document.get("state")), _d(document.get("manifest"))
    return int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1  # the turn being played


def not_ready(document: Mapping[str, Any], ability: Mapping[str, Any]) -> str:
    """Why the ability cannot be used now, in the game's words, or "" when it can."""
    name = _s(ability.get("name"))
    ready_at = int(_d(_d(_d(document.get("state")).get("ability_state")).get("ready_at")).get(_s(ability.get("ability_id"))) or 0)
    if ready_at > _turn(document):
        left = ready_at - _turn(document)
        return f"{name} is not ready yet ({left} more turn{'s' if left != 1 else ''})."
    resources = {**_d(_d(_d(document.get("state")).get("player")).get("resources")),
                 **_d(_d(_sections.player_state_of(_d(_sections.simulation_state_of(document)))).get("resources"))}
    for resource, amount in costs(ability).items():
        have = int(_d(resources.get(resource)).get("current") or 0)
        if have < amount:
            return f"{name} needs {amount} {resource}; you have {have}."
    return ""


def spend(document: Mapping[str, Any], ability: Mapping[str, Any]) -> list[StateChange]:
    """Using it: its cost paid, and its cooldown begun."""
    paid = costs(ability)
    changes: list[StateChange] = []
    if paid:
        changes.append(ResourcesChanged(stamina=-paid.get("stamina", 0), mana=-paid.get("mana", 0),
                                        reason=_s(ability.get("ability_id"))))
    changes.append(AbilityUsed(ability_id=_s(ability.get("ability_id")), name=_s(ability.get("name")),
                               ready_at_turn=_turn(document) + max(0, int(ability.get("cooldown_turns") or 0)) + 1))
    return changes


def in_fight(ability: Mapping[str, Any]) -> FightEffect:
    """What the ability's effect operations do in a fight."""
    strikes, damage, accuracy, heal, hinder, turns = False, 0, 0, 0, 0, 0
    for op in map(_d, _l(ability.get("effect_ops"))):
        kind, amount, check = _s(op.get("op")), int(op.get("amount") or 0), _s(op.get("check"))
        if kind == "resource_delta" and _s(op.get("resource")) == "hp":
            if _s(op.get("target")) in {"target", "enemy"} and amount < 0:
                strikes, damage = True, damage + math.ceil(-amount / DAMAGE_PER_BONUS)
            elif amount > 0:
                heal += amount
        elif kind == "modify_next_check" and "attack" in check and amount > 0:
            accuracy += amount
        elif kind == "modify_next_check" and check.startswith("enemy") and amount < 0:
            hinder, turns = hinder - amount, max(turns, int(op.get("duration_turns") or 1))
    return FightEffect(strikes=strikes, damage_bonus=damage, accuracy_bonus=accuracy, heal=heal, hinder=hinder,
                       hinder_turns=turns)


@dataclass(frozen=True)
class Outcome:
    """A use, or a hotbar change: the changes, the game's lines, and whether it was refused (nothing changes)."""

    changes: list[StateChange]
    lines: list[str]
    refused: bool = False


def out_of_fight(document: Mapping[str, Any], ability: Mapping[str, Any]) -> Outcome:
    """The ability used with no fight on: paid for and its cooldown begun; its heal heals the hero, up to their
    maximum health, and what it restores of their own stamina or mana comes back (the pools keep their maximum).
    Refused, in the game's words, when it is not ready or not paid for."""
    refusal = not_ready(document, ability)
    if refusal:
        return Outcome([], [refusal], refused=True)
    name = _s(ability.get("name"))
    changes = spend(document, ability)
    player = _d(_sections.player_state_of(_d(_sections.simulation_state_of(document))))
    pool = _d(_d(player.get("resources")).get("hp"))  # as the fight rule reads it
    maximum = int(pool.get("max") or player.get("max_hp") or 20)
    current = int(raw_current if (raw_current := pool.get("current")) is not None else player.get("hp") or maximum)
    healed = min(in_fight(ability).heal, max(0, maximum - current))
    restored = {resource: 0 for resource in ("stamina", "mana")}
    for op in map(_d, _l(ability.get("effect_ops"))):
        resource, amount = _s(op.get("resource")), int(op.get("amount") or 0)
        if _s(op.get("op")) == "resource_delta" and _s(op.get("target")) == "self" and resource in restored and amount > 0:
            restored[resource] += amount
    lines = [f"You use {name}."]
    if healed:
        changes.append(HpChanged(delta=healed))
        lines = [f"You use {name}, and {healed} health comes back to you."]
    if any(restored.values()):
        changes.append(ResourcesChanged(stamina=restored["stamina"], mana=restored["mana"],
                                        reason=f"{_s(ability.get('ability_id'))}:restored"))
        lines.append(" and ".join(f"{amount} {resource}" for resource, amount in restored.items() if amount)
                     .capitalize() + " comes back to you.")
    return Outcome(changes, lines)


def set_hotbar(document: Mapping[str, Any], slot: str, ability_ref: str = "") -> Outcome:
    """A hotbar slot given one of the hero's active abilities (by id or name), or cleared when none is named."""
    slot = _s(slot).strip()
    if slot not in {str(number) for number in range(1, 11)}:
        return Outcome([], ["The hotbar has slots 1 to 10."], refused=True)
    if not _s(ability_ref).strip():
        return Outcome([HotbarChanged(slot=slot)], [f"Hotbar slot {slot} is empty now."])
    ability = find(document, ability_ref)
    if ability is None:
        return Outcome([], ["You do not know that ability."], refused=True)
    if _s(ability.get("kind") or "active") != "active":
        return Outcome([], [f"{_s(ability.get('name'))} is always with you: there is nothing to put on the hotbar."],
                       refused=True)
    return Outcome([HotbarChanged(slot=slot, ability_id=_s(ability.get("ability_id")))],
                   [f"{_s(ability.get('name'))} is on hotbar slot {slot}."])


def acts_in_a_fight(ability: Mapping[str, Any]) -> bool:
    effect = in_fight(ability)
    return effect.strikes or effect.heal > 0 or effect.hinder > 0


__all__ = ["FightEffect", "Outcome", "acts_in_a_fight", "costs", "find", "in_fight", "known", "not_ready",
           "out_of_fight", "set_hotbar", "spend"]
