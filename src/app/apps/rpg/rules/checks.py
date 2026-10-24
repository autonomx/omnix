"""Checks outside a fight (RQ-5.2; docs/rpg/design/checks.md): try something, see the roll, and fail forward.

Pure and seeded: ``check`` reads the campaign and returns the changes. The roll is d20 + the skill's rank + the
attribute's modifier + the situation's (+2 from someone who trusts the hero, -2 from someone wary of them, less the
hero's condition penalties) against the difficulty: what the world sets for the target, else moderate. The margin
decides: a strong success, a success, a success at a cost, or a failure with a consequence; a natural 20 is at
least a success and a natural 1 at most a success at a cost. Trying the same thing again on the same target, in the
same place within two hours, is harder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    CheckResolved,
    HpChanged,
    RegardChanged,
    StateChange,
)
from app.apps.rpg.rules import routines
from app.apps.rpg.rules.combat.runtime_core import deterministic_roll
from app.apps.rpg.rules.player import progression

Kind = Literal["persuade", "intimidate", "deceive", "sneak", "climb", "pick_lock", "recall_lore", "search", "notice"]
KINDS: tuple[str, ...] = ("persuade", "intimidate", "deceive", "sneak", "climb", "pick_lock", "recall_lore", "search",
                          "notice")
DIFFICULTIES = {"trivial": 5, "easy": 10, "moderate": 13, "hard": 16, "very_hard": 19, "heroic": 22}
RETRY_PENALTY, RETRY_WINDOW_TICKS = 2, 12  # the same try again, here, within two hours (a tick is 10 minutes)
MINUTES = 10
# The skill and the attribute each kind of check rests on.
_RESTS_ON = {
    "persuade": ("persuasion", "charisma"), "intimidate": ("intimidation", "strength"),
    "deceive": ("persuasion", "charisma"), "sneak": ("stealth", "dexterity"), "climb": ("athletics", "strength"),
    "pick_lock": ("stealth", "dexterity"), "recall_lore": ("investigation", "intelligence"),
    "search": ("investigation", "wisdom"), "notice": ("investigation", "wisdom"),
}
_XP_SCALE = {5: 0.2, 10: 0.5, 13: 1.0, 16: 1.5, 19: 2.0, 22: 3.0}
SKILL_XP = 10  # a success at moderate difficulty


@dataclass(frozen=True)
class CheckOutcome:
    changes: list[StateChange]
    lines: list[str]
    minutes: int = MINUTES
    band: str = ""
    record: dict[str, Any] = field(default_factory=dict)  # the roll, for the outcome card


def _band(margin: int, natural: int) -> str:
    band = "strong" if margin >= 5 else "success" if margin >= 0 else "cost" if margin >= -4 else "failure"
    if natural == 20 and band in {"cost", "failure"}:
        return "success"
    if natural == 1 and band in {"strong", "success"}:
        return "cost"
    return band


def _target(simulation: Mapping[str, Any], target_id: str) -> tuple[str, dict[str, Any]]:
    """The target's kind (person, creature, place, item, or "" for the scene) and its world record."""
    world = _d(simulation.get("world_model"))
    if target_id in _d(world.get("npcs")):
        return "person", _d(_d(world.get("npcs")).get(target_id))
    creatures = _d(_d(simulation.get("campaign_mechanics")).get("creatures"))
    if target_id in creatures:
        return "creature", _d(creatures.get(target_id))
    if target_id in _d(world.get("locations")):
        return "place", _d(_d(world.get("locations")).get(target_id))
    return ("item", {}) if target_id else ("", {})


def _difficulty(record: Mapping[str, Any], kind: str) -> int:
    set_for = record.get("check_difficulty")
    value = _d(set_for).get(kind) if isinstance(set_for, Mapping) else set_for
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return DIFFICULTIES.get(_s(value).casefold().replace(" ", "_"), DIFFICULTIES["moderate"])


def _bonus(simulation: Mapping[str, Any], kind: str, target_kind: str, target_id: str) -> tuple[int, str]:
    player = _d(simulation.get("player_state"))
    skill, attribute = _RESTS_ON[kind]
    rank = int(_d(_d(player.get("skills")).get(skill)).get("level") or 0)
    modifier = (int(_d(player.get("stats")).get(attribute) or 10) - 10) // 2
    situation = 0
    if target_kind == "person" and kind in {"persuade", "deceive", "intimidate"}:
        trust = int(_d(_d(simulation.get("relationship_state")).get(target_id)).get("trust") or 0)
        situation = 2 if trust >= 50 else -2 if trust < 0 else 0
    situation -= sum(int(_d(row).get("attack_penalty") or 0) for row in _l(player.get("conditions")))
    return rank + modifier + situation, skill


def _retried(simulation: Mapping[str, Any], kind: str, target_id: str, here: str) -> bool:
    tick = int(simulation.get("tick") or 0)
    return any(_s(_d(row).get("kind")) == kind and _s(_d(row).get("target_id")) == target_id
               and _s(_d(row).get("location_id")) == here and tick - int(_d(row).get("tick") or 0) <= RETRY_WINDOW_TICKS
               for row in _l(_d(simulation.get("checks")).get("history")))


def _name(record: Mapping[str, Any], fallback: str) -> str:
    return _s(record.get("name")) or fallback


def _consequence(simulation: Mapping[str, Any], kind: str, band: str, target_kind: str, target_id: str,
                 record: Mapping[str, Any]) -> tuple[list[StateChange], list[str], int]:
    """What the try leads to: its changes, the facts the narrator is told, and any extra minutes."""
    name = _name(record, "them")
    present = [npc for npc in routines.present_now(simulation)[1] if npc != target_id]
    people = _d(_d(simulation.get("world_model")).get("npcs"))
    won = band in {"strong", "success", "cost"}

    def regard(npc_id: str, delta: int, reason: str) -> RegardChanged:
        return RegardChanged(npc_id=npc_id, name=_name(_d(people.get(npc_id)), npc_id), delta=delta, reason=reason)

    if kind in {"persuade", "intimidate", "deceive"} and target_kind == "person":
        delta = {"persuade": {"strong": 10, "success": 5, "cost": 2, "failure": -5},
                 "intimidate": {"strong": 0, "success": -3, "cost": -5, "failure": -10},
                 "deceive": {"strong": 0, "success": 0, "cost": -2, "failure": -15}}[kind][band]
        said = {"persuade": (f"{name} is won over.", f"{name} agrees.", f"{name} agrees, grudgingly.",
                             f"{name} is not persuaded, and trusts you a little less."),
                "intimidate": (f"{name} gives way at once.", f"{name} backs down.", f"{name} backs down, resentful.",
                               f"{name} stands firm, and will remember the threat."),
                "deceive": (f"{name} believes you completely.", f"{name} believes you.",
                            f"{name} believes you, for now.", f"{name} sees through the lie.")}[kind]
        line = said[("strong", "success", "cost", "failure").index(band)]
        return ([regard(target_id, delta, f"{kind}:{band}")] if delta else []), [line], 0
    if kind in {"persuade", "intimidate", "deceive"}:  # a creature that speaks, talked to (encounters.md)
        return [], [f"The {name} gives way." if won else f"The {name} is not swayed."], 0
    if kind in {"sneak", "pick_lock"}:
        if won:
            done = "You slip by unseen." if kind == "sneak" else "The lock gives."
            return [], [done + (" It takes longer than it should." if band == "cost" else "")], MINUTES if band == "cost" else 0
        seen = "You are seen." if kind == "sneak" else "The lock jams, and the noise carries."
        return [regard(npc, -5 if kind == "sneak" else -2, f"{kind}:noticed") for npc in present if npc in people], [seen], 0
    if kind == "climb":
        if band == "failure":
            return [HpChanged(delta=-6)], ["You fall, and the ground is hard."], MINUTES
        if band == "cost":
            return [HpChanged(delta=-3)], ["You make the climb, scraped and slower than you hoped."], MINUTES
        return [], ["You make the climb."], 0
    if kind == "recall_lore":
        if not won:
            return [], ["Nothing useful comes to mind."], 0
        known = [_s(row) for row in _l(record.get("tags"))[:2]]
        weak = [", ".join(_s(alias) for alias in _l(_d(row).get("aliases"))) for row in _l(record.get("vulnerabilities"))]
        lines = [f"You recall what is told of {name}" + (f": {'; '.join(known)}." if known else ".")]
        if weak and band in {"strong", "success"}:
            lines.append(f"Its weakness: {weak[0]}.")
        if target_kind == "person" and _s(record.get("role")):
            lines.append(f"{name} is known as {_s(record.get('role'))}.")
        return [], lines, 0
    # search, notice: what is here to be found
    here = routines.hero_location(simulation)
    if not won:
        return [], ["You find nothing of note."], 0
    ground = [_s(_d(item).get("name")) for item in _l(_d(simulation.get("world_items")).get(here)) if _s(_d(item).get("name"))]
    seen = routines.described(simulation, routines.present_now(simulation)[1], routines.clock(simulation))
    lines = []
    if ground:
        lines.append(f"Lying here: {', '.join(ground)}.")
    if kind == "notice" and seen:
        lines.append(f"You notice: {', '.join(seen)}.")
    return [], lines or ["You look carefully, and there is nothing hidden here."], 0


def check(simulation: Mapping[str, Any], kind: str, target_id: str = "", *, turn_key: str = "",
          difficulty: int | None = None) -> CheckOutcome:
    """One check: the roll against the difficulty (the target's, or what the situation sets: ``difficulty``), and what
    it leads to."""
    target_kind, record = _target(simulation, target_id)
    here = routines.hero_location(simulation)
    difficulty = ((_difficulty(record, kind) if difficulty is None else int(difficulty))
                  + (RETRY_PENALTY if _retried(simulation, kind, target_id, here) else 0))
    bonus, skill = _bonus(simulation, kind, target_kind, target_id)
    natural = deterministic_roll(f"check.{kind}.{target_id or here}.{turn_key}", 1, 20)
    total = natural + bonus
    margin = total - difficulty
    band = _band(margin, natural)
    changes, lines, extra = _consequence(simulation, kind, band, target_kind, target_id, record)
    words = {"strong": "a strong success", "success": "a success", "cost": "a success at a cost", "failure": "a failure"}
    roll_line = (f"You try to {kind.replace('_', ' ')}"
                 + (f" ({_name(record, target_id)})" if target_id else "")
                 + f": d20 {natural} {'+' if bonus >= 0 else '-'} {abs(bonus)} = {total} against {difficulty}, "
                   f"{words[band]}.")
    if band in {"strong", "success"}:  # a success teaches the skill, and earns the hero experience (progression.md)
        gained, xp_lines = progression.skill_gain(simulation, skill, max(1, round(SKILL_XP * _XP_SCALE.get(
            difficulty, difficulty / 13))))
        earned, hero_lines = progression.gain(simulation, progression.check_xp(difficulty))
        changes, lines = [*changes, *gained, *earned], [*lines, *xp_lines, *hero_lines]
    result = {"kind": kind, "target_id": target_id, "location_id": here, "natural": natural, "bonus": bonus,
              "total": total, "difficulty": difficulty, "margin": margin, "band": band, "skill": skill}
    return CheckOutcome([CheckResolved(**result), *changes], [roll_line, *lines], minutes=MINUTES + extra, band=band,
                        record=result)


__all__ = ["DIFFICULTIES", "KINDS", "CheckOutcome", "check"]
