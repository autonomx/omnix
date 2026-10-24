"""The one turn pipeline (RQ-1.4, roadmap §4.1).

A turn is a ``TurnRequest``. The pipeline loads the campaign once, interprets the text (the command grammar
first), plans a ``PlannedAction``, resolves it to ``StateChange`` values with the owning mechanic's pure
resolver, applies them with the reducer (the only mutation), lets the world tick for the time the turn took,
and hands the result to the commit. Mechanics move onto it one at a time (RQ-2), each with its own rule;
``OMNIX_RPG_TURN_PIPELINE_OFF`` keeps named ones on the older path.
"""
from __future__ import annotations

from app.apps.rpg.session.turn.planning import PlannedAction, plan_action
from app.apps.rpg.session.turn.request import TurnKind, TurnRequest
from app.apps.rpg.session.turn.run import pipeline_enabled, run_planned_turn

__all__ = ["PlannedAction", "TurnKind", "TurnRequest", "pipeline_enabled", "plan_action", "run_planned_turn"]
