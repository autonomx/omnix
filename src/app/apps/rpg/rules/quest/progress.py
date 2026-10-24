"""Quests of several steps, with branches, deadlines and failure (RQ-5.4; docs/rpg/design/quests.md).

A world may author a quest's ``steps``: stages done in order, each a set of conditions that must all hold, or
``any_of`` alternatives (the branches: either way completes the stage). A condition is one of ``reach`` a place,
``talk`` to someone, ``hold`` an item, ``defeat`` a creature (``count`` of them), or pass a ``check`` (its kind, and
a target when named). Progress is judged after every turn, against the campaign as the turn leaves it and the turn's
own changes: a stage done advances the quest, the last one completes it and pays its rewards. A quest with a
``deadline_hours`` fails when the time since it was taken up runs out, and its giver trusts the hero less. A quest
with no steps advances by its places, as before (``arrival.py``). Pure: it returns the changes.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    CheckResolved,
    CombatAdvanced,
    DialogueExchanged,
    QuestProgressed,
    QuestStatusChanged,
    QuestStepCompleted,
    RegardChanged,
    StateChange,
)
from app.apps.rpg.rules import routines

FAILED_REGARD = -10  # a quest failed costs its giver's trust (quests.md)


def victories(applied: Sequence[StateChange]) -> dict[str, int]:
    """The creatures this turn's won fight felled, by their bestiary id."""
    felled: dict[str, int] = {}
    for change in applied:
        combat = change.combat_state if isinstance(change, CombatAdvanced) else {}
        if combat.get("ended_reason") != "enemy_side_defeated":
            continue
        for row in _d(combat.get("participants")).values():
            row = _d(row)
            if _s(row.get("side")) == "enemy" and _s(row.get("kind")) != "person" and int(row.get("hp") or 0) <= 0:
                key = _s(row.get("definition_id"))
                felled[key] = felled.get(key, 0) + 1
    return felled


def _holds(condition: Mapping[str, Any], simulation: Mapping[str, Any], applied: Sequence[StateChange],
           counts: Mapping[str, int]) -> bool:
    if condition.get("reach"):
        return routines.hero_location(simulation) == _s(condition["reach"])
    if condition.get("talk"):
        # ``about``: words the hero's line must touch (asking Bran about the weather is not asking about the rumor).
        about = [_s(word).casefold() for word in (_l(condition.get("about")) or [condition.get("about")]) if _s(word)]
        return any(isinstance(change, DialogueExchanged) and change.npc_id == _s(condition["talk"])
                   and (not about or any(word in change.player_line.casefold() for word in about))
                   for change in applied)
    if condition.get("hold"):
        wanted = _s(condition["hold"])
        return any(_s(_d(item).get("item_id") or _d(item).get("id")) == wanted
                   for item in _l(_d(_d(simulation.get("player_state")).get("inventory_state")).get("items")))
    if condition.get("defeat"):
        return counts.get(_s(condition["defeat"]), 0) >= max(1, int(condition.get("count") or 1))
    if condition.get("check"):
        target = _s(condition.get("target"))
        return any(isinstance(change, CheckResolved) and change.kind == _s(condition["check"])
                   and change.band != "failure" and (not target or change.target_id == target) for change in applied)
    return False


def _alternatives(step: Mapping[str, Any]) -> list[list[dict[str, Any]]]:
    """A step's ways to be done: each a list of conditions that must all hold."""
    if _l(step.get("any_of")):
        return [[_d(row) for row in _l(way)] if isinstance(way, list) else [_d(way)] for way in _l(step["any_of"])]
    return [[_d(row) for row in _l(step.get("all_of") or step.get("conditions"))]]


def quest_progress(simulation: Mapping[str, Any], applied: Sequence[StateChange],
                   rewards: Any) -> tuple[list[StateChange], list[str]]:
    """What this turn did to the hero's stepped quests: stages done, quests completed (``rewards(quest)`` pays
    them) or failed, and how to say it."""
    changes: list[StateChange] = []
    lines: list[str] = []
    felled = victories(applied)
    now = routines.clock(simulation)
    people = _d(_d(simulation.get("world_model")).get("npcs"))
    for quest in map(_d, _l(_d(simulation.get("quest_state")).get("quests"))):
        steps = [_d(step) for step in _l(quest.get("steps"))]
        quest_id = _s(quest.get("quest_id") or quest.get("id"))
        if not steps or quest.get("status") != "active" or not quest_id:
            continue
        title = _s(quest.get("title")) or quest_id
        deadline = quest.get("deadline_hours")
        accepted = quest.get("accepted_at_minute")
        if deadline and accepted is not None and now >= int(accepted) + int(float(deadline) * 60):
            changes.append(QuestStatusChanged(quest_id=quest_id, status="failed"))
            lines.append(f"{title} has failed: the time for it ran out.")
            giver = _s(quest.get("giver_id") or quest.get("offered_by"))
            if giver in people:
                changes.append(RegardChanged(npc_id=giver, name=_s(_d(people[giver]).get("name")) or giver,
                                             delta=FAILED_REGARD, reason=f"failed:{quest_id}"))
            continue
        progress = _d(quest.get("progress"))
        stage = int(progress.get("stage") or 0)
        counts = {key: int(value) for key, value in _d(progress.get("counts")).items()}
        for key, amount in felled.items():
            counts[key] = counts.get(key, 0) + amount
        if counts != {key: int(value) for key, value in _d(progress.get("counts")).items()}:
            changes.append(QuestProgressed(quest_id=quest_id, counts=counts))
        while stage < len(steps):
            ways = _alternatives(steps[stage])
            branch = next((index for index, way in enumerate(ways)
                           if way and all(_holds(condition, simulation, applied, counts) for condition in way)), None)
            if branch is None:
                break
            stage += 1
            following = _s(steps[stage].get("summary")) if stage < len(steps) else ""
            changes.append(QuestStepCompleted(quest_id=quest_id, stage=stage, step_id=_s(steps[stage - 1].get("id")),
                                              branch=branch if len(ways) > 1 else None, next_objective=following))
            done = _s(steps[stage - 1].get("summary")) or "a step"
            lines.append(f"{title}: {done}" + (f". Next: {following}." if following else "."))
        if stage >= len(steps) and stage > int(progress.get("stage") or 0):
            changes.append(QuestStatusChanged(quest_id=quest_id, status="completed"))
            paid, said = rewards(quest)
            changes.extend(paid)
            lines.append(f"Quest complete: {title}." + (f" {said}" if said else ""))
    return changes, lines


__all__ = ["FAILED_REGARD", "quest_progress", "victories"]
