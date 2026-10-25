"""The one turn pipeline (RQ-1.4, roadmap §4.1).

A turn is a ``TurnRequest``. The pipeline loads the campaign once, interprets the text (the command grammar
first, then one intent call when it is not sure: RQ-3.2), plans a ``PlannedAction``, resolves it to ``StateChange``
values with the owning mechanic's pure resolver, applies them with the reducer (the only mutation), lets the world
tick for the time the turn took, and hands the result to the commit. Every turn takes it: what no rule decides is a
free action, told and kept as nothing.
"""
from __future__ import annotations

from app.apps.rpg.session.turn.planning import PlannedAction, plan_action
from app.apps.rpg.session.turn.request import TurnKind, TurnRequest
from app.apps.rpg.session.turn.run import run_planned_turn

__all__ = ["PlannedAction", "TurnKind", "TurnRequest", "plan_action", "run_planned_turn"]
