"""Step 3: what the turn will do, decided from the reading and the campaign's state (roadmap §4.1).

A ``PlannedAction`` names the mechanic that owns it and what it acts on. Only the mechanics already on the
pipeline are planned here; for anything else ``plan_action`` returns ``None`` and the turn takes the older path.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.apps.rpg.rules.intent.grammar import IntentCandidate
from app.apps.rpg.session.command_reading import SKIP_CONFIDENCE, clarification

# clarify: the command is unclear whatever is going on, so the turn ends with the game's question (step 3).
PipelineMechanic = Literal["look", "wait", "clarify", "travel", "trade", "use_item", "drop", "take", "rest",
                           "quest", "practice", "status", "party", "order", "talk", "fight", "equip", "unequip",
                           "ability", "check", "grow"]


# What cannot be done while a fight is on: leaving, resting, trading, talking it over (combat.md).
_NOT_IN_A_FIGHT = frozenset({"move", "rest", "wait", "buy", "sell", "take", "drop", "give", "quest", "practice",
                             "party", "talk", "ask", "look", "inspect"})


class PlannedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mechanic: PipelineMechanic
    target_id: str = ""
    # How long it takes, in turns of the campaign clock.
    ticks: int = 1
    reason: str = ""
    question: str = ""
    second_target_id: str = ""  # an ability's target (the foe it is aimed at)


def plan_action(reading: IntentCandidate, *, fighting: bool = False) -> PlannedAction | None:
    """The plan for a confident, single-step reading of a mechanic the pipeline runs; else ``None``.

    In a fight a bare "attack" means the foe in front of the hero, so it is not asked about.
    """
    question = clarification(reading)
    if question and not (fighting and reading.reason == "attack_without_target"):
        return PlannedAction(mechanic="clarify", ticks=0, reason=reading.reason, question=question)
    if len(reading.clauses) > 1:
        return None
    if fighting and reading.reason == "attack_without_target":
        return PlannedAction(mechanic="fight", ticks=0, reason="attack")  # "attack": the foe in front of the hero
    if reading.family == "attack" and (fighting or (reading.target_kind in {"creature", "person"} and reading.target_id)):
        # A creature the world knows or a person present, or in a fight the foe in front of the hero (combat.md).
        return PlannedAction(mechanic="fight", target_id=reading.target_id or "", ticks=0, reason="attack")
    if reading.family == "ability" and reading.target_id and (fighting or reading.second_target_id):
        # In a fight, or aimed at a foe present: what it does there is the ability rule's (combat.md).
        return PlannedAction(mechanic="ability", target_id=reading.target_id, ticks=0,
                             second_target_id=reading.second_target_id or "",
                             reason="in_fight" if fighting else "opening")
    if not fighting and reading.family == "grow":
        return PlannedAction(mechanic="grow", ticks=0, reason="level_choice")  # a level's choice (progression.md)
    if not fighting and reading.family == "check" and reading.reason.startswith("check:"):
        # A try decided by a roll (checks.md); in a fight it is no time for it.
        return PlannedAction(mechanic="check", target_id=reading.target_id or "", ticks=1,
                             reason=reading.reason.removeprefix("check:"))
    if not fighting and reading.family == "manipulate" and reading.reason == "searches":
        return PlannedAction(mechanic="check", target_id=reading.target_id or "", ticks=1, reason="search")
    if reading.family == "defend" and fighting:
        return PlannedAction(mechanic="fight", ticks=0, reason="defend")
    if reading.family == "flee" and fighting:
        return PlannedAction(mechanic="fight", ticks=0, reason="flee")
    if fighting and reading.family == "use_item" and reading.target_kind == "item" and reading.target_id:
        # Something carried, used in the fight: the hero's turn, and then everyone else's (combat.md).
        return PlannedAction(mechanic="use_item", target_id=reading.target_id, ticks=0, reason="in_fight")
    if fighting and reading.family in _NOT_IN_A_FIGHT:
        return PlannedAction(mechanic="fight", ticks=0, reason="busy")  # the game says no: the fight goes on
    if fighting and reading.family != "status":
        return None  # a move the grammar does not name; abilities and orders in a fight are RQ-2.6 part 2's
    if reading.family in {"buy", "sell"}:  # which offer, or which buyer, is the trade rule's to say
        return PlannedAction(mechanic="trade", reason=reading.family)
    if reading.confidence < SKIP_CONFIDENCE:
        return None
    if reading.family == "look":
        return PlannedAction(mechanic="look", target_id=reading.target_id or "", reason=reading.reason)
    if reading.family == "move" and reading.target_kind == "place" and reading.target_id:
        return PlannedAction(mechanic="travel", target_id=reading.target_id, reason=reading.reason)
    if (reading.family in {"use_item", "drop", "take", "equip", "unequip"} and reading.target_kind == "item"
            and reading.target_id):
        return PlannedAction(mechanic=reading.family, target_id=reading.target_id, ticks=0, reason=reading.reason)
    if reading.family == "quest" and reading.target_kind == "quest":
        return PlannedAction(mechanic="quest", target_id=reading.target_id or "", ticks=0, reason=reading.reason)
    if reading.family == "practice" and reading.target_kind == "skill":
        return PlannedAction(mechanic="practice", target_id=reading.target_id or "", ticks=0, reason=reading.reason)
    if reading.family == "status":
        return PlannedAction(mechanic="status", ticks=0, reason=reading.reason)
    if reading.family in {"party", "order"} and reading.target_kind == "person" and reading.target_id:
        return PlannedAction(mechanic=reading.family, target_id=reading.target_id, ticks=0, reason=reading.reason)
    if reading.family in {"talk", "ask"} and (reading.target_kind == "person" or not reading.target_id):
        # Someone named, or the one the hero is talking to; whether anyone present is, is the dialogue's to say.
        return PlannedAction(mechanic="talk", target_id=reading.target_id or "", ticks=0, reason=reading.reason)
    if reading.family == "rest":
        return PlannedAction(mechanic="rest", ticks=0, reason=reading.reason)
    if reading.family == "wait":
        return PlannedAction(mechanic="wait", ticks=3, reason=reading.reason)  # a while: half an hour
    return None


__all__ = ["PipelineMechanic", "PlannedAction", "plan_action"]
