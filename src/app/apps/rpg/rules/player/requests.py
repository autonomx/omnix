"""What the hero asks of themselves and their party (RQ-2.5): taking on a quest, practising a skill, asking where
they stand, and who travels with them.

Pure rules: they read the campaign and say what happens as changes, and the facts to tell.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    CompanionJoined,
    CompanionLeft,
    CompanionOrdered,
    QuestStatusChanged,
    StateChange,
)

PRACTICE_XP = 5  # an hour's practice, on the skill curve (progression.md)
PARTY_SIZE = 3
_STATUS_TOPICS = {
    "progress": re.compile(r"\b(level|experience|xp|progress|character)\b"),
    "inventory": re.compile(r"\b(inventory|pack|bag|belongings|purse|carry(?:ing)?|gear|have|money|coin|gold)\b"),
    "quests": re.compile(r"\b(quests?|journal|objectives?)\b"),
    "skills": re.compile(r"\b(skills?|training)\b"),
    "health": re.compile(r"\b(health|hurt|wounds?|hp)\b"),
}
_ORDERS = (("keep watch", "watch"), ("stand watch", "watch"), ("stand guard", "guard"), ("keep guard", "guard"),
           ("guard", "guard"), ("wait here", "stay"), ("stay", "stay"), ("hold", "stay"), ("follow", "follow"),
           ("scout", "scout"), ("protect", "guard"), ("cover", "guard"), ("take point", "scout"))


@dataclass(frozen=True)
class RequestOutcome:
    changes: list[StateChange] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    refused: bool = False
    minutes: int = 10


def _quests(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_d(quest) for quest in _l(_d(simulation.get("quest_state")).get("quests"))]


def _quest_id(quest: Mapping[str, Any]) -> str:
    return _s(quest.get("quest_id") or quest.get("id"))


def accept_quest(simulation: Mapping[str, Any], quest_id: str) -> RequestOutcome:
    quests = _quests(simulation)
    quest = next((row for row in quests if _quest_id(row) == quest_id), None)
    if quest is None:
        available = [row for row in quests if row.get("status") == "available"]
        quest = available[0] if len(available) == 1 else None
    if quest is None:
        return RequestOutcome(lines=["No such quest is offered to you."], refused=True, minutes=0)
    if quest.get("status") != "available":
        # A side quest offered again under its title (a pressure's next, quests.md): the offer is the one meant.
        quest = next((row for row in quests if row.get("status") == "available"
                      and _s(row.get("title")) == _s(quest.get("title"))), quest)
    title = _s(quest.get("title")) or _quest_id(quest)
    status = _s(quest.get("status"))
    if status in {"completed", "failed"}:
        return RequestOutcome(lines=[f"{title} is already {status}."], refused=True, minutes=0)
    if status == "active":
        return RequestOutcome(lines=[f"{title} is already among your active quests."], refused=True, minutes=0)
    objective = _s(quest.get("objective"))
    return RequestOutcome([QuestStatusChanged(quest_id=_quest_id(quest), status="active")],
                          [f"You take on the quest {title}" + (f": {objective}." if objective else ".")])


def practise(simulation: Mapping[str, Any], skill_id: str) -> RequestOutcome:
    skill_id = skill_id.removeprefix("skill:")
    skills = _d(_d(simulation.get("player_state")).get("skills"))
    if skill_id not in skills:
        return RequestOutcome(lines=["You have no such skill to practise."], refused=True, minutes=0)
    from app.apps.rpg.rules.player.progression import SKILL_RANK_MAX, skill_gain

    name = skill_id.replace("_", " ")
    if int(_d(skills.get(skill_id)).get("level") or 0) >= SKILL_RANK_MAX:
        return RequestOutcome(lines=[f"Your {name} is as good as practice can make it."], refused=True, minutes=0)
    changes, lines = skill_gain(simulation, skill_id, PRACTICE_XP)
    said = [f"Your practice earns {PRACTICE_XP} experience in {name}.", *lines[1:]]
    return RequestOutcome(changes, said, minutes=60)


def _count(item: Mapping[str, Any]) -> int:
    return int(item.get("qty") or item.get("quantity") or 1)


def _coins(currency: Mapping[str, Any]) -> str:
    coins = [f"{int(currency.get(coin) or 0)} {coin}" for coin in ("gold", "silver", "copper") if int(currency.get(coin) or 0)]
    return ", ".join(coins) or "no coin"


def status(simulation: Mapping[str, Any], text: str) -> RequestOutcome:
    """Where the hero stands, from the campaign, when they ask: nothing changes and no time passes."""
    lowered = text.casefold()
    topics = [topic for topic, pattern in _STATUS_TOPICS.items() if pattern.search(lowered)] or ["inventory", "health"]
    player = _d(simulation.get("player_state"))
    lines = []
    if "health" in topics:
        hp = _d(_d(player.get("resources")).get("hp"))
        conditions = [_s(_d(condition).get("kind")) for condition in _l(player.get("conditions"))]
        lines.append(f"You have {int(hp.get('current') or 0)} of {int(hp.get('max') or 0)} health"
                     + (f"; you are {' and '.join(conditions)}." if conditions else "."))
    if "progress" in topics:
        lines.append(f"You are level {int(player.get('level') or 1)}, with {int(player.get('xp') or 0)} of "
                     f"{int(player.get('xp_to_next') or 100)} experience toward the next level.")
    if "inventory" in topics:
        store = _d(player.get("inventory_state"))
        items = [_d(item) for item in _l(store.get("items")) if _d(item).get("name")]
        carried = ", ".join(f"{_count(item)} {item['name']}" if _count(item) > 1 else _s(item["name"]) for item in items)
        lines.append(f"You carry {carried or 'nothing'}; your purse holds "
                     f"{_coins(_d(store.get('currency') or player.get('currency')))}.")
    if "quests" in topics:
        quests = _quests(simulation)
        active = [f"{_s(quest.get('title'))} ({_s(quest.get('objective'))})" if quest.get("objective") else _s(quest.get("title"))
                  for quest in quests if quest.get("status") == "active"]
        available = [_s(quest.get("title")) for quest in quests if quest.get("status") == "available"]
        lines.append(f"Active quests: {'; '.join(active)}." if active else "You have no active quest.")
        if available:
            lines.append(f"Quests you could take on: {', '.join(available)}.")
    if "skills" in topics:
        trained = [f"{skill.replace('_', ' ')} level {int(_d(row).get('level') or 0)} "
                   f"({int(_d(row).get('xp') or 0)} of {int(_d(row).get('xp_to_next') or 25)} XP)"
                   for skill, row in _d(player.get("skills")).items()
                   if int(_d(row).get("xp") or 0) or int(_d(row).get("level") or 0)]
        lines.append(f"Skills in training: {'; '.join(trained)}." if trained else "None of your skills has progressed yet.")
    return RequestOutcome(lines=lines, minutes=0)


def _companions(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [_d(row) for row in _l(_d(_d(simulation.get("player_state")).get("party_state")).get("companions"))]


def _person(simulation: Mapping[str, Any], npc_id: str) -> dict[str, Any]:
    world = _d(simulation.get("world_model"))
    return {**_d(_d(world.get("npcs")).get(npc_id)), **_d(_d(simulation.get("npc_index")).get(npc_id))}


def join(simulation: Mapping[str, Any], npc_id: str) -> RequestOutcome:
    person = _person(simulation, npc_id)
    name = _s(person.get("name")) or npc_id
    present = set(_l(_d(simulation.get("present_npc_state")).get("present_npc_ids")))
    companions = _companions(simulation)
    if any(row.get("npc_id") == npc_id for row in companions):
        return RequestOutcome(lines=[f"{name} already travels with you."], refused=True, minutes=0)
    if npc_id not in present:
        return RequestOutcome(lines=[f"{name} is not here to ask."], refused=True, minutes=0)
    if len(companions) >= PARTY_SIZE:
        return RequestOutcome(lines=[f"Your party is full; {name} cannot join it."], refused=True, minutes=0)
    return RequestOutcome([CompanionJoined(npc_id=npc_id, name=name, role=_s(person.get("role")) or "companion")],
                          [f"{name} joins your party."])


def leave(simulation: Mapping[str, Any], npc_id: str) -> RequestOutcome:
    companion = next((row for row in _companions(simulation) if row.get("npc_id") == npc_id), None)
    name = _s(_person(simulation, npc_id).get("name")) or npc_id
    if companion is None:
        return RequestOutcome(lines=[f"{name} is not in your party."], refused=True, minutes=0)
    return RequestOutcome([CompanionLeft(npc_id=npc_id)], [f"{_s(companion.get('name')) or name} leaves your party."])


def order(simulation: Mapping[str, Any], npc_id: str, text: str) -> RequestOutcome | None:
    """A standing order to a companion; ``None`` when the person spoken to is not one (then it is talk)."""
    companion = next((row for row in _companions(simulation) if row.get("npc_id") == npc_id), None)
    if companion is None:
        return None
    lowered = text.casefold()
    words, stance = next(((words, stance) for words, stance in _ORDERS if words in lowered), ("follow", "follow"))
    name = _s(companion.get("name")) or npc_id
    return RequestOutcome([CompanionOrdered(npc_id=npc_id, order=words, stance=stance)],
                          [f"{name} will {words}." if stance != "follow" else f"{name} follows your lead."], minutes=0)


__all__ = ["RequestOutcome", "accept_quest", "join", "leave", "order", "practise", "status"]
