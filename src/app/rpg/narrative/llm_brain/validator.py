"""Validator - Safety layer to prevent LLM chaos. TIER 19."""
from __future__ import annotations
from .narrative_brain import NarrativeDecision
MAX_TD, MAX_EV = 0.2, 3
VALID_PACING = {"slow", "normal", "fast"}
class BrainOutputValidator:
    def validate(self, decision: NarrativeDecision) -> NarrativeDecision:
        decision.tension_delta = max(-MAX_TD, min(MAX_TD, decision.tension_delta))
        decision.events = decision.events[:MAX_EV]
        if decision.pacing not in VALID_PACING: decision.pacing = "normal"
        return decision
