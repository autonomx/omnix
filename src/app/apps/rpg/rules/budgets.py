"""The level's budgets (evolution roadmap EV-2): what a hero of each level should meet, carry and earn. Pure.

Nothing held these before: the balance simulation's bands were campaign-wide. A world may author its table as the
``budgets`` play section (``genesis/worlds/world_play_sections.Budget``, a row per level); a world that writes none,
and a campaign already running, reads the derived default here, which follows the bestiary's threat numbers
(``published_world_setup._THREAT_STATS``) and the shops' prices. Each row holds:

- a creature's health, damage and defence, alone and as one of a group (a group's members are each weaker);
- an item's numbers and price, by slot;
- a quest's and a site's reward in coin, experience and items;
- an encounter's total danger: the sum of its foes' ``budget_cost`` (their experience value).

Fights are set by it (a road's encounter is one whose danger fits, ``encounter_fits``), the balance simulation checks
it, and the game master (EV-0), crafting (EV-5) and areas filled in (EV-10) read it.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections

MAX_LEVEL = 30
GROUP_SHARE = 0.6  # one of a group: its health and damage at this share of a lone creature's
SLOTS = ("main_hand", "off_hand", "body", "head", "cloak", "ring", "tool")


class Band(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    low: int
    high: int

    def holds(self, value: int) -> bool:
        return self.low <= value <= self.high


class CreatureBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hp: Band
    damage_max: Band
    defense: Band


class ItemBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    damage_max: Band | None = None  # a weapon's
    armor: Band | None = None  # what is worn
    price_copper: Band


class RewardBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    copper: Band
    xp: Band
    items: int = Field(default=1, ge=0, le=10)


class LevelBudget(BaseModel):
    """What a hero of ``level`` should meet, carry and earn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: int = Field(ge=1, le=MAX_LEVEL)
    creature: CreatureBudget
    group_member: CreatureBudget
    items: dict[str, ItemBudget]
    quest_reward: RewardBudget
    site_reward: RewardBudget
    danger: Band  # an encounter's total budget_cost


def _band(value: float, spread: float = 0.35) -> Band:
    return Band(low=max(0, round(value * (1 - spread))), high=max(1, round(value * (1 + spread))))


def derived(level: int) -> LevelBudget:
    """The default row for ``level``: a lone creature of the hero's level, by the bestiary's threat numbers (a level 1
    creature has some 10 health and hits for up to 4; a level 5 one 28 and 8); goods priced as the shops price them."""
    level = max(1, min(MAX_LEVEL, int(level)))
    hp, damage, defense = 6 + 4.5 * level, 3 + level, 9.5 + level * 0.75
    weapon, armor, price = 2 + 1.2 * level, 0.5 + level / 3, 40 * level
    creature = CreatureBudget(hp=_band(hp), damage_max=_band(damage), defense=_band(defense, 0.15))
    member = CreatureBudget(hp=_band(hp * GROUP_SHARE), damage_max=_band(damage * GROUP_SHARE),
                            defense=_band(defense, 0.15))
    items = {slot: ItemBudget(damage_max=_band(weapon) if slot == "main_hand" else None,
                              armor=_band(armor, 0.6) if slot in {"off_hand", "body", "head", "cloak"} else None,
                              price_copper=_band(price * (2.0 if slot in {"main_hand", "body"} else 1.0), 0.6))
             for slot in SLOTS}
    return LevelBudget(level=level, creature=creature, group_member=member, items=items,
                       quest_reward=RewardBudget(copper=_band(100 * level, 0.6), xp=_band(60 * level, 0.6)),
                       site_reward=RewardBudget(copper=_band(60 * level, 0.6), xp=_band(40 * level, 0.6)),
                       danger=Band(low=0, high=round(35 * level + 40)))


def budget(simulation: Mapping[str, Any], level: int) -> LevelBudget:
    """The world's row for ``level`` (its ``budgets`` play section, kept in the world model), else the derived one."""
    rows = [_d(row) for row in _l(_d(_sections.world_model_of(simulation)).get("budgets"))]
    authored = {int(row.get("level") or 0): row for row in rows}
    row = authored.get(int(level))
    if row:
        try:
            return LevelBudget.model_validate(row)
        except ValueError:  # an authored row the table cannot read is played from the derived one
            pass
    return derived(level)


def danger(creatures: list[Mapping[str, Any]]) -> int:
    return sum(int(creature.get("budget_cost") or creature.get("xp_value") or 0) for creature in creatures)


def encounter_fits(simulation: Mapping[str, Any], creatures: list[Mapping[str, Any]], level: int) -> bool:
    """Whether an encounter's danger is within a hero of ``level``'s budget."""
    return danger(creatures) <= budget(simulation, level).danger.high


def creature_findings(simulation: Mapping[str, Any], creature: Mapping[str, Any]) -> list[str]:
    """Where a creature's numbers fall outside its level's budget (the balance simulation and authoring read them)."""
    row = budget(simulation, int(creature.get("level") or 1)).creature
    found = []
    for key, band in (("hp", row.hp), ("damage_max", row.damage_max), ("defense", row.defense)):
        value = int(creature.get(key) or 0)
        if not band.holds(value):
            found.append(f"{creature.get('definition_id') or creature.get('name')}: {key} {value} is outside "
                         f"{band.low}-{band.high} for level {int(creature.get('level') or 1)}")
    return found


# What a larger area holds (EV-10): how many of each kind of entry, by the area's size. Authored detail counts toward
# it; only what is missing is filled in. A world's ``gm_guide`` may change the counts of an area (``areas``).
AREA_KINDS = ("place", "site", "person", "creature", "item", "service", "quest", "rumour", "lore")
AREA_COUNTS: dict[str, dict[str, int]] = {
    "small": {"place": 1, "site": 1, "person": 2, "creature": 1, "item": 1, "service": 1, "quest": 1, "rumour": 1,
              "lore": 1},
    "medium": {"place": 3, "site": 1, "person": 3, "creature": 2, "item": 2, "service": 1, "quest": 1, "rumour": 2,
               "lore": 2},
    "large": {"place": 5, "site": 2, "person": 5, "creature": 3, "item": 3, "service": 2, "quest": 2, "rumour": 3,
              "lore": 3},
}
SITE_ROOMS = Band(low=2, high=5)  # a site's rooms, the last its boss's or its reward's


def area_budget(simulation: Mapping[str, Any], area_id: str) -> dict[str, int]:
    """How many of each kind ``area_id`` holds: its ``gm_guide`` row (its ``size``, and any ``counts`` it sets), else
    a medium area's."""
    row = _d(_d(_d(_d(_sections.world_model_of(simulation)).get("gm_guide")).get("areas")).get(area_id))
    counts = dict(AREA_COUNTS.get(_s(row.get("size")), AREA_COUNTS["medium"]))
    counts.update({kind: max(0, min(12, int(value))) for kind, value in _d(row.get("counts")).items()
                   if kind in AREA_KINDS and isinstance(value, int)})
    return counts


__all__ = ["AREA_COUNTS", "AREA_KINDS", "Band", "GROUP_SHARE", "LevelBudget", "SITE_ROOMS", "area_budget", "budget",
           "creature_findings", "danger", "derived", "encounter_fits"]
