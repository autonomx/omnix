"""Unified NPC decision pipeline.

This module collapses GOAP + LLM mind + intent into ONE authoritative
decision pipeline.

Core classes:
    DecisionContext: Context object for a single decision cycle.
    DecisionEngine: The ONLY entry point for NPC decisions.
    ActionResolver: Resolves structured plans into final actions.
    DecisionOutcome: Structured result of an executed action.
    OutcomeRecorder: Records outcomes into NPC memory.
"""

from .decision_engine import DecisionContext, DecisionEngine
from .resolver import ActionResolver
from .feedback import DecisionOutcome
from .outcome import OutcomeRecorder

__all__ = [
    "DecisionContext",
    "DecisionEngine",
    "ActionResolver",
    "DecisionOutcome",
    "OutcomeRecorder",
]