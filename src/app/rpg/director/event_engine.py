"""Event Engine — Creates and applies world-level events.

The EventEngine translates Director intervention decisions into concrete
world changes. It handles:

    1. Event creation: Maps decision types to specific events
    2. Event application: Modifies world state based on event type
    3. Event variety: Pool of events per intervention type

Design principle: "Narrative without scripting — events serve the system, not a story script."

Event Types:
    twist: Unexpected events change the situation (betrayal, surprise)
    escalation: Intensify existing conflict (reinforcements, threat increase)
    intervention: Assist struggling entities (supply drop, healing)
    chaos: Environmental unpredictability (hazards, random effects)
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

# ============================================================
# Event definitions — expandable pool per intervention type
# ============================================================

TWIST_EVENTS = [
    {
        "name": "unexpected_betrayal",
        "description": "An ally turns against the group",
        "world_effects": {"trust_level": -0.5},
        "tags": ["betrayal", "social"],
    },
    {
        "name": "hidden_ally_revealed",
        "description": "A secret supporter emerges from the shadows",
        "world_effects": {"trust_level": 0.3},
        "tags": ["alliance", "social"],
    },
    {
        "name": "sudden_opportunity",
        "description": "A critical weakness in the enemy line is exposed",
        "world_effects": {"enemy_count": -1},
        "tags": ["opportunity"],
    },
    {
        "name": "information_leak",
        "description": "Secret plans fall into the wrong hands",
        "world_effects": {"trust_level": -0.3, "danger_level": 1},
        "tags": ["betrayal", "danger"],
    },
]

ESCALATION_EVENTS = [
    {
        "name": "enemy_reinforcements",
        "description": "More enemies arrive",
        "world_effects": {"enemy_count": 2},
        "tags": ["enemies", "combat"],
    },
    {
        "name": "enemy_leader_appears",
        "description": "A dangerous enemy leader enters the scene",
        "world_effects": {"enemy_count": 1, "danger_level": 2},
        "tags": ["enemies", "leader"],
    },
    {
        "name": "supply_line_cut",
        "description": "Resources become harder to obtain",
        "world_effects": {"resources": -2, "danger_level": 1},
        "tags": ["economy", "danger"],
    },
    {
        "name": "territory_lost",
        "description": "The enemy pushes into controlled areas",
        "world_effects": {"danger_level": 2, "resources": -1},
        "tags": ["territory", "danger"],
    },
]

INTERVENTION_EVENTS = [
    {
        "name": "supply_drop",
        "description": "Helpful resources appear nearby",
        "world_effects": {"resources": 3},
        "tags": ["resources", "assistance"],
    },
    {
        "name": "unexpected_reinforcement",
        "description": "Allies arrive to bolster the defense",
        "world_effects": {"enemy_count": -1, "trust_level": 0.2},
        "tags": ["alliance", "assistance"],
    },
    {
        "name": "moment_of_clarity",
        "description": "Strategic insight reveals a path forward",
        "world_effects": {"trust_level": 0.3},
        "tags": ["insight", "assistance"],
    },
    {
        "name": "safe_haven_discovered",
        "description": "A hidden refuge is found nearby",
        "world_effects": {"danger_level": -1, "resources": 1},
        "tags": ["shelter", "assistance"],
    },
]

CHAOS_EVENTS = [
    {
        "name": "environmental_hazard",
        "description": "The environment becomes dangerous",
        "world_effects": {"danger_level": 2},
        "tags": ["environment", "danger"],
    },
    {
        "name": "storm_approaches",
        "description": "Severe weather threatens everyone",
        "world_effects": {"danger_level": 1, "resources": -1},
        "tags": ["weather", "danger"],
    },
    {
        "name": "wild_animals_stirred",
        "description": "Dangerous creatures are awakened",
        "world_effects": {"enemy_count": 1, "danger_level": 1},
        "tags": ["wildlife", "danger"],
    },
    {
        "name": "earth_tremors",
        "description": "The ground shakes unpredictably",
        "world_effects": {"danger_level": 2, "trust_level": -0.2},
        "tags": ["environment", "danger"],
    },
]

# Map from intervention type to event pool
EVENT_POOLS: Dict[str, List[Dict[str, Any]]] = {
    "twist": TWIST_EVENTS,
    "escalation": ESCALATION_EVENTS,
    "intervention": INTERVENTION_EVENTS,
    "chaos": CHAOS_EVENTS,
}


class EventEngine:
    """Creates and applies world-level events from Director decisions.

    The EventEngine is responsible of turning high-level Director intervention
    signals into concrete world state changes. It maintains an event history
    to avoid repetition and supports targeted events against specific NPCs.

    Attributes:
        history: List of all events that have been applied.
        last_event_type: The most recent event type applied (for cooldown).
        targeted_events: Whether targeted (NPC-specific) events are enabled.
    """

    def __init__(self, targeted: bool = True):
        """Initialize EventEngine.

        Args:
            targeted: Whether to support NPC-targeted events.
        """
        self.history: List[Dict[str, Any]] = []
        self.last_event_type: Optional[str] = None
        self.targeted = targeted

    def create_event(
        self,
        decision: Dict[str, Any],
        world_state: Dict[str, Any],
        npcs: Optional[List[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create an event from a Director decision.

        Maps the decision type to a specific event, applying variety
        logic to avoid repeating the same event.

        Args:
            decision: Director decision dict with 'type' and 'intensity' keys.
            world_state: Current world state for context.
            npcs: Optional list of NPCs for targeted events.

        Returns:
            Event dict with name, description, tags, and world_effects.
        """
        event_type = decision.get("type", "chaos")
        intensity = decision.get("intensity", 0.5)
        target_npc = decision.get("target_npc")

        # Get event pool for this decision type
        pool = EVENT_POOLS.get(event_type, CHAOS_EVENTS)
        if not pool:
            return None

        # Pick event from pool — avoid last event for variety
        available = [e for e in pool if e.get("name") != self.last_event_type]
        if not available:
            available = pool  # Fallback to full pool

        event = random.choice(available).copy()
        event["event_type"] = event_type
        event["intensity"] = intensity
        event["tick_applied"] = len(self.history)

        # Apply intensity scaling to world effects
        if "world_effects" in event:
            for key, value in event["world_effects"].items():
                if isinstance(value, (int, float)):
                    event["world_effects"][key] = value * intensity

        # Handle targeted events
        if self.targeted and target_npc and npcs:
            event["target"] = target_npc
            event["targeted"] = True

        return event

    def apply_event(
        self,
        event: Optional[Dict[str, Any]],
        world_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply an event's effects to the world state.

        Args:
            event: Event dict from create_event, or None.
            world_state: World state dict to modify in place.

        Returns:
            The event that was applied, or None if no event.
        """
        if not event:
            return None

        name = event.get("name", "unknown")
        effects = event.get("world_effects", {})

        for key, delta in effects.items():
            if isinstance(delta, (int, float)):
                current = world_state.get(key, 0)
                world_state[key] = current + delta
                # Clamp common stats
                if key == "trust_level":
                    world_state[key] = max(-1.0, min(1.0, world_state[key]))
                elif key in ("enemy_count", "danger_level"):
                    world_state[key] = max(0, world_state[key])
                elif key == "resources":
                    world_state[key] = max(0, world_state[key])

        self.history.append(event)
        self.last_event_type = name

        return event

    def get_event_summary(self) -> Dict[str, Any]:
        """Get summary of events for debugging/analysis.

        Returns:
            Dict with event counts by type and recent event names.
        """
        type_counts: Dict[str, int] = {}
        recent_names: List[str] = []

        for event in self.history[-10:]:
            etype = event.get("event_type", "unknown")
            type_counts[etype] = type_counts.get(etype, 0) + 1
            recent_names.append(event.get("name", "unknown"))

        return {
            "total_events": len(self.history),
            "by_type": type_counts,
            "recent_events": recent_names,
        }

    def reset(self) -> None:
        """Clear event history and state."""
        self.history.clear()
        self.last_event_type = None