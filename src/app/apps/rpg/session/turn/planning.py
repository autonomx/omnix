"""Step 3: what the turn will do, decided from the reading and the campaign's state (roadmap §4.1).

A ``PlannedAction`` names the mechanic that owns it and what it acts on. Only the mechanics already on the
pipeline are planned here; for anything else ``plan_action`` returns ``None`` and the turn takes the older path.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.apps.rpg.rules.intent.grammar import IntentCandidate
from app.apps.rpg.session.command_reading import SKIP_CONFIDENCE

PipelineMechanic = Literal["look", "wait"]


class PlannedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mechanic: PipelineMechanic
    target_id: str = ""
    # How long it takes, in turns of the campaign clock.
    ticks: int = 1
    reason: str = ""


def plan_action(reading: IntentCandidate) -> PlannedAction | None:
    """The plan for a confident, single-step reading of a mechanic the pipeline runs; else ``None``."""
    if reading.confidence < SKIP_CONFIDENCE or len(reading.clauses) > 1:
        return None
    if reading.family == "look":
        return PlannedAction(mechanic="look", target_id=reading.target_id or "", reason=reading.reason)
    if reading.family == "wait":
        return PlannedAction(mechanic="wait", reason=reading.reason)
    return None


__all__ = ["PipelineMechanic", "PlannedAction", "plan_action"]
