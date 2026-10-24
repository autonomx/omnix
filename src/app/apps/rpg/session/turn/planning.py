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
PipelineMechanic = Literal["look", "wait", "clarify", "travel"]


class PlannedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mechanic: PipelineMechanic
    target_id: str = ""
    # How long it takes, in turns of the campaign clock.
    ticks: int = 1
    reason: str = ""
    question: str = ""


def plan_action(reading: IntentCandidate, *, fighting: bool = False) -> PlannedAction | None:
    """The plan for a confident, single-step reading of a mechanic the pipeline runs; else ``None``.

    In a fight a bare "attack" means the foe in front of the hero, so it is not asked about.
    """
    question = clarification(reading)
    if question and not (fighting and reading.reason == "attack_without_target"):
        return PlannedAction(mechanic="clarify", ticks=0, reason=reading.reason, question=question)
    if reading.confidence < SKIP_CONFIDENCE or len(reading.clauses) > 1:
        return None
    if reading.family == "look":
        return PlannedAction(mechanic="look", target_id=reading.target_id or "", reason=reading.reason)
    if reading.family == "move" and reading.target_kind == "place" and reading.target_id:
        return PlannedAction(mechanic="travel", target_id=reading.target_id, reason=reading.reason)
    if reading.family == "wait":
        return PlannedAction(mechanic="wait", ticks=3, reason=reading.reason)  # a while: half an hour
    return None


__all__ = ["PipelineMechanic", "PlannedAction", "plan_action"]
