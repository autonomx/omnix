"""RPG Director — Emergence-driven narrative intervention system.

The Director observes system-level patterns and injects events to shape
narrative without scripting. It creates guided emergence rather than
random or scripted events.

Architecture:
    Director receives: OBSERVE -> ANALYZE -> DECIDE -> INJECT EVENT
    
    This happens AFTER all NPCs act in the game loop.
    The Director closes the loop: Director Output -> NPC decisions -> Outcomes -> Director feedback

Key capabilities:
    - Stagnation detection: Injects twists when nothing is happening
    - Conflict escalation: Intensifies when conflict spikes
    - Failure intervention: Assists NPCs on failure streaks
    - Divergence management: Introduces chaos when system is too predictable
    - Event history tracking: Avoids repetition and maintains narrative threads
    - Cooldown system: Prevents event spam
    - Targeted events: Can target specific NPCs rather than global effects

Components:
    Director: Main loop orchestrator that decides interventions
    EventEngine: Creates and applies world-level events
    EmergenceAdapter: Standardizes system metrics for Director consumption
"""

from .director import Director
from .event_engine import EventEngine
from .emergence_adapter import EmergenceAdapter

__all__ = ["Director", "EventEngine", "EmergenceAdapter"]