"""Quests of several steps, with branches, deadlines and failure (RQ-5.4; docs/rpg/design/quests.md).

A world may author a quest's ``steps``: stages done in order, each a set of conditions that must all hold, or
``any_of`` alternatives (the branches: either way completes the stage; one written ``{"all_of": [...], "told": ...}``
says what came of it, told when it is taken). A condition is one of ``reach`` a place,
``talk`` to someone (with ``about``: about what the step asks, which the reading judges by meaning and names as the
step it answers, EV-3), ``hold`` an item, ``defeat`` a creature (``count`` of them), pass a ``check`` (its kind, and
a target when named), or have a ``companion`` (someone named, or ``anyone``) in the party. Progress is judged after every turn, against the campaign as the turn leaves it and the turn's
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
from app.apps.rpg.foundation.state import access as _sections

FAILED_REGARD = -10  # a quest failed costs its giver's trust (quests.md)
ANYONE = "anyone"  # a ``companion`` condition any companion meets
DONE_REGARD = 10  # and one done earns it (the playtest: the captain's contract finished, her regard unmoved)


def giver_thanks(simulation: Mapping[str, Any], quest: Mapping[str, Any]) -> list[StateChange]:
    """The regard a finished quest earns from whoever gave it, when they are one of the world's people."""
    people = _d(_d(_sections.world_model_of(simulation)).get("npcs"))
    giver = _s(quest.get("giver_id") or quest.get("offered_by"))
    if giver not in people:
        return []
    quest_id = _s(quest.get("quest_id") or quest.get("id"))
    return [RegardChanged(npc_id=giver, name=_s(_d(people[giver]).get("name")) or giver, delta=DONE_REGARD,
                          reason=f"completed:{quest_id}")]


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


def step_address(quest_id: str, step_id: str, way: int) -> str:
    """How a reading names the step a line answers, and the way of it (EV-3)."""
    return f"{quest_id}|{step_id}|{way}"


def _holds(condition: Mapping[str, Any], simulation: Mapping[str, Any], applied: Sequence[StateChange],
           counts: Mapping[str, int], address: str = "") -> bool:
    if condition.get("reach"):
        return routines.hero_location(simulation) == _s(condition["reach"])
    if condition.get("talk"):
        # ``about``: the step asks something particular of them (asking the innkeeper about the weather is not asking
        # about the rumor): the line answers it when its reading named this step and way, and the plan accepted it
        # (EV-3; no word of the line is matched).
        about = [_s(word) for word in (_l(condition.get("about")) or [condition.get("about")]) if _s(word)]
        return any(isinstance(change, DialogueExchanged) and change.npc_id == _s(condition["talk"])
                   and (not about or change.step == address)
                   for change in applied)
    if condition.get("hold"):
        wanted = _s(condition["hold"])
        return any(_s(_d(item).get("item_id") or _d(item).get("id")) == wanted
                   for item in _l(_d(_sections.inventory_state_of(_d(_sections.player_state_of(simulation)))).get("items")))
    if condition.get("defeat"):
        return counts.get(_s(condition["defeat"]), 0) >= max(1, int(condition.get("count") or 1))
    if condition.get("companion"):
        party, who = routines.companions(simulation), _s(condition["companion"])
        return bool(party) if who == ANYONE else who in party
    if condition.get("check"):
        target = _s(condition.get("target"))
        return any(isinstance(change, CheckResolved) and change.kind == _s(condition["check"])
                   and change.band != "failure" and (not target or change.target_id == target) for change in applied)
    return False


def step_ways(step: Mapping[str, Any]) -> list[tuple[list[dict[str, Any]], str]]:
    """A step's ways to be done: each the conditions that must all hold, and what is told when it is taken."""
    if _l(step.get("any_of")):
        ways = []
        for way in _l(step["any_of"]):
            if isinstance(way, list):
                ways.append(([_d(row) for row in way], ""))
            elif isinstance(way, Mapping) and "all_of" in way:  # a way with its own telling
                ways.append(([_d(row) for row in _l(way.get("all_of"))], _s(way.get("told"))))
            else:
                ways.append(([_d(way)], ""))
        return ways
    return [([_d(row) for row in _l(step.get("all_of") or step.get("conditions"))], _s(step.get("told")))]


def quest_progress(simulation: Mapping[str, Any], applied: Sequence[StateChange],
                   rewards: Any) -> tuple[list[StateChange], list[str]]:
    """What this turn did to the hero's stepped quests: stages done, quests completed (``rewards(quest)`` pays
    them) or failed, and how to say it."""
    changes: list[StateChange] = []
    lines: list[str] = []
    felled = victories(applied)
    now = routines.clock(simulation)
    people = _d(_d(_sections.world_model_of(simulation)).get("npcs"))
    for quest in map(_d, _l(_d(_sections.quest_state_of(simulation)).get("quests"))):
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
            ways = step_ways(steps[stage])
            step_id = _s(steps[stage].get("id"))
            branch = next((index for index, (way, _) in enumerate(ways)
                           if way and all(_holds(condition, simulation, applied, counts,
                                                 step_address(quest_id, step_id, index)) for condition in way)), None)
            if branch is None:
                break
            told = ways[branch][1]
            stage += 1
            following = _s(steps[stage].get("summary")) if stage < len(steps) else ""
            changes.append(QuestStepCompleted(quest_id=quest_id, stage=stage, step_id=_s(steps[stage - 1].get("id")),
                                              branch=branch if len(ways) > 1 else None, next_objective=following))
            done = _s(steps[stage - 1].get("summary")) or "a step"
            if told:  # what came of the way taken (an ending's branch: the gate made a guarded bridge)
                lines.append(told)
            if stage < len(steps):  # the last step is told by the quest's completion
                lines.append(f"{title}: {done}. Next: {following}.")
        if stage >= len(steps) and stage > int(progress.get("stage") or 0):
            changes.append(QuestStatusChanged(quest_id=quest_id, status="completed"))
            paid, said = rewards(quest)
            changes.extend(paid)
            changes.extend(giver_thanks(simulation, quest))
            lines.append(f"Quest complete: {title}." + (f" {said}" if said else ""))
    return changes, lines


def fold_quest_offer(document: Mapping[str, Any], payload: Mapping[str, Any]):
    """A quest the game master offers (EV-0): one of the world's, not in the log yet, open to the hero by its facts;
    offered by its giver (or the world), within the day's limit."""
    from app.apps.rpg.foundation.state.changes import QuestOffered
    from app.apps.rpg.foundation.state.proposals import Folded, refused
    from app.apps.rpg.rules.consequences import quest_open
    from app.apps.rpg.rules.direction import allows, counted

    simulation = _d(_sections.simulation_state_of(document))
    quest_id = _s(payload.get("quest_id"))
    quest = _d(_d(_d(_sections.world_model_of(simulation)).get("quests")).get(quest_id))
    logged = {_s(_d(row).get("quest_id") or _d(row).get("id")) for row in _l(_d(_sections.quest_state_of(simulation)).get("quests"))}
    if not quest:
        return refused(f"no quest {quest_id!r} in this world")
    if quest_id in logged:
        return refused("the hero already has it")
    if not quest_open(simulation, quest):
        return refused("its facts close it")
    limit = allows(simulation, "quest")
    if limit:
        return refused(limit)
    giver = _s(quest.get("giver_id")) or "world"
    return Folded([QuestOffered(quest_id=quest_id, npc_id=giver, quest={**quest, "status": "available"}),
                   counted(simulation, "quest")])


def open_steps(simulation: Mapping[str, Any], speaker_id: str) -> list[tuple[str, str]]:
    """The open steps of the hero's active quests a line to ``speaker_id`` may answer, each way of them (EV-3): its
    address, and what it asks, as the reading is told it (the step's summary, and its ``about``, which describes the
    subject; no word is matched)."""
    found: list[tuple[str, str]] = []
    for quest in map(_d, _l(_d(_sections.quest_state_of(simulation)).get("quests"))):
        steps = [_d(step) for step in _l(quest.get("steps"))]
        stage = int(_d(quest.get("progress")).get("stage") or 0)
        quest_id = _s(quest.get("quest_id") or quest.get("id"))
        if quest.get("status") != "active" or stage >= len(steps) or not quest_id:
            continue
        for index, (way, told) in enumerate(step_ways(steps[stage])):
            talk = next((condition for condition in way if _s(condition.get("talk")) == speaker_id), None)
            if talk is None:
                continue
            about = [_s(word) for word in (_l(talk.get("about")) or [talk.get("about")]) if _s(word)]
            asks = _s(steps[stage].get("summary")) + (f" (about: {', '.join(about)})" if about else "")
            found.append((step_address(quest_id, _s(steps[stage].get("id")), index),
                          asks + (f"; this way: {told}" if told and len(step_ways(steps[stage])) > 1 else "")))
    return found


def accepted_step(simulation: Mapping[str, Any], speaker_id: str, step: str) -> str:
    """The step a reading proposed a line answers, accepted only when it is one of ``speaker_id``'s open steps: the
    speaker is its subject, the step is open, and the hero stands where the speaker is (EV-3); else none."""
    return step if step and step in {address for address, _ in open_steps(simulation, speaker_id)} else ""


__all__ = ["ANYONE", "DONE_REGARD", "FAILED_REGARD", "accepted_step", "fold_quest_offer", "giver_thanks", "open_steps", "quest_progress",
           "step_address", "step_ways", "victories"]
