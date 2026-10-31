"""The hero's progression (RQ-5.3; docs/rpg/design/progression.md): one experience curve, and each level's choice.

Experience comes from fights won, quests finished, checks passed and first visits to the world's places. Rising from
level n takes 100 x n more (level 2 at 100 in all, 3 at 300, 4 at 600, 5 at 1,000), and each level brings 5 more
health (and the constitution modifier) and a choice that waits until it is made, never blocking play: +2 to one
attribute, a new ability the hero's level allows, or a rank in two skills. Skills rise with use, from rank 0 to 5,
50 x (rank + 1) to the next. Pure: it returns the changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    ExperienceGained,
    LevelChoiceMade,
    LevelReached,
    SkillProgressed,
    StateChange,
)
from app.apps.rpg.foundation.state import access as _sections

XP_PER_LEVEL = 100
HP_PER_LEVEL = 5
ATTRIBUTE_RAISE = 2
SKILL_RANK_MAX = 5
DISCOVERY_XP = 15  # the first visit to a named place
QUEST_STEP_XP = 50  # a quest that names no experience pays this for each of its places (tuned, RQ-5.3)
CHECK_XP = ((22, 35), (16, 20), (13, 10), (0, 5))  # a check passed: by difficulty, heroic to easy
ATTRIBUTES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
PROMPT = ('Choose how you grow: raise an attribute by 2 ("raise strength"), learn a new ability ("learn ...") or '
          'improve two skills ("improve stealth and archery").')


@dataclass(frozen=True)
class Growth:
    changes: list[StateChange]
    lines: list[str]
    refused: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


def xp_to_next(level: int) -> int:
    return XP_PER_LEVEL * max(1, int(level))


def skill_xp_to_next(rank: int) -> int:
    return 50 * (max(0, int(rank)) + 1)


def check_xp(difficulty: int) -> int:
    return next((amount for floor, amount in CHECK_XP if difficulty >= floor), CHECK_XP[-1][1])  # below all: the least


def _player(simulation: Mapping[str, Any]) -> dict[str, Any]:
    return _d(_sections.player_state_of(simulation))


def gain(simulation: Mapping[str, Any], amount: int) -> tuple[list[StateChange], list[str]]:
    """``amount`` experience for the hero, and the levels it brings."""
    if amount <= 0:
        return [], []
    player = _player(simulation)
    level = max(1, int(player.get("level") or 1))
    xp = int(player.get("xp") or 0) + amount
    risen = 0
    while xp >= xp_to_next(level):
        xp, level, risen = xp - xp_to_next(level), level + 1, risen + 1
    changes: list[StateChange] = [ExperienceGained(amount=amount)]
    lines = [f"You gain {amount} experience."]
    if risen:
        constitution = (int(_d(player.get("stats")).get("constitution") or 10) - 10) // 2
        changes.append(LevelReached(
            level=level, xp=xp, xp_to_next=xp_to_next(level),
            unspent_points=int(player.get("unspent_points") or 0),
            unspent_skill_points=int(player.get("unspent_skill_points") or 0),
            choices_pending=int(player.get("level_choices_pending") or 0) + risen,
            max_hp_gain=risen * max(1, HP_PER_LEVEL + constitution)))
        lines += [f"You reach level {level}.", PROMPT]
    return changes, lines


def skill_gain(simulation: Mapping[str, Any], skill: str, amount: int) -> tuple[list[StateChange], list[str]]:
    """``amount`` experience in one of the hero's skills, and the ranks it brings (up to 5)."""
    skills = _d(_player(simulation).get("skills"))
    if skill not in skills or amount <= 0:
        return [], []
    row = _d(skills.get(skill))
    rank, xp = int(row.get("level") or 0), int(row.get("xp") or 0)
    if rank >= SKILL_RANK_MAX:
        return [], []
    xp += amount
    name = skill.replace("_", " ")
    lines = [f"Your {name} earns {amount} experience."]
    while rank < SKILL_RANK_MAX and xp >= skill_xp_to_next(rank):
        xp, rank = xp - skill_xp_to_next(rank), rank + 1
        lines.append(f"{name.capitalize()} rises to rank {rank}.")
    xp = 0 if rank >= SKILL_RANK_MAX else xp
    return [SkillProgressed(skill_id=skill, level=rank, xp=xp, xp_to_next=skill_xp_to_next(rank))], lines


def _learnable(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    state = _d(document.get("state"))
    unlocked = {_s(ability_id) for ability_id in _l(_d(state.get("ability_state")).get("unlocked"))}
    level = max(1, int(_player(_d(_sections.simulation_state_of(document))).get("level") or 1))
    return [_d(row) for row in _l(_d(state.get("ability_tree")).get("abilities"))
            if _s(_d(row).get("ability_id")) not in unlocked and int(_d(row).get("level_required") or 1) <= level
            and all(_s(need) in unlocked for need in _l(_d(row).get("prerequisites")))]


def choose(document: Mapping[str, Any], choice: str) -> Growth:
    """The level's choice the reading names (EV-9), or a card's: "attribute:<name>" raised, "ability:<id>" learned, or
    "skills:<one>,<other>" each a rank higher. Anything else asks again."""
    simulation = _d(_sections.simulation_state_of(document))
    player = _player(simulation)
    if int(player.get("level_choices_pending") or 0) <= 0:
        return Growth([], ["You have no level's choice to make yet."], refused=True)
    kind, _, value = choice.partition(":")
    attribute = value if kind == "attribute" and value in ATTRIBUTES else ""
    if attribute:
        stats = _d(player.get("stats"))
        value = int(stats.get(attribute) or 10) + ATTRIBUTE_RAISE
        return Growth([LevelChoiceMade(choice="attribute", attribute=attribute, value=value)],
                      [f"Your {attribute} rises to {value}."], detail={"choice": "attribute", "attribute": attribute})
    learnable = _learnable(document)
    named = [row for row in learnable if kind == "ability" and _s(row.get("ability_id")) == value]
    if named:
        ability = named[0]
        return Growth([LevelChoiceMade(choice="ability", ability_id=_s(ability.get("ability_id")))],
                      [f"You learn {_s(ability.get('name'))}."], detail={"choice": "ability",
                                                                        "ability_id": _s(ability.get("ability_id"))})
    skills = _d(player.get("skills"))
    asked = value.split(",") if kind == "skills" else []
    chosen = [skill for skill in dict.fromkeys(asked)
              if skill in skills and int(_d(skills.get(skill)).get("level") or 0) < SKILL_RANK_MAX][:2]
    if len(chosen) == 2:
        return Growth([LevelChoiceMade(choice="skills", skills=tuple(chosen))],
                      [f"Your {chosen[0]} and {chosen[1]} each rise a rank."], detail={"choice": "skills",
                                                                                     "skills": chosen})
    names = ", ".join(_s(row.get("name")) for row in learnable[:4])
    return Growth([], [PROMPT + (f" Abilities you could learn: {names}." if names else "")], refused=True)


__all__ = ["ATTRIBUTES", "DISCOVERY_XP", "PROMPT", "QUEST_STEP_XP", "SKILL_RANK_MAX", "Growth", "check_xp", "choose",
           "gain", "skill_gain", "skill_xp_to_next", "xp_to_next"]
