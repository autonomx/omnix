"""Event Injector - Phase-Based Narrative Event Injection.

TIER 18: Narrative Intelligence - Meta-AI Story Director
"""

from app.apps.rpg.foundation.core.determinism import deterministic_rng


class EventInjector:
    """Injects narrative events based on story phase."""

    def inject(self, story_state, world):
        events = []
        phase = story_state.phase
        rng = deterministic_rng("narrative.event_injector", {"phase": str(phase)})

        if phase == "climax":
            if rng.random() < 0.3:
                events.append({"type": "major_betrayal", "impact": 1.0})
            if rng.random() < 0.2:
                events.append({"type": "boss_appearance", "impact": 0.9})

        elif phase == "falling":
            if rng.random() < 0.4:
                events.append({"type": "resolution_opportunity", "impact": 0.6})
            if rng.random() < 0.3:
                events.append({"type": "loose_end", "impact": 0.4})

        else:  # rising
            if rng.random() < 0.3:
                events.append({"type": "complication", "impact": 0.5})
            if rng.random() < 0.2:
                events.append({"type": "foreshadowing", "impact": 0.3})
            if rng.random() < 0.15:
                events.append({"type": "minor_conflict", "impact": 0.4})

        return events
