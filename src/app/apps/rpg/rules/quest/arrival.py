"""A quest that names its places advances as the hero reaches them, and pays its rewards when the last is reached.

The rule reads the campaign and says what happens as changes (RQ-2.1, RQ-2.5): the place reached, the quest
completed, and its rewards, coin and items, for the reducer to apply.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    ItemAdded,
    PurseChanged,
    QuestPlaceReached,
    QuestStatusChanged,
    StateChange,
)
from app.apps.rpg.foundation.state import access as _sections

_COINS = {"gold": 100, "silver": 10, "copper": 1}


def _reward_coins(rewards: list[str]) -> dict[str, int]:
    coins = {"gold": 0, "silver": 0, "copper": 0}
    for reward in rewards:
        for amount, coin in re.findall(r"(\d+)\s*(gold|silver|copper)", reward.lower()):
            coins[coin] += int(amount)
    return coins


def _reward_items(rewards: list[str], world_items: Mapping[str, Mapping[str, Any]]) -> list[ItemAdded]:
    items = []
    for reward in rewards:
        if not reward.startswith("item:"):
            continue
        item = _d(world_items.get(reward))
        items.append(ItemAdded(item_id=reward, name=_s(item.get("name")) or reward.rsplit(":", 1)[-1].replace("-", " ").title(),
                               category=_s(item.get("type")) or "misc",
                               fields={"description": _s(item.get("effect") or item.get("description")),
                                       **({"equipment": _d(item.get("equipment"))} if _d(item.get("equipment")) else {})}))
    return items


def quest_rewards(simulation_state: Mapping[str, Any], quest: Mapping[str, Any]) -> tuple[list[StateChange], str]:
    """A completed quest's rewards (its coin, items and experience: what it names, else 50 for each of its steps or
    places, progression.md), and how to say what the hero receives."""
    from app.apps.rpg.rules.player import progression

    world_items = {_s(item.get("id")): _d(item) for item in _l(_d(_sections.world_model_of(simulation_state)).get("items"))
                   if isinstance(item, Mapping)}
    rewards = [_s(reward) for reward in _l(quest.get("rewards"))]
    coins = _reward_coins(rewards)
    changes: list[StateChange] = []
    copper = sum(amount * _COINS[coin] for coin, amount in coins.items())
    if copper:
        changes.append(PurseChanged(delta_copper=copper, reason=f"quest reward: {_s(quest.get('title'))}"))
    items = _reward_items(rewards, world_items)
    changes.extend(items)
    named = sum(int(amount) for reward in rewards for amount in re.findall(r"(\d+)\s*(?:xp|experience)", reward.lower()))
    stages = len(_l(quest.get("steps"))) or len(_l(quest.get("locations")))
    gained, xp_lines = progression.gain(simulation_state, named or progression.QUEST_STEP_XP * max(1, stages))
    received = [*(f"{amount} {coin}" for coin, amount in coins.items() if amount), *(item.name for item in items)]
    said = " ".join([*([f"You receive {', '.join(received)}."] if received else []), *xp_lines])
    return [*changes, *gained], said


def arrival_changes(simulation_state: Mapping[str, Any], location_id: str, *,
                    discovery_xp: int = 0) -> tuple[list[StateChange], list[str]]:
    """What reaching ``location_id`` does to the hero's active quests, and how to say it; the experience the arrival
    earns (a quest finished, and ``discovery_xp`` for a first visit) is gained at once, on the one curve."""
    from app.apps.rpg.rules.player import progression

    earned = discovery_xp
    world_items = {_s(item.get("id")): _d(item) for item in _l(_d(_sections.world_model_of(simulation_state)).get("items"))
                   if isinstance(item, Mapping)}
    changes: list[StateChange] = []
    lines: list[str] = []
    for quest in _l(_d(_sections.quest_state_of(simulation_state)).get("quests")):
        quest = _d(quest)
        quest_id = _s(quest.get("quest_id") or quest.get("id"))
        places = [_s(place) for place in _l(quest.get("locations"))]
        visited = [_s(place) for place in _l(quest.get("visited_locations"))]
        if (not quest_id or quest.get("status") != "active" or location_id not in places or location_id in visited
                or _l(quest.get("steps"))):  # a quest of steps advances by them (progress.py)
            continue
        changes.append(QuestPlaceReached(quest_id=quest_id, location_id=location_id))
        title = _s(quest.get("title")) or quest_id
        if set(places) <= {*visited, location_id}:
            rewards = [_s(reward) for reward in _l(quest.get("rewards"))]
            changes.append(QuestStatusChanged(quest_id=quest_id, status="completed"))
            from app.apps.rpg.rules.quest.progress import giver_thanks

            changes.extend(giver_thanks(simulation_state, quest))
            coins = _reward_coins(rewards)
            copper = sum(amount * _COINS[coin] for coin, amount in coins.items())
            if copper:
                changes.append(PurseChanged(delta_copper=copper, reason=f"quest reward: {title}"))
            items = _reward_items(rewards, world_items)
            changes.extend(items)
            received = [*(f"{amount} {coin}" for coin, amount in coins.items() if amount), *(item.name for item in items)]
            lines.append(f"Quest complete: {title}." + (f" You receive {', '.join(received)}." if received else ""))
            # The experience the quest names, else a hundred for each of its places (progression.md).
            named = sum(int(amount) for reward in rewards
                        for amount in re.findall(r"(\d+)\s*(?:xp|experience)", reward.lower()))
            earned += named or progression.QUEST_STEP_XP * max(1, len(places))
        else:
            lines.append(f"Progress on {title}: {len(visited) + 1} of {len(places)} places reached.")
    gained, xp_lines = progression.gain(simulation_state, earned)
    return [*changes, *gained], [*lines, *xp_lines]


__all__ = ["arrival_changes", "quest_rewards"]
